# portefeuille.py
# ==============================================================================
# PORTEFEUILLE RECOMMANDÉ — calculé par le cron, affiché par l'appli
# ==============================================================================
# Méthode (journal des choix et des hypothèses : docs/METHODE.md) :
#   1. Candidats : TOUS les membres actuels du S&P 500 (hors ETF) ayant 3 ans
#      d'historique, hors titres en détresse (Z-Score < 1,81). Pas de présélection
#      par momentum : ce pari n'a pas été probant au laboratoire.
#   2. Risque : covariance Ledoit-Wolf sur 3 ans, mise sous forme factorielle
#      Σ ≈ B·Bᵀ + D (20 composantes principales + risque propre de chaque titre,
#      variance de chaque titre conservée exactement). Assez légère pour l'appli.
#   3. Rendements attendus = 90 % CAPM (taux sans risque + bêta x prime de risque
#      de 5 %) + 10 % historique. Hypothèse de long terme, pas une prévision.
#   4. Optimisation de Markowitz par gradient projeté accéléré (FISTA), MÊME
#      algorithme que l'appli (mobile/src/optim.ts) : pour une grille de compromis
#      λ, min wᵀΣw − λ·wᵀμ sous 0 ≤ w ≤ 20 %, Σw = 1. Chaque λ donne un point de
#      la frontière efficiente ; le portefeuille conseillé est celui au meilleur
#      ratio de Sharpe.
#   5. Épuration : au plus 12 lignes d'au moins 3 %, en ré-optimisant sur les
#      titres retenus.
# Les statistiques (rendement, volatilité, perte max) sont mesurées sur l'année
# passée : elles décrivent ce qu'aurait fait CE portefeuille, pas une promesse.
# ==============================================================================
import numpy as np
import pandas as pd

RF = 0.0435             # taux sans risque annuel (même valeur que l'appli)
N_CANDIDATS = 40        # ancienne présélection par momentum (gardée pour le backtest comparatif)
N_FACTEURS = 20         # composantes principales de la covariance publiée
ITERATIONS = 400        # itérations FISTA (comme l'appli)
N_LAMBDAS = 18          # points de la grille de compromis (comme l'appli)
POIDS_MAX = 0.20
POIDS_MIN = 0.03
N_MAX_LIGNES = 12       # au-delà, trop de petits ordres pour un petit capital
POIDS_HISTORIQUE = 0.1  # part du rendement historique dans le rendement attendu
PRIME_RISQUE = 0.05     # prime de risque actions de long terme (au-dessus du taux sans risque)
INDICE_MARCHE = "SPY"
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


