# modele_horizon.py
# ==============================================================================
# MODÈLE IA « HORIZON » : classer les titres selon leur performance attendue
# PAR RAPPORT AU MARCHÉ sur 1 mois, 6 mois ou 1 an.
# ==============================================================================
# Pourquoi pas « hausse ou baisse demain » ? À 1 jour, les cours sont proches du
# hasard (le modèle précédent faisait ~50 %). Pour un placement à 6-12 mois, la
# bonne question est : « parmi ces titres, lesquels feront MIEUX que les autres ? ».
#
# Méthode
#   - Caractéristiques (calculées chaque semaine, pour chaque titre) : momentum
#     12-1 et 6-1 mois, retournement 1 mois, volatilité 3 mois, écart à la MM200,
#     RSI 14, distance au plus haut 1 an, bêta 1 an vs SPY, tendance du volume.
#     Chacune est transformée en RANG du jour (0 = plus faible, 1 = plus fort) :
#     le modèle compare les titres entre eux, il ne prédit pas le marché.
#   - Cible : rang du rendement futur sur H jours, relatif aux autres titres.
#   - Modèle : XGBoost (régression), volontairement peu profond (régularisé).
#   - Évaluation honnête : validation « walk-forward » (entraîné sur le passé,
#     testé sur la période suivante) avec un embargo de H jours entre les deux,
#     sinon les cibles qui se chevauchent font croire à un faux signal.
#   - Mesures : IC (corrélation de rang entre prédiction et réalité, par date),
#     écart de rendement entre le 1er et le dernier quintile, et comparaison
#     avec la règle simple « momentum 12-1 » : si le modèle ne fait pas mieux,
#     il n'apporte rien.
# ==============================================================================
import numpy as np
import pandas as pd

HORIZONS = {"court": 21, "6m": 126, "1a": 252}
PAS_ECHANTILLON = 5          # une observation par titre et par semaine
N_FENETRES = 4               # nombre de périodes de test (walk-forward)
INDICE = "SPY"
FEATURES = ["mom_12_1", "mom_6_1", "rev_1m", "vol_3m", "ecart_mm200",
            "rsi_14", "dist_plus_haut", "beta_1a", "tendance_volume"]
LABELS = {
    "mom_12_1": "Momentum 12 mois (hors dernier mois)",
    "mom_6_1": "Momentum 6 mois (hors dernier mois)",
    "rev_1m": "Performance du dernier mois",
    "vol_3m": "Volatilité 3 mois",
    "ecart_mm200": "Écart à la moyenne 200 j",
    "rsi_14": "RSI 14 j",
    "dist_plus_haut": "Distance au plus haut 1 an",
    "beta_1a": "Bêta 1 an (sensibilité au marché)",
    "tendance_volume": "Volume récent vs habituel",
}


