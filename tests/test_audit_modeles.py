"""Audit des quatre autres modèles (docs/METHODE.md § 4.27)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_modeles as am        # noqa: E402
import experiences                # noqa: E402
import modele_horizon as mh       # noqa: E402
import modele_regime as mreg      # noqa: E402
from test_biais import _cours     # noqa: E402


# --- F : fidélité des scores publiés -------------------------------------------------------------------------
def test_scores_publies_ne_dependent_pas_des_titres_hors_indice():
    raw, syms, compo = _cours(extra=("ETF1", "NM1"))
    _, seuls = mh.entrainer_horizon(raw[raw["symbol"].isin(syms + ["SPY"])], syms, "6m", compo)
    _, tous = mh.entrainer_horizon(raw, syms + ["ETF1", "NM1"], "6m", compo)
    a, b = seuls.set_index("symbol")["score"], tous.set_index("symbol")["score"]
    assert {"ETF1", "NM1"} <= set(b.index)
    # Les membres gardent leur ordre ; les titres hors indice sont seulement insérés parmi eux
    assert a.rank().corr(b.reindex(a.index).rank()) == pytest.approx(1.0)
    assert seuls["date"].iloc[0] == str(pd.Timestamp(raw["date"].max()).date())     # dernier jour de cours


# --- C : placebo --------------------------------------------------------------------------------------------
def test_melanger_cible_garde_les_valeurs_de_chaque_date():
    d = pd.DataFrame({"date": [1, 1, 1, 2, 2], "symbol": list("abcde"), "y": [0.1, 0.5, 0.9, 0.2, 0.8],
                      "rel": [1, 2, 3, 4, 5.0], "mom_12_1": [0.3] * 5})
    m = mh.melanger_cible(d)
    for k in (1, 2):
        assert sorted(m.loc[m["date"] == k, "y"]) == sorted(d.loc[d["date"] == k, "y"])
    assert (m[["y", "rel"]].corr().iloc[0, 1]) == pytest.approx(d[["y", "rel"]].corr().iloc[0, 1])  # y et rel restent liés
    assert list(m["mom_12_1"]) == list(d["mom_12_1"])


# --- D : biais par groupe et règle de concentration ----------------------------------------------------------
def test_alerte_concentration():
    g = {"taille": {"1 (bas)": {"ic": 0.08}, "5 (haut)": {"ic": -0.01}}}
    assert am.alerte_concentration(g, 0.03)
    assert not am.alerte_concentration({"taille": {"1 (bas)": {"ic": 0.05}, "5 (haut)": {"ic": 0.02}}}, 0.03)
    assert not am.alerte_concentration(g, -0.01)


def test_bilan_rendement_deux_comptages_et_placebo():
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2012-01-06", periods=120, freq="W-FRI")
    t = pd.DataFrame([{"date": d, "symbol": f"S{i}", "rel": rng.normal(), "liquidite": i / 40, "beta_1a": rng.random(),
                       "vol_3m": rng.random(), "secteur": "A" if i % 2 else "B"} for d in dates for i in range(40)])
    t["pred"] = t["rel"] + rng.normal(0, 3, len(t))
    ev = {"_tests": t, "ic_moyen": 0.05, "t_stat": 3.0, "n_effectif": 40}
    b = am.bilan_rendement(ev, {"ic_moyen": 0.0, "t_stat": 2.5}, {"verdict": "non probant"}, n_essais_ancien=40, n_essais_nouveau=10)
    assert "_tests" not in ev
    assert b["seuil_comptage_ancien"] > b["seuil"]                  # plus d'essais comptés : seuil plus haut
    assert b["placebo"]["fuite_suspectee"]
    assert set(b["groupes"]) == {"secteur", "taille", "beta", "volatilite_passee", "annee"}
    assert "FUITE" in am.verdict_audit_rendement(b)


def test_comptage_famille_rendement():
    tous = {("reference", "6m"), ("reference", "1a"), ("cnn", "6m"), ("examen_hybride", "6m"),
            ("risque_volatilite", "6m"), ("audit_rendement", "6m"), ("regime_logistique", "6m")}
    assert experiences.n_essais_rendement(tous) == 3
    assert experiences.n_essais_rendement_ancien(tous) == 4          # l'ancien comptait aussi examen_hybride


# --- Régime : placebo et calibration ------------------------------------------------------------------------
def _mensuel_simule(n=360, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("1995-01-31", periods=n, freq="ME")
    m = pd.DataFrame({f: rng.normal(size=n) for f in mreg.FEATURES}, index=idx)
    p = 1 / (1 + np.exp(-(2 * m["vix"] - 1.5)))                       # le VIX du mois annonce la baisse
    m["y"] = (rng.random(n) < p).astype(float)
    return m


def test_decaler_regime():
    m = _mensuel_simule()
    d = am.decaler_regime(m, 12)
    assert d["vix"].iloc[0] == pytest.approx(m["vix"].iloc[0]) and d.index[0] == m.index[12]
    assert d["y"].iloc[0] == m["y"].iloc[12]


def test_audit_regime_vrai_signal_et_placebo():
    m = _mensuel_simule()
    ev = mreg.evaluer(m, "logistique", garder_tests=True)
    evp = mreg.evaluer(am.decaler_regime(m), "logistique")
    b = am.bilan_regime(ev, evp, {"verdict": "non probant"}, n_essais=2)
    assert b["auc"] > 0.75 and b["calibration"]["gain_brier"] > 0
    assert not b["placebo"]["fuite_suspectee"]                       # un VIX d'il y a un an n'annonce rien ici
    assert len(b["calibration"]["fiabilite"]) == 5
    assert b["verdict_change"] == (b["verdict"] != "non probant")
