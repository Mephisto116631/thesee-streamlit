"""Tests du portefeuille recommandé sur données synthétiques."""
import numpy as np
import pandas as pd

import portefeuille as pf


def _marche(n_titres=30, jours=300, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-01", periods=jours)
    rows = []
    for i in range(n_titres):
        drift = 0.0002 * (i - n_titres / 2)
        px = 100 * np.cumprod(1 + rng.normal(drift, 0.015, jours))
        rows += [{"symbol": f"T{i:02d}", "date": d, "close": p} for d, p in zip(dates, px)]
    raw = pd.DataFrame(rows)
    snap = pd.DataFrame({"symbol": [f"T{i:02d}" for i in range(n_titres)],
                         "nom": "x", "secteur": ["A", "B", "C"] * (n_titres // 3), "z_score": 3.0})
    return raw, snap


def test_poids_valides():
    raw, snap = _marche()
    reco = pf.portefeuille_recommande(raw, snap)
    w = np.array([l["poids"] for l in reco["lignes"]])
    assert abs(w.sum() - 1) < 1e-6
    assert w.min() >= pf.POIDS_MIN - 1e-9
    assert w.max() <= pf.POIDS_MAX + 1e-6
    assert len(w) >= 5


def test_exclut_detresse():
    raw, snap = _marche()
    snap.loc[snap["symbol"] == "T29", "z_score"] = 1.0   # meilleur momentum mais en détresse
    reco = pf.portefeuille_recommande(raw, snap)
    assert "T29" not in [l["symbol"] for l in reco["lignes"]]


def test_donnees_insuffisantes():
    raw, snap = _marche(n_titres=3)
    assert pf.portefeuille_recommande(raw, snap) is None
