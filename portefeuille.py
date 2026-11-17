# portefeuille.py
# ==============================================================================
# PORTEFEUILLE RECOMMANDÉ — calculé par le cron, affiché par l'appli
# ==============================================================================
# Méthode (volontairement simple et robuste, à titre indicatif) :
#   1. Présélection : titres avec 1 an d'historique complet, classés par
#      momentum 12-1 mois ajusté du risque (rendement 12 mois hors dernier mois
#      / volatilité). On écarte les titres en détresse (Z-Score < 1,81).
#   2. Optimisation de Markowitz « portefeuille tangent » (Sharpe maximal),
#      sans vente à découvert, avec un plafond par ligne (20 %) pour éviter
#      qu'un seul titre domine.
#      - Covariance estimée par Ledoit-Wolf (stable avec peu d'observations).
#      - Rendements attendus « rétrécis » de 50 % vers une hypothèse de long
#        terme (8 %/an) : le rendement passé d'un titre prédit mal son rendement
#        futur ; sans rétrécissement, Markowitz concentre tout sur les gagnants.
#      - Estimation sur 3 ans d'historique.
#   4. Frontière efficiente : pour une grille de rentabilités visées, le
#      portefeuille de variance minimale qui l'atteint (même contraintes).
#   3. Épuration : au plus 12 lignes d'au moins 3 %, en ré-optimisant sur les
#      titres retenus (supprimer des lignes sans ré-optimiser casserait le
#      portefeuille, surtout le moins risqué qui se répartit sur beaucoup de titres).
# Les statistiques (rendement, volatilité, perte max) sont mesurées sur l'année
# passée : elles décrivent ce qu'aurait fait CE portefeuille, pas une promesse.
# ==============================================================================
import numpy as np
import pandas as pd

RF = 0.0435             # taux sans risque annuel (même valeur que l'appli)
N_CANDIDATS = 40
POIDS_MAX = 0.20
POIDS_MIN = 0.03
N_MAX_LIGNES = 12       # au-delà, trop de petits ordres pour un petit capital
RETRECISSEMENT = 0.5    # poids de l'hypothèse long terme dans le rendement attendu
RENDEMENT_LT = 0.08     # hypothèse de rendement long terme des actions US (~8 %/an)
JOURS = 252
JOURS_ESTIMATION = 3 * 252  # 3 ans pour estimer rendements et covariance (plus stable qu'1 an)
N_FRONTIERE = 12


def _matrice_rendements(market_raw: pd.DataFrame, symboles: list[str], jours: int = JOURS) -> pd.DataFrame:
    px = (market_raw[market_raw["symbol"].isin(symboles)]
          .pivot_table(index="date", columns="symbol", values="close")
          .sort_index())
    px = px.iloc[-(jours + 1):]
    px = px.dropna(axis=1, thresh=int(len(px) * 0.95)).ffill().dropna()
    return px.pct_change().dropna()


def estimations(R: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """(rendements attendus annuels rétrécis, covariance annuelle Ledoit-Wolf)."""
    from sklearn.covariance import LedoitWolf
    cov = LedoitWolf().fit(R.values).covariance_ * JOURS
    mu_hist = R.mean().values * JOURS
    mu = (1 - RETRECISSEMENT) * mu_hist + RETRECISSEMENT * RENDEMENT_LT
    return mu, cov


def preselection(market_raw: pd.DataFrame, snapshot: pd.DataFrame, n: int = N_CANDIDATS) -> list[str]:
    """Top n par momentum 12-1 / volatilité, hors titres en détresse financière."""
    ok = snapshot.copy()
    if "z_score" in ok:
        ok = ok[~(ok["z_score"].astype(float) < 1.81)]
    px = (market_raw[market_raw["symbol"].isin(ok["symbol"])]
          .pivot_table(index="date", columns="symbol", values="close").sort_index())
    px = px.iloc[-(JOURS + 1):].dropna(axis=1, thresh=int(JOURS * 0.95)).ffill()
    if len(px) < JOURS // 2:
        return []
    mom_12_1 = px.iloc[-22] / px.iloc[0] - 1                       # 12 mois hors dernier mois
    vol = px.pct_change().std() * np.sqrt(JOURS)
    score = (mom_12_1 / vol.replace(0, np.nan)).dropna().sort_values(ascending=False)
    return score.index[:n].tolist()


def _optimiser(objectif, n: int, poids_max: float, contraintes: list) -> np.ndarray | None:
    from scipy.optimize import minimize
    w0 = np.full(n, 1 / n)
    # Tolérance fine : les variances annuelles valent ~0,005, la tolérance par défaut
    # de SLSQP (1e-6) arrêtait l'optimisation presque au point de départ.
    res = minimize(objectif, w0, method="SLSQP", bounds=[(0.0, poids_max)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}] + contraintes,
                   options={"maxiter": 1000, "ftol": 1e-12})
    w = np.clip(res.x, 0, None)
    # SLSQP signale parfois un échec (« Positive directional derivative ») alors que
    # la solution est correcte : on l'accepte si toutes les contraintes sont tenues.
    faisable = (abs(w.sum() - 1) < 1e-4 and w.max() <= poids_max + 1e-4
                and all(c["fun"](w) >= -1e-4 for c in contraintes))
    return w if (res.success or faisable) else None


