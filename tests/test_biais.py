"""Fidélité laboratoire / production (METHODE § 4.20) et audit des biais (§ 4.21)."""
import numpy as np
import pandas as pd
import pytest

import examen_risque as ex
import modele_horizon as mh
import modele_risque as mr


def _cours(n=60, jours=1300, seed=7, extra=()):
    """Actions dont le risque propre croît avec leur numéro, plus des titres « extra » (ETF calme, action hors indice agitée)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2019-01-01", periods=jours)
    marche = rng.normal(0.0003, 0.01, jours)
    rows = []
    for i in range(n):
        px = 100 * np.cumprod(1 + (0.5 + i / n) * marche + rng.normal(0, 0.008 + 0.02 * i / n, jours))
        rows += [{"symbol": f"T{i:02d}", "date": d, "close": p, "volume": 1e6} for d, p in zip(dates, px)]
    bruit = {"ETF1": 0.001, "NM1": 0.04}
    for s in extra:
        px = 100 * np.cumprod(1 + marche + rng.normal(0, bruit[s], jours))
        rows += [{"symbol": s, "date": d, "close": p, "volume": 1e6} for d, p in zip(dates, px)]
    rows += [{"symbol": "SPY", "date": d, "close": p, "volume": 1e7} for d, p in zip(dates, 100 * np.cumprod(1 + marche))]
    syms = [f"T{i:02d}" for i in range(n)]
    compo = pd.DataFrame({"symbol": syms, "debut": pd.Timestamp("2000-01-01"), "fin": pd.NaT})
    return pd.DataFrame(rows), syms, compo


# --- § 4.20 : fidélité ----------------------------------------------------------------------------------
def test_rangs_parmi_membres():
    auj = pd.DataFrame({"f": [0.1, 0.5, 0.9, 0.3, 0.95]}, index=["A", "B", "C", "ETF", "X"])
    out = mr.rangs_parmi_membres(auj, pd.Index(["A", "B", "C"]), ["f"])
    assert list(out.loc[["A", "B", "C"], "f"]) == pytest.approx([1 / 3, 2 / 3, 1.0])     # rangs parmi les membres
    assert out.loc["ETF", "f"] == pytest.approx(1 / 3)        # 0,3 : au-dessus d'un seul membre sur trois
    assert out.loc["X", "f"] == pytest.approx(1.0)


def test_membres_du_jour():
    compo = pd.DataFrame({"symbol": ["A", "B", "C"], "debut": pd.to_datetime(["2000-01-01", "2020-01-01", "2000-01-01"]),
                          "fin": pd.to_datetime([None, None, "2010-01-01"])})
    assert set(mr.membres_du_jour(compo, "2015-06-01", ["A", "B", "C", "D"])) == {"A"}
    assert set(mr.membres_du_jour(None, "2015-06-01", ["A", "D"])) == {"A", "D"}


def test_caracteristiques_au_dernier_jour():
    raw, syms, _ = _cours(n=12, jours=600)
    px, X = mh.caracteristiques(raw, syms, derniere_date=True)
    assert X["date"].max() == px.index[-1]
    _, X2 = mh.caracteristiques(raw, syms)
    assert set(X2["date"]) <= set(X["date"])                  # le laboratoire garde ses dates


@pytest.mark.parametrize("niveaux", ["vol_3m", "har"])
def test_un_etf_ou_une_action_hors_indice_ne_deplace_pas_les_membres(niveaux):
    raw, syms, compo = _cours(extra=("ETF1", "NM1"))
    seuls = mr.predire_volatilite(raw[raw["symbol"].isin(syms + ["SPY"])], syms, compo, niveaux=niveaux)
    tous = mr.predire_volatilite(raw, syms + ["ETF1", "NM1"], compo, niveaux=niveaux, exclus={"ETF1"})
    pd.testing.assert_series_equal(tous.reindex(syms), seuls.reindex(syms), check_names=False)
    assert {"ETF1", "NM1"} <= set(tous.index)
    assert tous["ETF1"] < tous[syms].median()                  # ETF calme : niveau de référence, sans l'IA
    assert tous["NM1"] > tous[syms].median()                   # action agitée hors indice : placée parmi les membres


# --- § 4.21 : audit des biais ---------------------------------------------------------------------------
def _walk_forward_simule(sous_estime=0.8, seed=3):
    """Sorties de walk-forward simulées : le secteur « A » a un risque prévu trop bas (σ × 0,8), « B » juste."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2010-01-01", periods=160, freq="W-FRI")
    lignes = []
    for k, d in enumerate(dates):
        for i in range(40):
            brut = 0.15 + 0.01 * i + rng.normal(0, 0.02)
            secteur = "A" if i % 2 else "B"
            lignes.append({"date": d, "symbol": f"S{i}", "secteur": secteur, "fenetre": k * 4 // len(dates),
                           "brut": brut, "pred": brut + rng.normal(0, 0.02), "lvl_har": (brut + rng.normal(0, 0.04)) * 1.05,
                           "lvl_hybride": brut * (sous_estime if secteur == "A" else 1.0),
                           "liquidite": rng.random(), "beta_1a": rng.random(), "vol_3m": rng.random()})
    return pd.DataFrame(lignes)


def test_audit_signale_une_sous_estimation_persistante():
    a = ex.audit_biais(_walk_forward_simule())
    alertes = {(x["groupe"], x["valeur"], x["alerte"]) for x in a["alertes"]}
    assert ("secteur", "A", "sous-estimation persistante") in alertes
    assert not any(v == "B" for _, v, _ in alertes)
    assert a["groupes"]["secteur"]["A"]["rapport_variance"] == pytest.approx(0.64, abs=0.01)
    assert a["groupes"]["secteur"]["B"]["rapport_variance"] == pytest.approx(1.0, abs=1e-9)
    assert set(a["groupes"]) == {"secteur", "taille", "beta", "volatilite_passee", "annee"}
    assert a["ic_intra_secteur"]["ia"] > 0.5
    assert "sous-estimation persistante" in ex.verdict_audit(a)


def test_audit_sans_biais_aucune_alerte():
    a = ex.audit_biais(_walk_forward_simule(sous_estime=1.0))
    assert a["alertes"] == [] and ex.verdict_audit(a) == "aucune alerte"


def test_classement_creux_detecte():
    t = _walk_forward_simule(sous_estime=1.0)
    t["pred"] = np.random.default_rng(0).random(len(t))           # l'IA ne classe plus rien
    alertes = {(x["groupe"], x["alerte"]) for x in ex.audit_biais(t)["alertes"]}
    assert ("secteur", "classement creux (IA < HAR)") in alertes


def test_couverture_survivant():
    dates = pd.bdate_range("2010-01-01", periods=10)
    ret = pd.DataFrame(0.01, index=dates, columns=["A", "B", "C"])
    compo = pd.DataFrame({"symbol": ["A", "B", "C", "D"], "debut": pd.Timestamp("2000-01-01"), "fin": pd.NaT})
    assert ex.couverture_survivant(ret, compo, dates[-1:]) == {2010: pytest.approx(0.75)}   # D a disparu de Yahoo