def estimations(R: pd.DataFrame, marche: pd.Series | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(rendements attendus annuels, covariance annuelle Ledoit-Wolf).

    Rendement attendu = 90 % modèle CAPM (taux sans risque + bêta x prime de risque
    de 5 %) + 10 % historique. Les titres sont présélectionnés parce qu'ils ont
    monté : leur rendement historique surestime fortement le futur (biais de
    sélection). Le CAPM ne récompense que le risque de marché (bêta).
    """
    from sklearn.covariance import LedoitWolf
    cov = LedoitWolf().fit(R.values).covariance_ * JOURS
    mu_hist = R.mean().values * JOURS
    m = marche.reindex(R.index).fillna(0.0) if marche is not None else R.mean(axis=1)
    var_m = float(m.var())
    betas = np.array([float(R[c].cov(m)) / var_m if var_m > 0 else 1.0 for c in R.columns])
    mu_capm = RF + betas * PRIME_RISQUE
    mu = (1 - POIDS_HISTORIQUE) * mu_capm + POIDS_HISTORIQUE * mu_hist
    return mu, cov


def ingredients(R: pd.DataFrame, marche: pd.Series | None = None) -> dict:
    """Données brutes pour que l'appli recalcule la frontière avec SES hypothèses
    (taux sans risque, prime de risque, part d'historique, plafonds...).

    {symbols, mu_hist (annuel), beta, facteurs (n x k), idio (n), jours} :
    covariance annuelle Ledoit-Wolf = facteurs·facteursᵀ + diag(idio).
    """
    from sklearn.covariance import LedoitWolf
    cov = LedoitWolf().fit(R.values).covariance_ * JOURS
    B, D = facteurs(cov)
    m = marche.reindex(R.index).fillna(0.0) if marche is not None else R.mean(axis=1)
    var_m = float(m.var())
    return {
        "symbols": list(R.columns),
        "mu_hist": [float(x) for x in R.mean().values * JOURS],
        "beta": [float(R[c].cov(m)) / var_m if var_m > 0 else 1.0 for c in R.columns],
        "facteurs": [[float(f"{x:.6g}") for x in row] for row in B],
        "idio": [float(f"{x:.6g}") for x in D],
        "jours": int(len(R)),
    }


# ------------------------------------------------------------------------------
# Covariance factorielle et optimiseur (identique à mobile/src/optim.ts)
# ------------------------------------------------------------------------------
def facteurs(cov: np.ndarray, k: int = N_FACTEURS) -> tuple[np.ndarray, np.ndarray]:
    """Σ ≈ B·Bᵀ + diag(D) : k premières composantes principales + risque propre.
    D est choisi pour que la variance de chaque titre soit EXACTEMENT conservée."""
    n = cov.shape[0]
    k = max(1, min(k, n - 1)) if n > 1 else 1
    val, vec = np.linalg.eigh(cov)
    ordre = np.argsort(val)[::-1][:k]
    B = vec[:, ordre] * np.sqrt(np.clip(val[ordre], 0, None))
    D = np.clip(np.diag(cov) - (B ** 2).sum(axis=1), 1e-10, None)
    return B, D


def _mul(B: np.ndarray, D: np.ndarray, w: np.ndarray) -> np.ndarray:
    return B @ (B.T @ w) + D * w


def variance(B: np.ndarray, D: np.ndarray, w: np.ndarray) -> float:
    return float(w @ _mul(B, D, w))


def projeter(v: np.ndarray, cap: float, mn: np.ndarray | None = None) -> np.ndarray:
    """Projection euclidienne sur {mn ≤ w ≤ cap, Σw = 1} : w = clip(v − τ, mn, cap), où τ annule
    Σw − 1. Cette somme est affine par morceaux en τ : la méthode de Newton tombe sur la valeur
    exacte en quelques pas (repli : dichotomie, comme l'appli)."""
    bas = mn if mn is not None else np.zeros_like(v)
    tau = float(np.mean(v) - 1 / len(v))
    for _ in range(30):
        w = np.clip(v - tau, bas, cap)
        ecart = w.sum() - 1
        if abs(ecart) < 1e-13:
            return w
        actifs = int(((v - tau > bas) & (v - tau < cap)).sum())
        if actifs == 0:
            break
        tau += ecart / actifs
    lo, hi = v.min() - cap - 1, v.max() + 1
    for _ in range(60):
        mid = (lo + hi) / 2
        if np.clip(v - mid, bas, cap).sum() > 1:
            lo = mid
        else:
            hi = mid
    return np.clip(v - (lo + hi) / 2, bas, cap)


def resoudre(B: np.ndarray, D: np.ndarray, mu: np.ndarray, lam: float, cap: float,
             iters: int = ITERATIONS, mn: np.ndarray | None = None) -> np.ndarray:
    """min wᵀΣw − λ·wᵀμ sur le simplexe plafonné, par FISTA."""
    n = len(mu)
    # Pas : 1 / constante de Lipschitz du gradient 2Σw ; ‖Σ‖ ≤ ‖B·Bᵀ‖ + max D, et ‖B·Bᵀ‖ est la
    # plus grande valeur propre de Bᵀ·B (petite matrice k x k : calcul exact et rapide)
    L = 2 * (float(np.linalg.eigvalsh(B.T @ B).max()) if B.size else 0.0) + 2 * float(D.max())
    pas = 1 / (L + 1e-12)
    w = projeter(np.full(n, 1 / n), cap, mn)
    y, t = w, 1.0
    for _ in range(iters):
        w_suiv = projeter(y - pas * (2 * _mul(B, D, y) - lam * mu), cap, mn)
        t_suiv = (1 + np.sqrt(1 + 4 * t * t)) / 2
        y = w_suiv + ((t - 1) / t_suiv) * (w_suiv - w)
        w, t = w_suiv, t_suiv
    return w


def resoudre_epure(B: np.ndarray, D: np.ndarray, mu: np.ndarray, lam: float, poids_max: float = POIDS_MAX,
                   n_max: int = N_MAX_LIGNES, poids_min: float = POIDS_MIN) -> tuple[np.ndarray, np.ndarray]:
    """Résout puis garde au plus n_max lignes ≥ poids_min en ré-optimisant sur elles. -> (indices, poids)"""
    idx = np.arange(len(mu))
    n_min = int(np.ceil(1 / poids_max - 1e-9))
    w = resoudre(B, D, mu, lam, poids_max)
    for _ in range(4):
        ordre = np.argsort(-w)
        garder = [k for k in ordre if w[k] >= poids_min][:n_max]
        if len(garder) < n_min:
            garder = list(ordre[:max(n_min, min(n_max, len(ordre)))])
        if len(garder) == len(idx):
            break
        idx = idx[np.sort(garder)]
        w = resoudre(B[idx], D[idx], mu[idx], lam, poids_max)
    return idx, w


def frontiere_lambdas(B: np.ndarray, D: np.ndarray, mu: np.ndarray, n_points: int = N_LAMBDAS,
                      poids_max: float = POIDS_MAX) -> list[dict]:
    """Points de la frontière efficiente pour une grille de λ (même grille que l'appli).
    Chaque point : {rendement, volatilite, sharpe, idx, w}, triés, sans points dominés."""
    n = len(mu)
    if n == 0 or poids_max * min(n, N_MAX_LIGNES) < 1 - 1e-9:
        return []
    diag = (B ** 2).sum(axis=1) + D
    echelle = diag.mean() / (np.abs(mu).max() or 1)
    lambdas = [0.0] + [echelle * 10 ** (-2 + 3.5 * k / (n_points - 2)) for k in range(n_points - 1)]
    pts = []
    for lam in lambdas:
        idx, w = resoudre_epure(B, D, mu, lam, poids_max)
        w = w / w.sum()
        r = float(w @ mu[idx])
        vol = float(np.sqrt(max(variance(B[idx], D[idx], w), 0)))
        pts.append({"rendement": r, "volatilite": vol, "sharpe": (r - RF) / vol if vol > 0 else 0.0,
                    "idx": idx, "w": w})
    pts.sort(key=lambda p: p["rendement"])
    garde = [a for a in pts if not any(b is not a and b["rendement"] > a["rendement"] + 1e-6
                                        and b["volatilite"] <= a["volatilite"] * 1.02 for b in pts)]
    out = []
    for p in garde:
        if not out or p["rendement"] - out[-1]["rendement"] > 1e-5:
            out.append(p)
    return out


def optimiser(mu: np.ndarray, B: np.ndarray, D: np.ndarray, colonnes, cible) -> pd.Series | None:
    """Portefeuille épuré : cible=None -> meilleur ratio de Sharpe de la frontière ;
    cible non finie (nan, -inf) -> variance minimale."""
    pts = frontiere_lambdas(B, D, mu)
    if not pts:
        return None
    if cible is None:
        p = max(pts, key=lambda q: q["sharpe"])
    else:
        p = min(pts, key=lambda q: q["volatilite"])
    return _nettoyer(pd.Series(p["w"], index=[colonnes[i] for i in p["idx"]]))


def candidats(market_raw: pd.DataFrame, snapshot: pd.DataFrame) -> list[str]:
    """Tous les membres actuels du S&P 500 (hors ETF) avec 3 ans d'historique, hors détresse."""
    ok = snapshot.copy()
    if "indice" in ok:
        ok = ok[ok["indice"] == "S&P 500"]
    if "is_etf" in ok:
        ok = ok[~ok["is_etf"].fillna(False).astype(bool)]
    if "z_score" in ok:
        ok = ok[~(ok["z_score"].astype(float) < 1.81)]
    px = (market_raw[market_raw["symbol"].isin(ok["symbol"])]
          .pivot_table(index="date", columns="symbol", values="close").sort_index())
    px = px.iloc[-(JOURS_ESTIMATION + 1):]
    if len(px) < JOURS // 2:
        return []
    return sorted(px.dropna(axis=1, thresh=int(len(px) * 0.95)).columns)


def score_momentum(px: pd.DataFrame) -> pd.Series:
    """Ancien critère de présélection : momentum 12-1 mois / volatilité 1 an (non probant)."""
    mom_12_1 = px.iloc[-22] / px.iloc[0] - 1
    vol = px.pct_change().std() * np.sqrt(JOURS)
    return (mom_12_1 / vol.replace(0, np.nan)).dropna().sort_values(ascending=False)


def preselection(market_raw: pd.DataFrame, snapshot: pd.DataFrame, n: int = N_CANDIDATS) -> list[str]:
    """ANCIENNE méthode (jusqu'à la PR #24) : top n par momentum 12-1 / volatilité.
    Plus utilisée pour le portefeuille ; gardée pour le backtest comparatif."""
    ok = snapshot.copy()
    if "z_score" in ok:
        ok = ok[~(ok["z_score"].astype(float) < 1.81)]
    px = (market_raw[market_raw["symbol"].isin(ok["symbol"])]
          .pivot_table(index="date", columns="symbol", values="close").sort_index())
    px = px.iloc[-(JOURS + 1):].dropna(axis=1, thresh=int(JOURS * 0.95)).ffill()
    if len(px) < JOURS // 2:
        return []
    return score_momentum(px).index[:n].tolist()


def markowitz_tangent(R: pd.DataFrame, poids_max: float = POIDS_MAX, marche: pd.Series | None = None) -> pd.Series:
    """Poids long-only au meilleur ratio de Sharpe, plafonnés, au plus N_MAX_LIGNES lignes."""
    mu, cov = estimations(R, marche)
    B, D = facteurs(cov)
    w = optimiser(mu, B, D, list(R.columns), None)
    return w if w is not None else pd.Series(1 / R.shape[1], index=R.columns)


def frontiere_efficiente(R: pd.DataFrame, marche: pd.Series | None = None) -> list[dict]:
    """Frontière publiée : {cible, rendement, volatilite, sharpe, lignes: [{symbol, poids}]}."""
    mu, cov = estimations(R, marche)
    B, D = facteurs(cov)
    cols = list(R.columns)
    out = []
    for p in frontiere_lambdas(B, D, mu):
        w = _nettoyer(pd.Series(p["w"], index=[cols[i] for i in p["idx"]]))
        out.append({"cible": p["rendement"], "rendement": p["rendement"], "volatilite": p["volatilite"],
                    "sharpe": p["sharpe"], "lignes": [{"symbol": k, "poids": float(v)} for k, v in w.items()]})
    return out


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
    cands = candidats(market_raw, snapshot)
    if len(cands) < 5:
        return None
    R = _matrice_rendements(market_raw, cands, JOURS_ESTIMATION)
    marche = None
    if INDICE_MARCHE in set(market_raw["symbol"]):
        px_m = market_raw[market_raw["symbol"] == INDICE_MARCHE].set_index("date")["close"].sort_index()
        marche = px_m.pct_change().reindex(R.index)
    if R.shape[1] < 5 or len(R) < JOURS // 2:
        return None

    mu, cov = estimations(R, marche)
    B, D = facteurs(cov)
    w = optimiser(mu, B, D, list(R.columns), None)
    if w is None:
        return None
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
            "volatilite_attendue": float(np.sqrt(variance(B, D, wv))),
        },
        "frontiere": frontiere_efficiente(R, marche=marche),
        "titres": titres,
        # Nouveau format (forme factorielle) sous une nouvelle clé : les anciennes versions de l'appli,
        # qui attendent `univers.cov`, voient `univers` vide et affichent la frontière du serveur.
        "univers": None,
        "univers_facteurs": ingredients(R, marche),
        "methode": (f"Markowitz (meilleur ratio de Sharpe) parmi les {R.shape[1]} titres du S&P 500 "
                    f"ayant 3 ans d'historique, plafond {int(POIDS_MAX * 100)} % par ligne, "
                    f"au plus {N_MAX_LIGNES} lignes d'au moins {int(POIDS_MIN * 100)} %, "
                    f"covariance Ledoit-Wolf sur 3 ans ({N_FACTEURS} facteurs), rendements attendus = 90 % CAPM "
                    f"(taux sans risque + bêta x prime de risque de {int(PRIME_RISQUE * 100)} %) + 10 % historique."),
    }