def _resoudre(mu: np.ndarray, cov: np.ndarray, poids_max: float, cible: float | None) -> np.ndarray | None:
    """cible=None : Sharpe maximal ; sinon variance minimale avec rendement >= cible."""
    n = len(mu)
    if n * poids_max < 1 - 1e-9:
        return None
    if cible is None:
        def objectif(w):
            vol = np.sqrt(w @ cov @ w)
            return -(w @ mu - RF) / vol if vol > 0 else 0.0
        return _optimiser(objectif, n, poids_max, [])
    contraintes = [{"type": "ineq", "fun": lambda w: w @ mu - cible}] if np.isfinite(cible) else []
    return _optimiser(lambda w: 1e4 * (w @ cov @ w), n, poids_max, contraintes)


def _optimiser_epure(mu: np.ndarray, cov: np.ndarray, colonnes, poids_max: float, cible: float | None) -> pd.Series | None:
    """Optimise, garde au plus N_MAX_LIGNES lignes >= POIDS_MIN, ré-optimise sur ce sous-ensemble.

    Si le sous-ensemble ne permet plus d'atteindre la cible, on garde la dernière
    solution valide (quitte à avoir quelques petites lignes de plus).
    """
    idx = np.arange(len(mu))
    n_min = int(np.ceil(1 / poids_max - 1e-9))
    meilleur = None  # (w, idx) dernière solution valide
    for _ in range(4):
        w = _resoudre(mu[idx], cov[np.ix_(idx, idx)], poids_max, cible)
        if w is None or (cible is not None and np.isfinite(cible) and w @ mu[idx] < cible - 1e-4):
            break
        meilleur = (w, idx)
        ordre = np.argsort(-w)
        garder = [i for i in ordre[:N_MAX_LIGNES] if w[i] >= POIDS_MIN]
        if len(garder) < n_min:
            garder = list(ordre[:max(n_min, min(N_MAX_LIGNES, len(ordre)))])
        if len(garder) == len(idx):
            break
        idx = idx[sorted(garder)]
    if meilleur is None:
        return None
    w, idx = meilleur
    return _nettoyer(pd.Series(w, index=[colonnes[i] for i in idx]))


def markowitz_tangent(R: pd.DataFrame, poids_max: float = POIDS_MAX) -> pd.Series:
    """Poids long-only maximisant le Sharpe, plafonnés, au plus N_MAX_LIGNES lignes."""
    mu, cov = estimations(R)
    w = _optimiser_epure(mu, cov, list(R.columns), poids_max, None)
    return w if w is not None else pd.Series(1 / R.shape[1], index=R.columns)


def frontiere_efficiente(R: pd.DataFrame, n_points: int = N_FRONTIERE, poids_max: float = POIDS_MAX) -> list[dict]:
    """Pour une grille de rentabilités visées : portefeuille de variance minimale.

    Chaque point : {cible, rendement, volatilite, sharpe, lignes: [{symbol, poids}]}.
    La grille va du portefeuille le moins risqué au plus rentable atteignable
    sous le plafond par ligne.
    """
    mu, cov = estimations(R)
    cols = list(R.columns)
    w_minvar = _optimiser_epure(mu, cov, cols, poids_max, -np.inf)
    if w_minvar is None:
        return []
    # Rendement maximal sous plafond : les meilleurs titres à poids_max
    r_max = float(np.sort(mu)[::-1][:int(np.ceil(1 / poids_max))].mean())
    r_min = float(w_minvar.reindex(cols).fillna(0).values @ mu)

    points = []
    for cible in np.linspace(r_min, r_max * 0.995, n_points):
        w = w_minvar if cible <= r_min + 1e-9 else _optimiser_epure(mu, cov, cols, poids_max, float(cible))
        if w is None:
            continue
        wv = w.reindex(cols).fillna(0).values
        rend, vol = float(wv @ mu), float(np.sqrt(wv @ cov @ wv))
        if points and rend < points[-1]["rendement"] - 1e-6:
            continue  # l'épuration peut faire reculer légèrement : on garde une frontière croissante
        points.append({
            "cible": float(cible), "rendement": rend, "volatilite": vol,
            "sharpe": (rend - RF) / vol if vol > 0 else None,
            "lignes": [{"symbol": k, "poids": float(v)} for k, v in w.items()],
        })
    # Frontière efficiente au sens strict : on retire les points dominés
    # (un autre point fait au moins aussi bien en rentabilité ET en risque).
    # Tolérance de 2 % (relatif) sur le risque : +10 pts de rentabilité pour un risque
    # identique à 0,0002 près, c'est un portefeuille meilleur.
    def domine(a, b):
        return (b["rendement"] > a["rendement"] + 1e-6 and b["volatilite"] <= a["volatilite"] * 1.02)
    points = [a for a in points if not any(domine(a, b) for b in points if b is not a)]
    # Doublons (même portefeuille pour plusieurs cibles)
    uniques = []
    for p in points:
        if not uniques or abs(p["rendement"] - uniques[-1]["rendement"]) > 1e-6:
            uniques.append(p)
    return uniques


