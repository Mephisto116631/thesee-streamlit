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

import fondamentaux_sec as fsec
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
        "controles": mh.sens_facteurs(t, feats),
        "horizon_jours": h, "ic_moyen": float(ic_m.mean()), "ic_base": float(ic_b.mean()),
        "gain": float(gain.mean()), "t_stat": t_gain, "n_effectif": float(n_eff),
        "part_dates_gagnantes": float((gain > 0).mean()), "fenetres": fenetres,
        "debut_test": str(pd.Timestamp(t["date"].min()).date()),
    }


def entrainer_risque(market_raw: pd.DataFrame, symboles: list[str], nom: str, genre: str,
                     composition: pd.DataFrame | None = None, faits_sec: pd.DataFrame | None = None,
                     splits: pd.DataFrame | None = None) -> dict:
    """Évalue l'IA de risque. Avec `faits_sec` : ajoute les comptes publiés des entreprises
    (endettement, rentabilité, accruals, émissions…) aux facteurs de cours."""
    h = mh.HORIZONS[nom]
    px, X = mh.caracteristiques(market_raw, symboles)
    if X.empty:
        return {}
    feats = list(mh.FEATURES)
    couverture = None
    if faits_sec is not None:
        fd = fsec.caracteristiques_fondamentales(faits_sec, px, splits, pd.DatetimeIndex(X["date"].unique()))
        couverture = {f: float(fd[f].notna().mean()) for f in fsec.FEATURES_FD}
        for f in fsec.FEATURES_FD:
            fd[f] = fd.groupby("date")[f].rank(pct=True).fillna(0.5)
        fd["date"] = fd["date"].astype(X["date"].dtype)
        X = X.merge(fd, on=["date", "symbol"], how="left")
        X[fsec.FEATURES_FD] = X[fsec.FEATURES_FD].fillna(0.5)
        feats += fsec.FEATURES_FD
    Y = cible_risque(px, pd.DatetimeIndex(X["date"].unique()), h, genre)
    data = X.merge(Y, on=["date", "symbol"]).dropna(subset=mh.FEATURES + ["y"])
    if composition is not None:
        filtre = mh.membres_a_date(data, composition, False, feats)
        if not filtre.empty:
            data = filtre
    ev = evaluer_risque(data, h, feats)
    if not ev:
        return {}
    config, _ = mh.choisir_config(data, h, feats)
    m = mh._modele(config).fit(data[feats], data["y"])
    ev["config"] = config
    ev["cible"] = genre
    ev["facteurs_utilises"] = feats
    if couverture is not None:
        ev["couverture_fondamentaux"] = couverture
    ev["importance"] = sorted([{"feature": f, "label": mh.LABELS[f], "importance": float(v)}
                               for f, v in zip(feats, mh._importances(m, config))],
                              key=lambda d: -d["importance"])
    return ev


def predire_volatilite(market_raw: pd.DataFrame, symboles: list[str], composition: pd.DataFrame | None = None,
                       nom: str = "6m", niveaux: str = "vol_3m") -> pd.Series:
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
    if niveaux in ("har", "har_seul"):
        lvl = niveaux_har_du_jour(px, data, auj.index)
        if niveaux == "har_seul":
            return lvl.reindex(auj.index)
        base = np.sort(lvl.reindex(auj.index).dropna().values)   # hybride : ordre de l'IA, niveaux HAR
    else:
        vol_3m = px.pct_change().iloc[-63:].std() * np.sqrt(252)
        base = np.sort(vol_3m.reindex(auj.index).dropna().values)
    return pd.Series(np.quantile(base, rang.values), index=rang.index)


def niveaux_har_du_jour(px: pd.DataFrame, data: pd.DataFrame, symboles) -> pd.Series:
    """Volatilité prévue par HAR (Corsi) à la dernière date, régression ajustée sur toutes les dates
    dont la volatilité future est déjà connue (`data` contient la cible réalisée `brut`)."""
    import examen_risque as ex
    entrees = ex.har_entrees(px.pct_change())
    lignes = []
    for nom_e, t in entrees.items():
        st = t.reindex(pd.DatetimeIndex(data["date"].unique())).stack(future_stack=True).rename(nom_e)
        st.index.names = ["date", "symbol"]
        lignes.append(st)
    hist = data[["date", "symbol", "brut"]].merge(pd.concat(lignes, axis=1).reset_index(), on=["date", "symbol"]).dropna()
    coef = ex.har_ajuster(hist)
    auj = pd.DataFrame({k: t.iloc[-1] for k, t in entrees.items()}).reindex(list(symboles))
    return pd.Series(ex.har_prevoir(auj, coef), index=auj.index)


