"""Le modèle horizon doit trouver un signal quand il existe, et n'en inventer aucun sinon."""
import numpy as np
import pandas as pd

import modele_horizon as mh


def _marche(n=80, jours=1100, persistance=True, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-01", periods=jours)
    derive = rng.normal(0, 0.0012, n) if persistance else np.zeros(n)   # tendance propre à chaque titre
    rows = []
    marche = rng.normal(0.0003, 0.008, jours)
    for i in range(n):
        r = derive[i] + marche + rng.normal(0, 0.015, jours)
        px = 100 * np.cumprod(1 + r)
        rows += [{"symbol": f"T{i:02d}", "date": d, "close": p, "volume": 1e6} for d, p in zip(dates, px)]
    spy = 100 * np.cumprod(1 + marche)
    rows += [{"symbol": "SPY", "date": d, "close": p, "volume": 1e7} for d, p in zip(dates, spy)]
    return pd.DataFrame(rows), [f"T{i:02d}" for i in range(n)]


def test_trouve_un_signal_persistant():
    raw, syms = _marche(persistance=True)
    ligne, scores = mh.entrainer_horizon(raw, syms, "6m")
    d = ligne["diagnostics"]
    assert d["ic_moyen"] > 0.05
    assert d["spread_quintiles"] > 0
    assert len(scores) == len(syms) and scores["score"].between(0, 1).all()


def test_n_invente_pas_de_signal():
    """Sur du bruit pur, le réglage choisi sur le passé ne doit pas fabriquer de signal en moyenne.
    (Un seul tirage peut donner un IC de ±0,07 sur ce petit échantillon : on teste la moyenne.)"""
    ics = []
    for seed in range(5):
        raw, syms = _marche(persistance=False, seed=seed)
        ligne, _ = mh.entrainer_horizon(raw, syms, "6m")
        assert ligne["verdict"] != "signal"
        assert ligne["diagnostics"]["config"] in mh.CONFIGS
        ics.append(ligne["diagnostics"]["ic_moyen"])
    assert abs(np.mean(ics)) < 0.04


def test_publie_le_meilleur_classement():
    """Données à tendance pure : le momentum suffit ; la source publiée doit être cohérente avec les IC."""
    raw, syms = _marche(persistance=True)
    ligne, _ = mh.entrainer_horizon(raw, syms, "6m")
    d = ligne["diagnostics"]
    ics = {"modele": d["ic_moyen"], "momentum": d["ic_momentum"], "multifacteurs": d["ic_multifacteurs"]}
    assert d["source"] == max(ics, key=ics.get)
    assert ligne["verdict"] in {"signal", "bruit", "aucun"}


def test_score_multifacteurs_borne():
    X = pd.DataFrame({"mom_12_1": [0.0, 1.0], "vol_3m": [1.0, 0.0], "dist_plus_haut": [0.0, 1.0]})
    sc = mh.score_multifacteurs(X)
    assert sc.tolist() == [0.0, 1.0]   # pire et meilleur titre sur les trois facteurs


def test_composition_historique():
    """Seuls les membres de l'indice à chaque date sont évalués, rangs recalculés entre eux."""
    raw, syms = _marche(n=80, persistance=True)
    debut_tard = pd.Timestamp("2023-01-02")
    compo = pd.DataFrame({
        "symbol": syms,
        "debut": [pd.Timestamp("2000-01-01") if i < 60 else debut_tard for i in range(len(syms))],
        "fin": [pd.NaT] * len(syms),
    })
    px, X = mh.caracteristiques(raw, syms)
    Y = mh.cible(px, pd.DatetimeIndex(X["date"].unique()), 126)
    data = X.merge(Y, on=["date", "symbol"]).dropna(subset=mh.FEATURES + ["y"])
    f = mh.membres_a_date(data, compo)
    avant = f[f["date"] < debut_tard]
    assert set(avant["symbol"]) <= set(syms[:60])                     # entrés en 2023 : absents avant
    assert set(f[f["date"] >= debut_tard]["symbol"]) - set(syms[:60])  # puis présents
    assert f.groupby("date")["y"].max().round(6).eq(1).all()          # rangs recalculés entre membres

    ligne, scores = mh.entrainer_horizon(raw, syms, "6m", compo)
    assert ligne["diagnostics"]["composition_historique"] is True
    assert len(scores) == len(syms)                                   # scores du jour : tous les titres actuels


def test_fichier_composition():
    c = mh.charger_composition()
    assert c is not None and {"symbol", "debut", "fin"} <= set(c.columns)
    assert "BRK-B" in set(c["symbol"])                                 # format Yahoo
    tsla = c[c["symbol"] == "TSLA"].iloc[0]
    assert tsla["debut"] == pd.Timestamp("2020-12-21")


def test_seuil_t_corrige():
    """Peu de périodes indépendantes ou plusieurs classements comparés : seuil plus exigeant."""
    assert mh.seuil_t(3) > mh.seuil_t(13) > mh.seuil_t(166) > 2.3      # Bonferroni sur 3 classements
    assert mh.verdict(0.14, 2.4, 2.9) == "bruit"                        # 3 périodes : jamais « signal »
    assert mh.verdict(0.09, 2.2, 13) == "bruit"                         # sous le seuil corrigé (~2,8)
    assert mh.verdict(0.09, 3.5, 13) == "signal"


def test_controles_sens_facteurs():
    raw, syms = _marche(persistance=True)
    ligne, _ = mh.entrainer_horizon(raw, syms, "6m")
    c = ligne["diagnostics"]["controles"]
    assert set(c["facteurs"]) == set(mh.FEATURES)
    for f in mh.FACTEURS_SURVEILLES:
        assert -1 <= c["facteurs"][f]["modele"] <= 1 and len(c["facteurs"][f]["quintiles"]) == 5
    # Tendance pure : le modèle doit suivre le momentum, et marcher chez les grandes comme les petites
    assert c["facteurs"]["mom_12_1"]["modele"] > 0.3
    assert c["ic_grandes"] > 0 and c["ic_petites"] > 0


def _marche_betas(n=80, jours=1300, seed=5):
    """Marché très haussier, titres de bêtas différents, aucun talent de sélection possible."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2019-01-01", periods=jours)
    marche = rng.normal(0.0012, 0.01, jours)
    betas = np.linspace(0.4, 1.6, n)
    rows = []
    for i in range(n):
        px = 100 * np.cumprod(1 + betas[i] * marche + rng.normal(0, 0.012, jours))
        rows += [{"symbol": f"T{i:02d}", "date": d, "close": p, "volume": 1e6} for d, p in zip(dates, px)]
    rows += [{"symbol": "SPY", "date": d, "close": p, "volume": 1e7}
             for d, p in zip(dates, 100 * np.cumprod(1 + marche))]
    return pd.DataFrame(rows), [f"T{i:02d}" for i in range(n)]


def test_cible_alpha_retire_le_beta():
    """Avec la cible « relatif », les bêtas élevés gagnent mécaniquement en marché haussier ;
    avec l'alpha de Jensen, cet avantage disparaît."""
    raw, syms = _marche_betas()
    rel, _ = mh.entrainer_horizon(raw, syms, "6m", cible_mode="relatif")
    alp, _ = mh.entrainer_horizon(raw, syms, "6m", cible_mode="alpha")
    beta_rel = rel["diagnostics"]["controles"]["facteurs"]["beta_1a"]["realite"]
    beta_alp = alp["diagnostics"]["controles"]["facteurs"]["beta_1a"]["realite"]
    assert beta_rel > 0.15
    assert abs(beta_alp) < beta_rel / 2
    assert alp["diagnostics"]["cible"] == "alpha"
    assert set(alp["diagnostics"]["regimes"]) == {"hausse", "baisse"}


def test_exclure_un_facteur():
    raw, syms = _marche(persistance=True)
    ligne, _ = mh.entrainer_horizon(raw, syms, "6m", exclure=["liquidite"])
    assert "liquidite" not in {x["feature"] for x in ligne["importance"]}
    assert ligne["diagnostics"]["facteurs_exclus"] == ["liquidite"]


def test_entrainement_avec_fondamentaux():
    """Les fondamentaux s'ajoutent aux facteurs ; seuls, ils remplacent ceux de cours."""
    import fondamentaux_sec as fsec
    raw, syms = _marche(persistance=True)
    faits = pd.DataFrame([
        {"symbol": s, "variable": v, "end": pd.Timestamp(f"{y}-12-31"), "filed": pd.Timestamp(f"{y + 1}-02-15"),
         "val": val}
        for i, s in enumerate(syms) for y in range(2020, 2025)
        for v, val in (("actifs", 100 + i + y), ("fonds_propres", 50 + i), ("resultat_net", 5 + i % 7),
                       ("marge_brute", 30 + i % 11), ("flux_exploitation", 6 + i % 5), ("actions", 10.0))
    ])
    ligne, scores = mh.entrainer_horizon(raw, syms, "6m", faits_sec=faits)
    d = ligne["diagnostics"]
    assert set(fsec.FEATURES_FD) <= set(d["facteurs_utilises"])
    assert d["couverture_fondamentaux"]["fd_rentabilite"] > 0.5
    seuls, _ = mh.entrainer_horizon(raw, syms, "6m", exclure=list(mh.FEATURES), faits_sec=faits)
    assert seuls["diagnostics"]["facteurs_utilises"] == fsec.FEATURES_FD
    assert len(scores) == len(syms)


def test_modele_risque_bat_la_reference():
    """Volatilité qui dépend du bêta et d'un régime persistant : le modèle doit retrouver
    le risque futur au moins aussi bien que la volatilité passée."""
    import modele_risque as mr
    rng = np.random.default_rng(7)
    n, jours = 60, 1300
    dates = pd.bdate_range("2019-01-01", periods=jours)
    marche = rng.normal(0.0003, 0.01, jours)
    rows = []
    for i in range(n):
        niveau = 0.008 + 0.02 * (i / n)                       # risque propre stable dans le temps
        px = 100 * np.cumprod(1 + (0.5 + i / n) * marche + rng.normal(0, niveau, jours))
        rows += [{"symbol": f"T{i:02d}", "date": d, "close": p, "volume": 1e6} for d, p in zip(dates, px)]
    rows += [{"symbol": "SPY", "date": d, "close": p, "volume": 1e7} for d, p in zip(dates, 100 * np.cumprod(1 + marche))]
    raw, syms = pd.DataFrame(rows), [f"T{i:02d}" for i in range(n)]
    ev = mr.entrainer_risque(raw, syms, "6m", "volatilite")
    assert ev["ic_base"] > 0.5 and ev["ic_moyen"] > 0.5          # le risque est prévisible
    assert ev["gain"] > -0.05                                     # pas pire que la référence
    dd = mr.entrainer_risque(raw, syms, "6m", "perte_max")
    assert dd["ic_moyen"] > 0.3
    vol = mr.predire_volatilite(raw, syms)
    assert len(vol) == len(syms) and vol.between(0.05, 1.0).all()
    # Le risque propre croît avec l'indice du titre : la prévision doit le retrouver
    assert vol.rank().corr(pd.Series(range(len(syms)), index=syms).rank()) > 0.7


def test_backtest_risque():
    """Risque propre qui change par régimes : le backtest tourne et compare les trois variantes."""
    import backtest_risque as bt
    rng = np.random.default_rng(11)
    n, jours = 60, 2600
    dates = pd.bdate_range("2006-01-02", periods=jours)
    marche = rng.normal(0.0003, 0.01, jours)
    rows = []
    for i in range(n):
        niveau = np.repeat(rng.uniform(0.005, 0.03, jours // 250 + 1), 250)[:jours]   # régimes annuels
        px = 100 * np.cumprod(1 + (0.5 + i / n) * marche + rng.normal(0, 1, jours) * niveau)
        rows += [{"symbol": f"T{i:02d}", "date": d, "close": p, "volume": 1e6} for d, p in zip(dates, px)]
    rows += [{"symbol": "SPY", "date": d, "close": p, "volume": 1e7} for d, p in zip(dates, 100 * np.cumprod(1 + marche))]
    raw, syms = pd.DataFrame(rows), [f"T{i:02d}" for i in range(n)]
    res = bt.backtest(raw, syms, None, debut="2012-01-01", pas_semaines=8)
    pfs = res[res["portefeuille"] != "indice"]
    assert set(pfs["variante"]) == set(bt.VARIANTES) and set(pfs["portefeuille"]) == set(bt.PORTEFEUILLES)
    assert (res["portefeuille"] == "indice").any()                    # l'indice sert de repère
    r = bt.resume(res)
    for nom_pf in bt.PORTEFEUILLES:
        assert r[nom_pf]["n_mois"] >= 5
        assert "ia_vs_hist_3a" in r[nom_pf]
        assert all(0 < v["vol_reelle"] < 1 for v in r[nom_pf]["variantes"].values())

    # Base large (tous les titres) contre ancienne base (40 meilleurs au momentum), même moteur
    secteurs = {s: "AB"[i % 2] for i, s in enumerate(syms)}
    res2 = bt.backtest(raw, syms, None, debut="2012-01-01", pas_semaines=8, base=bt.BASES,
                       variantes=["hist_3a"], secteurs=secteurs)
    assert set(res2["base"]) == {"sp500", "momentum40"}
    c = bt.comparer_bases(res2, "sharpe_max", "hist_3a")
    assert c["sp500"]["n_mois"] == c["momentum40"]["n_mois"] >= 5
    assert 0 < c["sp500"]["volatilite"] < 1 and "indice" in c and "t" in c["ecart"]
    assert 0.5 <= c["sp500"]["poids_secteur_max"] <= 1


def test_risque_avec_comptes():
    """Les comptes publiés s'ajoutent aux facteurs du modèle de risque, sans fuite du futur."""
    import fondamentaux_sec as fsec
    import modele_risque as mr
    raw, syms = _marche(persistance=True)
    faits = pd.DataFrame([
        {"symbol": s, "variable": v, "end": pd.Timestamp(f"{y}-12-31"), "filed": pd.Timestamp(f"{y + 1}-02-15"), "val": val}
        for i, s in enumerate(syms) for y in range(2020, 2025)
        for v, val in (("actifs", 100.0), ("fonds_propres", 20 + i), ("resultat_net", 5.0),
                       ("marge_brute", 30.0), ("flux_exploitation", 6.0), ("actions", 10.0))
    ])
    ev = mr.entrainer_risque(raw, syms, "6m", "perte_max", faits_sec=faits)
    assert "fd_levier" in ev["facteurs_utilises"] and ev["couverture_fondamentaux"]["fd_levier"] > 0.5
    assert set(fsec.FEATURES_FD) <= {x["feature"] for x in ev["importance"]}
    assert "controles" in ev


def test_ensemble():
    """L'ensemble trouve le signal planté et rapporte des importances qui somment à 1."""
    raw, syms = _marche(persistance=True)
    ligne, scores = mh.entrainer_horizon(raw, syms, "6m", forcer_config="ensemble")
    d = ligne["diagnostics"]
    assert d["config"] == "ensemble" and all(f["config"] == "ensemble" for f in d["fenetres"])
    assert d["ic_moyen"] > 0.05
    assert abs(sum(x["importance"] for x in ligne["importance"]) - 1) < 1e-6
