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
    raw, syms = _marche(persistance=False, seed=3)
    ligne, _ = mh.entrainer_horizon(raw, syms, "6m")
    assert ligne["verdict"] != "signal"
    assert abs(ligne["diagnostics"]["ic_moyen"]) < 0.06


def test_publie_le_meilleur_classement():
    """Données à tendance pure : le momentum suffit ; la source publiée doit être cohérente avec les IC."""
    raw, syms = _marche(persistance=True)
    ligne, _ = mh.entrainer_horizon(raw, syms, "6m")
    d = ligne["diagnostics"]
    attendu = "momentum" if d["ic_momentum"] > d["ic_moyen"] else "modele"
    assert d["source"] == attendu
    assert ligne["verdict"] in {"signal", "bruit", "aucun"}