def _nettoyer(w: pd.Series) -> pd.Series:
    """Renormalise, re-plafonne (arrondis de l'optimiseur) et trie."""
    w = w[w > 1e-6]
    w = w / w.sum()
    for _ in range(200):
        trop = w > POIDS_MAX + 1e-9
        if not trop.any():
            break
        surplus = (w[trop] - POIDS_MAX).sum()
        w[trop] = POIDS_MAX
        w[~trop] += surplus * w[~trop] / w[~trop].sum()
    return w.sort_values(ascending=False)


def stats_portefeuille(R: pd.DataFrame, w: pd.Series) -> dict:
    pr = R[w.index].values @ w.values
    ann_ret = float((1 + pr).prod() ** (JOURS / len(pr)) - 1)
    ann_vol = float(pr.std() * np.sqrt(JOURS))
    courbe = np.cumprod(1 + pr)
    mdd = float((courbe / np.maximum.accumulate(courbe) - 1).min())
    return {
        "rendement_1y": ann_ret,
        "volatilite": ann_vol,
        "sharpe": (ann_ret - RF) / ann_vol if ann_vol > 0 else None,
        "perte_max": mdd,
        "n_jours": int(len(pr)),
    }


def portefeuille_recommande(market_raw: pd.DataFrame, snapshot: pd.DataFrame) -> dict | None:
    """Retourne {lignes: [...], stats: {...}, methode: str} ou None si données insuffisantes."""
    if market_raw.empty or snapshot.empty:
        return None
    candidats = preselection(market_raw, snapshot)
    if len(candidats) < 5:
        return None
    R = _matrice_rendements(market_raw, candidats, JOURS_ESTIMATION)
    if R.shape[1] < 5 or len(R) < JOURS // 2:
        return None

    w = markowitz_tangent(R)
    mu, cov = estimations(R)
    wv = w.reindex(R.columns).fillna(0).values
    infos = snapshot.set_index("symbol")
    lignes = []
    for sym, poids in w.items():
        r = R[sym].iloc[-JOURS:]
        lignes.append({
            "symbol": sym,
            "nom": infos.at[sym, "nom"] if sym in infos.index else sym,
            "secteur": infos.at[sym, "secteur"] if sym in infos.index else None,
            "poids": float(poids),
            "rendement_1y": float((1 + r).prod() - 1),
            "volatilite": float(r.std() * np.sqrt(JOURS)),
        })
    # Infos de tous les titres présents sur la frontière (pour l'appli)
    titres = {}
    for sym in R.columns:
        r1 = R[sym].iloc[-JOURS:]
        titres[sym] = {
            "nom": infos.at[sym, "nom"] if sym in infos.index else sym,
            "secteur": infos.at[sym, "secteur"] if sym in infos.index else None,
            "prix": float(infos.at[sym, "close"]) if sym in infos.index and "close" in infos else None,
            "rendement_1y": float((1 + r1).prod() - 1),
            "volatilite": float(r1.std() * np.sqrt(JOURS)),
        }
    secteurs = pd.Series({l["secteur"] or "Autre": 0.0 for l in lignes})
    for l in lignes:
        secteurs[l["secteur"] or "Autre"] += l["poids"]
    return {
        "lignes": lignes,
        "stats": stats_portefeuille(R.iloc[-JOURS:], w) | {
            "poids_secteur_max": float(secteurs.max()),
            "secteur_principal": str(secteurs.idxmax()),
            "rendement_attendu": float(wv @ mu),
            "volatilite_attendue": float(np.sqrt(wv @ cov @ wv)),
        },
        "frontiere": frontiere_efficiente(R),
        "titres": titres,
        "methode": (f"Markowitz (Sharpe max), {len(candidats)} candidats présélectionnés par "
                    f"momentum 12-1 ajusté du risque, plafond {int(POIDS_MAX * 100)} % par ligne, "
                    f"au plus {N_MAX_LIGNES} lignes d'au moins {int(POIDS_MIN * 100)} %, "
                    f"covariance Ledoit-Wolf sur 3 ans, rendements attendus = 50 % historique + 50 % hypothèse "
                    f"long terme de {int(RENDEMENT_LT * 100)} %/an."),
    }
