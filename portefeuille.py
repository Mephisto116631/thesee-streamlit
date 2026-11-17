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
#      - Rendements attendus « rétrécis » vers la moyenne : le rendement passé
#        d'un titre prédit mal son rendement futur ; sans rétrécissement,
#        Markowitz concentre tout sur les gagnants de l'année.
#   3. Les lignes < 4 % sont supprimées puis les poids renormalisés.
# Les statistiques (rendement, volatilité, perte max) sont mesurées sur l'année
# passée : elles décrivent ce qu'aurait fait CE portefeuille, pas une promesse.
# ==============================================================================
import numpy as np
import pandas as pd

RF = 0.0435             # taux sans risque annuel (même valeur que l'appli)
N_CANDIDATS = 40
POIDS_MAX = 0.20
POIDS_MIN = 0.04
RETRECISSEMENT = 0.5    # 0 = rendements historiques bruts, 1 = tous identiques
JOURS = 252


def _matrice_rendements(market_raw: pd.DataFrame, symboles: list[str]) -> pd.DataFrame:
    px = (market_raw[market_raw["symbol"].isin(symboles)]
          .pivot_table(index="date", columns="symbol", values="close")
          .sort_index())
    px = px.iloc[-(JOURS + 1):]
    px = px.dropna(axis=1, thresh=int(JOURS * 0.95)).ffill().dropna()
    return px.pct_change().dropna()


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


def markowitz_tangent(R: pd.DataFrame, poids_max: float = POIDS_MAX) -> pd.Series:
    """Poids long-only maximisant le Sharpe, plafonnés à poids_max."""
    from scipy.optimize import minimize
    from sklearn.covariance import LedoitWolf

    n = R.shape[1]
    cov = LedoitWolf().fit(R.values).covariance_ * JOURS
    mu_hist = R.mean().values * JOURS
    mu = (1 - RETRECISSEMENT) * mu_hist + RETRECISSEMENT * mu_hist.mean()

    def neg_sharpe(w):
        vol = np.sqrt(w @ cov @ w)
        return -(w @ mu - RF) / vol if vol > 0 else 0.0

    w0 = np.full(n, 1 / n)
    res = minimize(neg_sharpe, w0, method="SLSQP",
                   bounds=[(0.0, poids_max)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                   options={"maxiter": 500})
    w = res.x if res.success else w0
    return pd.Series(np.clip(w, 0, None), index=R.columns)


def _nettoyer(w: pd.Series) -> pd.Series:
    """Supprime les poussières (< POIDS_MIN) puis renormalise ; re-plafonne si besoin."""
    w = w[w >= POIDS_MIN]
    w = w / w.sum()
    for _ in range(10):  # le renormalisation peut repasser au-dessus du plafond
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
    R = _matrice_rendements(market_raw, candidats)
    if R.shape[1] < 5 or len(R) < JOURS // 2:
        return None

    w = _nettoyer(markowitz_tangent(R))
    infos = snapshot.set_index("symbol")
    lignes = []
    for sym, poids in w.items():
        r = R[sym]
        lignes.append({
            "symbol": sym,
            "nom": infos.at[sym, "nom"] if sym in infos.index else sym,
            "secteur": infos.at[sym, "secteur"] if sym in infos.index else None,
            "poids": float(poids),
            "rendement_1y": float((1 + r).prod() - 1),
            "volatilite": float(r.std() * np.sqrt(JOURS)),
        })
    secteurs = pd.Series({l["secteur"] or "Autre": 0.0 for l in lignes})
    for l in lignes:
        secteurs[l["secteur"] or "Autre"] += l["poids"]
    return {
        "lignes": lignes,
        "stats": stats_portefeuille(R, w) | {"poids_secteur_max": float(secteurs.max()),
                                             "secteur_principal": str(secteurs.idxmax())},
        "methode": (f"Markowitz (Sharpe max), {len(candidats)} candidats présélectionnés par "
                    f"momentum 12-1 ajusté du risque, plafond {int(POIDS_MAX * 100)} % par ligne, "
                    f"covariance Ledoit-Wolf, rendements rétrécis de {int(RETRECISSEMENT * 100)} % vers la moyenne."),
    }
