# modele_risque.py
# ==============================================================================
# MODÈLE IA DE RISQUE : prédire quels titres seront les plus AGITÉS (volatilité)
# ou subiront la plus forte PERTE MAXIMALE sur 6 mois / 1 an.
#
# Pourquoi : le rendement est presque imprévisible, le risque beaucoup moins (un
# titre agité le reste souvent). Mais la volatilité passée prédit DÉJÀ très bien
# la volatilité future : le modèle n'a de valeur que s'il fait MIEUX que cette
# référence naïve. C'est ce gain (IC du modèle − IC de la référence) qui est testé.
#
# Même protocole honnête que modele_horizon : walk-forward avec embargo, réglage
# choisi sur le passé seulement, seuls les membres du S&P 500 à chaque date.
# ==============================================================================
import numpy as np
import pandas as pd

import modele_horizon as mh

CIBLES_RISQUE = {
    "volatilite": "volatilité réalisée sur l'horizon (écart-type des rendements quotidiens, annualisé)",
    "perte_max": "perte maximale sur l'horizon (plus forte baisse depuis un sommet, en valeur absolue)",
}
REFERENCE = "vol_3m"         # référence naïve : la volatilité des 3 derniers mois
GAIN_MIN = 0.02              # gain d'IC minimal pour parler d'apport utile


def cible_risque(px: pd.DataFrame, dates: pd.Index, h: int, genre: str) -> pd.DataFrame:
    """Risque FUTUR (jours t+1 à t+h) pour chaque date d'échantillon : brut = plus haut = plus risqué."""
    ret = px.pct_change()
    pos = {d: i for i, d in enumerate(px.index)}
    lignes = {}
    for d in dates:
        i = pos.get(d)
        if i is None or i + h >= len(px):
            continue
        if genre == "volatilite":
            fen = ret.iloc[i + 1:i + h + 1]
            v = fen.std() * np.sqrt(252)
            v[fen.notna().sum() < h * 0.8] = np.nan
        else:
            fen = px.iloc[i:i + h + 1]
            v = -(fen / fen.cummax() - 1).min()
            v[fen.notna().sum() < h * 0.8] = np.nan
        lignes[d] = v
    brut = pd.DataFrame(lignes).T
    out = brut.stack(future_stack=True).rename("brut").to_frame()
    out.index.names = ["date", "symbol"]
    return mh._relatif(out.reset_index(), par_secteur=False)


def evaluer_risque(data: pd.DataFrame, h: int, feats: list[str] | None = None) -> dict:
    """Walk-forward : IC du modèle et IC de la référence sur les MÊMES dates, et leur écart."""
    feats = feats or mh.FEATURES
    dates = np.sort(data["date"].unique())
    if len(dates) < 60:
        return {}
    bornes = np.array_split(dates[len(dates) // 3:], mh.N_FENETRES)
    embargo = pd.Timedelta(days=int(h * 7 / 5) + 1)
    tests, fenetres = [], []
    for bloc in bornes:
        debut = pd.Timestamp(bloc[0])
        train = data[data["date"] < debut - embargo]
        test = data[data["date"].isin(bloc)].copy()
        if len(train) < 2000 or test.empty:
            continue
        config, _ = mh.choisir_config(train, h, feats)
        test["pred"] = mh._modele(config).fit(train[feats], train["y"]).predict(test[feats])
        ic_m, ic_b = mh._ic_par_date(test, "pred"), mh._ic_par_date(test, REFERENCE)
        fenetres.append({"debut": str(debut.date()), "fin": str(pd.Timestamp(bloc[-1]).date()),
                         "ic": float(ic_m.mean()), "ic_base": float(ic_b.mean()), "config": config})
        tests.append(test)
    if not tests:
        return {}
    t = pd.concat(tests)
    ic_m = mh._ic_par_date(t, "pred")
    ic_b = mh._ic_par_date(t, REFERENCE)
    gain = (ic_m - ic_b).dropna()
    n_eff = max(1.0, len(gain) / max(1.0, h / mh.PAS_ECHANTILLON))
    t_gain = float(gain.mean() / gain.std() * np.sqrt(n_eff)) if gain.std() > 0 else 0.0
    return {
        "horizon_jours": h, "ic_moyen": float(ic_m.mean()), "ic_base": float(ic_b.mean()),
        "gain": float(gain.mean()), "t_stat": t_gain, "n_effectif": float(n_eff),
        "part_dates_gagnantes": float((gain > 0).mean()), "fenetres": fenetres,
        "debut_test": str(pd.Timestamp(t["date"].min()).date()),
    }


def entrainer_risque(market_raw: pd.DataFrame, symboles: list[str], nom: str, genre: str,
                     composition: pd.DataFrame | None = None) -> dict:
    h = mh.HORIZONS[nom]
    px, X = mh.caracteristiques(market_raw, symboles)
    if X.empty:
        return {}
    Y = cible_risque(px, pd.DatetimeIndex(X["date"].unique()), h, genre)
    data = X.merge(Y, on=["date", "symbol"]).dropna(subset=mh.FEATURES + ["y"])
    if composition is not None:
        filtre = mh.membres_a_date(data, composition)
        if not filtre.empty:
            data = filtre
    ev = evaluer_risque(data, h)
    if not ev:
        return {}
    config, _ = mh.choisir_config(data, h)
    m = mh._modele(config).fit(data[mh.FEATURES], data["y"])
    ev["config"] = config
    ev["cible"] = genre
    ev["importance"] = sorted([{"feature": f, "label": mh.LABELS[f], "importance": float(v)}
                               for f, v in zip(mh.FEATURES, mh._importances(m, config))],
                              key=lambda d: -d["importance"])
    return ev


def predire_volatilite(market_raw: pd.DataFrame, symboles: list[str], composition: pd.DataFrame | None = None,
                       nom: str = "6m") -> pd.Series:
    """Volatilité annuelle PRÉVUE par l'IA pour chaque titre, à la dernière date connue.
    Le modèle classe les titres ; le rang prédit est converti en niveau avec la distribution
    actuelle des volatilités 3 mois (même méthode que le backtest, validée sur 2013-2026)."""
    h = mh.HORIZONS[nom]
    px, X = mh.caracteristiques(market_raw, symboles)
    if X.empty:
        return pd.Series(dtype=float)
    Y = cible_risque(px, pd.DatetimeIndex(X["date"].unique()), h, "volatilite")
    data = X.merge(Y, on=["date", "symbol"]).dropna(subset=mh.FEATURES + ["y"])
    if composition is not None:
        filtre = mh.membres_a_date(data, composition)
        if not filtre.empty:
            data = filtre
    config, _ = mh.choisir_config(data, h)
    m = mh._modele(config).fit(data[mh.FEATURES], data["y"])
    derniere = X["date"].max()
    auj = X[X["date"] == derniere].dropna(subset=mh.FEATURES).set_index("symbol")
    rang = pd.Series(m.predict(auj[mh.FEATURES]), index=auj.index).rank(pct=True)
    vol_3m = px.pct_change().iloc[-63:].std() * np.sqrt(252)
    niveaux = np.sort(vol_3m.reindex(auj.index).dropna().values)
    return pd.Series(np.quantile(niveaux, rang.values), index=rang.index)