def _rsi(px: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    d = px.diff()
    up = d.clip(lower=0).ewm(com=n - 1, adjust=False).mean()
    down = (-d.clip(upper=0)).ewm(com=n - 1, adjust=False).mean()
    return 100 - 100 / (1 + up / down.replace(0, np.nan))


def caracteristiques(market_raw: pd.DataFrame, symboles: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retourne (tableau large des cours, caractéristiques empilées par date et titre)."""
    m = market_raw[market_raw["symbol"].isin(set(symboles) | {INDICE})]
    px = m.pivot_table(index="date", columns="symbol", values="close").sort_index().ffill(limit=5)
    vol = m.pivot_table(index="date", columns="symbol", values="volume").sort_index().reindex(px.index)
    ret = px.pct_change()

    f = {
        "mom_12_1": px.shift(21) / px.shift(252) - 1,
        "mom_6_1": px.shift(21) / px.shift(126) - 1,
        "rev_1m": px / px.shift(21) - 1,
        "vol_3m": ret.rolling(63).std() * np.sqrt(252),
        "ecart_mm200": px / px.rolling(200).mean() - 1,
        "rsi_14": _rsi(px),
        "dist_plus_haut": px / px.rolling(252).max() - 1,
        "tendance_volume": vol.rolling(20).mean() / vol.rolling(120).mean(),
    }
    if INDICE in ret.columns:
        rm = ret[INDICE]
        f["beta_1a"] = ret.rolling(252).cov(rm).div(rm.rolling(252).var(), axis=0)
    else:
        f["beta_1a"] = ret * np.nan

    dates = px.index[252::PAS_ECHANTILLON]
    cols = [c for c in px.columns if c != INDICE and c in symboles]
    blocs = []
    for nom, tab in f.items():
        t = tab.reindex(index=dates, columns=cols)
        blocs.append(t.rank(axis=1, pct=True).stack(future_stack=True).rename(nom))  # rang du jour
    X = pd.concat(blocs, axis=1)
    X.index.names = ["date", "symbol"]
    return px[cols], X.reset_index()


def cible(px: pd.DataFrame, dates: pd.Index, h: int) -> pd.DataFrame:
    """Rendement futur sur h jours, relatif à la médiane du jour, et son rang."""
    fut = (px.shift(-h) / px - 1).reindex(dates)
    rel = fut.sub(fut.median(axis=1), axis=0)
    out = pd.concat([rel.stack(future_stack=True).rename("rel"),
                     rel.rank(axis=1, pct=True).stack(future_stack=True).rename("y")], axis=1)
    out.index.names = ["date", "symbol"]
    return out.reset_index()


def _modele():
    from xgboost import XGBRegressor
    return XGBRegressor(n_estimators=200, max_depth=3, learning_rate=0.05, subsample=0.8,
                        colsample_bytree=0.8, min_child_weight=50, reg_lambda=5.0, random_state=42)


def _ic_par_date(df: pd.DataFrame, col: str) -> pd.Series:
    """Corrélation de rang (Spearman) entre `col` et le rendement relatif réalisé, date par date."""
    return df.groupby("date").apply(lambda g: g[col].rank().corr(g["rel"].rank()) if len(g) > 10 else np.nan,
                                    include_groups=False).dropna()


def evaluer(data: pd.DataFrame, h: int) -> dict:
    """Walk-forward avec embargo de h jours entre entraînement et test."""
    dates = np.sort(data["date"].unique())
    if len(dates) < 60:
        return {}
    bornes = np.array_split(dates[len(dates) // 3:], N_FENETRES)  # 1er tiers : entraînement initial
    embargo = pd.Timedelta(days=int(h * 7 / 5) + 1)                  # h jours de bourse ≈ h·7/5 jours
    tests, fenetres = [], []
    for bloc in bornes:
        debut = pd.Timestamp(bloc[0])
        train = data[data["date"] < debut - embargo]
        test = data[data["date"].isin(bloc)].copy()
        if len(train) < 2000 or test.empty:
            continue
        m = _modele().fit(train[FEATURES], train["y"])
        test["pred"] = m.predict(test[FEATURES])
        ic = _ic_par_date(test, "pred")
        fenetres.append({"debut": str(debut.date()), "fin": str(pd.Timestamp(bloc[-1]).date()),
                         "ic": float(ic.mean()) if len(ic) else None, "n_dates": int(len(ic))})
        tests.append(test)
    if not tests:
        return {}
    t = pd.concat(tests)
    ic = _ic_par_date(t, "pred")
    ic_mom = _ic_par_date(t, "mom_12_1")
    # Les dates se chevauchent (cible sur h jours, une date par semaine) :
    # nombre effectif d'observations indépendantes ≈ n_dates / (h / 5).
    n_eff = max(1.0, len(ic) / max(1.0, h / PAS_ECHANTILLON))
    t_stat = float(ic.mean() / ic.std() * np.sqrt(n_eff)) if ic.std() > 0 else 0.0
    t["quintile"] = t.groupby("date")["pred"].transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False))
    q = t.groupby("quintile")["rel"].mean()
    haut_bat_mediane = t[t["quintile"] == 4].groupby("date")["rel"].mean()
    return {
        "horizon_jours": h,
        "ic_moyen": float(ic.mean()), "ic_ecart_type": float(ic.std()), "t_stat": t_stat,
        "ic_momentum": float(ic_mom.mean()) if len(ic_mom) else None,
        "spread_quintiles": float(q.get(4, np.nan) - q.get(0, np.nan)),   # rendement relatif Q5 - Q1 sur h jours
        "rendement_par_quintile": [float(q.get(i, np.nan)) for i in range(5)],
        "taux_reussite_top": float((haut_bat_mediane > 0).mean()) if len(haut_bat_mediane) else None,
        "n_dates_test": int(len(ic)), "n_effectif": float(n_eff),
        "fenetres": fenetres,
    }


def verdict(ev: dict) -> str:
    """signal : IC > 0,03, statistiquement net (t > 2) et meilleur que le momentum seul."""
    if not ev:
        return "aucun"
    ic, t, mom = ev["ic_moyen"], ev["t_stat"], ev.get("ic_momentum") or 0.0
    if ic > 0.03 and t > 2 and ic > mom:
        return "signal"
    if ic > 0.01:
        return "bruit"
    return "aucun"


def entrainer_horizon(market_raw: pd.DataFrame, symboles: list[str], nom: str) -> tuple[dict, pd.DataFrame]:
    """Évalue puis entraîne le modèle final ; retourne (ligne model_runs, scores du jour)."""
    h = HORIZONS[nom]
    px, X = caracteristiques(market_raw, symboles)
    if X.empty:
        return {}, pd.DataFrame()
    Y = cible(px, pd.DatetimeIndex(X["date"].unique()), h)
    data = X.merge(Y, on=["date", "symbol"]).dropna(subset=FEATURES + ["y"])
    ev = evaluer(data, h)
    if data.empty:
        return {}, pd.DataFrame()
    m = _modele().fit(data[FEATURES], data["y"])

    derniere = X["date"].max()
    aujourd_hui = X[X["date"] == derniere].dropna(subset=FEATURES).copy()
    aujourd_hui["pred"] = m.predict(aujourd_hui[FEATURES])
    aujourd_hui["score"] = aujourd_hui["pred"].rank(pct=True)
    scores = aujourd_hui[["symbol", "score"]].assign(horizon=nom, date=str(pd.Timestamp(derniere).date()))

    imp = sorted([{"feature": f, "label": LABELS[f], "importance": float(v)}
                  for f, v in zip(FEATURES, m.feature_importances_)], key=lambda d: -d["importance"])
    ic = ev.get("ic_moyen")
    ligne = {
        "kind": f"horizon_{nom}",
        "trained_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "accuracy": ev.get("taux_reussite_top", 0) * 100 if ev.get("taux_reussite_top") is not None else None,
        "baseline": 50.0,
        "gain_pts": ic * 100 if ic is not None else None,   # IC en points (ex. 3,5 = IC 0,035)
        "verdict": verdict(ev),
        "importance": imp,
        "diagnostics": ev,
    }
    return ligne, scores
