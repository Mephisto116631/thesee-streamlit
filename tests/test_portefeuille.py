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


def test_rendement_attendu_prudent():
    """Un titre qui a fait +60 %/an ne doit pas promettre plus de ~20 %/an (biais de sélection)."""
    rng = np.random.default_rng(1)
    jours = 756
    marche = pd.Series(rng.normal(0.0004, 0.01, jours))
    gagnant = marche * 1.2 + rng.normal(0.0, 0.01, jours)      # bêta 1,2
    gagnant = gagnant - gagnant.mean() + 0.60 / 252               # moyenne exacte : +60 %/an
    R = pd.DataFrame({"G": gagnant, "M": marche})
    mu, _ = pf.estimations(R, marche)
    assert R["G"].mean() * 252 > 0.45
    assert mu[0] < 0.20
    assert 0.06 < mu[1] < 0.12   # le marché lui-même : ~ taux sans risque + prime


def test_ingredients_coherents():
    """Les ingrédients publiés redonnent exactement les rendements attendus du serveur."""
    raw, snap = _marche(n_titres=21, jours=800)
    reco = pf.portefeuille_recommande(raw, snap)
    u = reco["univers_facteurs"]
    assert reco["univers"] is None          # anciennes versions de l'appli : frontière du serveur
    n = len(u["symbols"])
    assert len(u["mu_hist"]) == n and len(u["beta"]) == n
    assert len(u["facteurs"]) == n and len(u["idio"]) == n
    mu = [(1 - pf.POIDS_HISTORIQUE) * (pf.RF + b * pf.PRIME_RISQUE) + pf.POIDS_HISTORIQUE * h
          for b, h in zip(u["beta"], u["mu_hist"])]
    R = pf._matrice_rendements(raw, u["symbols"], pf.JOURS_ESTIMATION)
    mu_srv, _ = pf.estimations(R, None)
    assert np.allclose(mu, mu_srv, atol=1e-9)


def test_facteurs_conservent_les_variances():
    """Σ ≈ B·Bᵀ + D : variance de chaque titre exacte, covariances proches."""
    rng = np.random.default_rng(3)
    f = rng.normal(0, 0.01, (800, 3))
    R = f @ rng.normal(1, 0.5, (3, 60)) + rng.normal(0, 0.01, (800, 60))
    cov = np.cov(R.T) * 252
    B, D = pf.facteurs(cov, k=10)
    approx = B @ B.T + np.diag(D)
    assert np.allclose(np.diag(approx), np.diag(cov), rtol=1e-9)
    assert np.abs(approx - cov).max() / np.abs(cov).max() < 0.05


def test_fista_retrouve_la_variance_minimale():
    """2 titres non corrélés : poids de variance minimale ∝ 1 / variance (comme l'appli)."""
    B = np.zeros((2, 1))
    D = np.array([0.04, 0.01])
    w = pf.resoudre(B, D, np.zeros(2), 0.0, 1.0, iters=2000)
    assert abs(w[0] - 0.2) < 1e-3 and abs(w[1] - 0.8) < 1e-3


def test_candidats_tout_le_sp500_sans_etf_ni_detresse():
    raw, snap = _marche(n_titres=30, jours=800)
    snap["indice"] = ["S&P 500"] * 27 + ["ETF", "Nasdaq-100", "S&P 500"]
    snap["is_etf"] = [False] * 27 + [True, False, False]
    snap.loc[snap["symbol"] == "T29", "z_score"] = 1.0
    c = pf.candidats(raw, snap)
    assert c == [f"T{i:02d}" for i in range(27)]     # ni ETF, ni Nasdaq seul, ni détresse ; pas de limite à 40
