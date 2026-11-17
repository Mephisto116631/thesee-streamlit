"""Tests du portefeuille recommandé sur données synthétiques."""
import numpy as np
import pandas as pd

import portefeuille as pf


def _marche(n_titres=30, jours=300, seed=0):
    """Titres dont le risque et le rendement augmentent ensemble (vraie frontière)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-01", periods=jours)
    rows = []
    for i in range(n_titres):
        drift = 0.0001 + 0.00003 * i
        vol = 0.006 + 0.0007 * i
        px = 100 * np.cumprod(1 + rng.normal(drift, vol, jours))
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
    assert w.min() >= pf.POIDS_MIN - 1e-6
    assert len(w) <= pf.N_MAX_LIGNES
    assert w.max() <= pf.POIDS_MAX + 1e-6
    assert len(w) >= 5


def test_exclut_detresse():
    raw, snap = _marche()
    snap.loc[snap["symbol"] == "T29", "z_score"] = 1.0   # titre en détresse
    reco = pf.portefeuille_recommande(raw, snap)
    tous = {l["symbol"] for p in reco["frontiere"] for l in p["lignes"]} | {l["symbol"] for l in reco["lignes"]}
    assert "T29" not in tous


def test_donnees_insuffisantes():
    raw, snap = _marche(n_titres=3)
    assert pf.portefeuille_recommande(raw, snap) is None


def test_frontiere_croissante():
    raw, snap = _marche(n_titres=30, jours=800)
    reco = pf.portefeuille_recommande(raw, snap)
    f = reco["frontiere"]
    assert len(f) >= 4
    rend = [p["rendement"] for p in f]
    vol = [p["volatilite"] for p in f]
    assert rend == sorted(rend)               # plus de rentabilité visée...
    assert vol[-1] > vol[0]                   # ...coûte plus de risque
    for p in f:
        w = sum(l["poids"] for l in p["lignes"])
        assert abs(w - 1) < 1e-6
        assert max(l["poids"] for l in p["lignes"]) <= pf.POIDS_MAX + 1e-6
    assert set(reco["titres"]) >= {l["symbol"] for p in f for l in p["lignes"]}
