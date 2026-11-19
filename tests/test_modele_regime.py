"""Régime de marché : un signal planté doit être trouvé, du bruit ne doit rien donner."""
import numpy as np
import pandas as pd

import modele_regime as mr


def _marche(signal: bool, seed=1, jours=6500):
    """S&P 500 simulé ; si signal, les baisses arrivent quand un « stress » (VIX, crédit) monte d'abord."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("1995-01-02", periods=jours)
    stress = np.zeros(jours)
    for k in range(1, jours):                       # stress persistant (régimes)
        stress[k] = 0.995 * stress[k - 1] + rng.normal(0, 0.1)
    # Avec signal : quand le stress dépasse 1, le marché glisse dans les semaines qui suivent
    derive = 0.0004 - (0.008 * np.maximum(np.roll(stress, 10) - 0.8, 0) if signal else 0.0)
    ret = derive + rng.normal(0, 0.007, jours)
    spx = 100 * np.cumprod(1 + ret)
    bruit = rng.normal(0, 1, jours)
    d = pd.DataFrame({"spx": spx,
                      "vix": 15 + 5 * (stress if signal else bruit) + rng.normal(0, 1, jours),
                      "credit": 2 + 0.5 * (stress if signal else bruit) + rng.normal(0, 0.1, jours),
                      "pente": rng.normal(1, 0.5, jours)}, index=dates)
    return d


def test_trouve_un_signal_plante():
    d = _marche(True, seed=4)
    m = mr.mensuel(mr.caracteristiques(d), mr.cible(d))
    ev = mr.evaluer(m, "logistique")
    assert ev["auc"] > 0.65 and ev["gain_logloss"] > 0
    expl = mr.explication(m, "logistique")
    assert expl[0]["feature"] in {"vix", "credit", "vix_vs_1a", "credit_3m", "vol_3m"}


def test_n_invente_rien_sur_du_bruit():
    d = _marche(False, seed=4)
    m = mr.mensuel(mr.caracteristiques(d), mr.cible(d))
    ev = mr.evaluer(m, "logistique")
    assert ev["auc"] < 0.65
    p = mr.probabilite_du_jour(d)
    assert 0 <= p["proba"] <= 1
