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