# ------------------------------------------------------------------------------
# PREUVE CONTINUE : verdict du laboratoire et bilan en conditions réelles
# ------------------------------------------------------------------------------
JOURS_SUIVI = 126            # 6 mois de bourse : délai avant de pouvoir juger une prévision
NOM_LABO = "risque_volatilite"


def verdict_labo(lignes: list[dict]) -> dict:
    """Dernier verdict du laboratoire pour l'IA de volatilité à 6 mois (le plus récent fait foi).
    `lignes` : lignes de la table `experiences`. Sans essai : non probant (prudence)."""
    l6 = [r for r in lignes or [] if r.get("nom") == NOM_LABO and r.get("horizon") == "6m"]
    if not l6:
        return {"probant": False, "verdict": "jamais testé"}
    r = max(l6, key=lambda r: str(r.get("cree_le") or ""))
    d = r.get("diagnostics") or {}
    return {"probant": r.get("verdict") == "probant", "verdict": r.get("verdict"),
            "t_stat": r.get("t_stat"), "seuil": r.get("seuil_t_global"), "date": r.get("cree_le"),
            "ic": d.get("ic_moyen"), "ic_base": d.get("ic_base"), "gain": d.get("gain"),
            "part_dates_gagnantes": d.get("part_dates_gagnantes")}


def bilan_reel(suivi: pd.DataFrame, px: pd.DataFrame, premiere=None, h: int = JOURS_SUIVI) -> dict:
    """Compare les prévisions ENREGISTRÉES (table suivi_volatilite : date, symbol, vol_prevue,
    vol_3m) à la volatilité RÉELLEMENT observée pendant les `h` séances suivantes.
    Aucune donnée de test n'a servi à entraîner : c'est la preuve la plus forte.
    `px` : cours de clôture (dates × symboles)."""
    out = {"n_dates": 0}
    if premiere is None and suivi is not None and not suivi.empty:
        premiere = pd.to_datetime(suivi["date"]).min()
    if premiere is not None:
        out["premiere_prevision"] = str(pd.Timestamp(premiere).date())
        # Premier bilan possible : h séances (~6 mois) après la première prévision
        out["premier_bilan"] = str((pd.Timestamp(premiere) + pd.tseries.offsets.BDay(h)).date())
    if suivi is None or suivi.empty:
        return out
    s = suivi.copy()
    s["date"] = pd.to_datetime(s["date"])
    dates = np.sort(s["date"].unique())
    if px is None or px.empty:
        return out
    px = px.sort_index()
    reel = cible_risque(px, pd.DatetimeIndex([d for d in dates if d in px.index]), h, "volatilite")
    if reel.empty:
        return out
    t = s.merge(reel[["date", "symbol", "rel"]], on=["date", "symbol"]).dropna(subset=["vol_prevue", "vol_3m", "rel"])
    if t.empty:
        return out
    ic_ia = mh._ic_par_date(t, "vol_prevue")
    ic_ref = mh._ic_par_date(t, "vol_3m")
    gain = (ic_ia - ic_ref).dropna()
    if gain.empty:
        return out
    # Prévisions hebdomadaires, horizon de 6 mois : elles se chevauchent -> périodes indépendantes
    n_eff = max(1.0, len(gain) * 5 / h)
    t_gain = float(gain.mean() / gain.std() * np.sqrt(n_eff)) if len(gain) > 1 and gain.std() > 0 else 0.0
    seuil = mh.seuil_t(n_eff, n_candidats=1)
    if n_eff < mh.MIN_PERIODES_SIGNAL:
        verdict = "pas encore assez de recul"
    elif gain.mean() > GAIN_MIN and t_gain > seuil:
        verdict = "probant"
    else:
        verdict = "non probant"
    out.update({"n_dates": int(len(gain)), "n_effectif": n_eff, "ic_ia": float(ic_ia.mean()),
                "ic_reference": float(ic_ref.mean()), "gain": float(gain.mean()), "t_stat": t_gain,
                "seuil": seuil, "part_dates_gagnantes": float((gain > 0).mean()), "verdict": verdict,
                "derniere_date_jugee": str(pd.Timestamp(gain.index.max()).date())})
    return out
