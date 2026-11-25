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


# --- § 4.22 : membres historiques retrouvés ---------------------------------------------------------------
def test_symboles_examen_ajoute_les_anciens_membres():
    import experiences
    compo = pd.DataFrame({"symbol": ["A", "OLD"], "debut": pd.Timestamp("2000-01-01"), "fin": [pd.NaT, pd.Timestamp("2010-01-01")]})
    assert experiences.symboles_examen(["A", "B"], compo) == ["A", "B", "OLD"]
    assert experiences.symboles_examen(["B"], None) == ["B"]


def test_couverture_ecarte_un_titre_peu_cote():
    raw, syms, compo = _cours(n=55, jours=700)
    trous = raw["symbol"].eq("T03") & (pd.to_datetime(raw["date"]).dt.dayofweek < 2)     # coté 3 jours sur 5
    raw = raw[~trous]
    cov = ex.couverture_cours(raw, syms)
    assert cov["T03"].iloc[-1] == pytest.approx(0.6, abs=0.05) and cov["T00"].iloc[-1] == pytest.approx(1.0)
    avec, _ = ex.preparer(raw, syms, compo, couverture_min=ex.COUVERTURE_MIN, h=63)
    sans, _ = ex.preparer(raw, syms, compo, h=63)
    assert "T03" not in set(avec["symbol"]) and "T00" in set(avec["symbol"])
    assert set(avec["symbol"]) <= set(sans["symbol"])


# --- §§ 4.23-4.24 : essais « HAR relatif » et « IA plus informée » ------------------------------------------
def _cours_niveaux_propres(n=60, jours=1500, seed=4):
    """Chaque titre a SON niveau de risque, très différent d'un titre à l'autre, et persistant ; régime commun qui varie."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2012-01-02", periods=jours)
    regime = np.exp(0.4 * np.sin(np.arange(jours) / 120))
    marche = rng.normal(0.0002, 0.008, jours) * regime
    rows = []
    for i in range(n):
        sig = 0.004 + 0.03 * (i / n) ** 2                          # titres très calmes à très agités
        px = 100 * np.cumprod(1 + 0.8 * marche + rng.normal(0, sig, jours) * regime)
        rows += [{"symbol": f"T{i:02d}", "date": d, "close": p, "volume": 1e6} for d, p in zip(dates, px)]
    rows += [{"symbol": "SPY", "date": d, "close": p, "volume": 1e7} for d, p in zip(dates, 100 * np.cumprod(1 + marche))]
    syms = [f"T{i:02d}" for i in range(n)]
    compo = pd.DataFrame({"symbol": syms, "debut": pd.Timestamp("2000-01-01"), "fin": pd.NaT})
    return pd.DataFrame(rows), syms, compo


def test_har_relatif_ramene_chaque_titre_vers_son_propre_risque():
    raw, syms, compo = _cours_niveaux_propres()
    data, ret = ex.preparer(raw, syms, compo)
    d = ex.ajouter_risque_habituel(data, ret)
    assert d["L"].notna().mean() > 0.9
    tr = ex.walk_forward_har_relatif(d)
    tp = ex.walk_forward_har_relatif(d, placebo=True)
    assert set(tr["fenetre"]) and {"lvl_rel", "lvl_har"} <= set(tr.columns)
    c = ex.comparer_har_relatif(tr, tp)
    assert set(c["regles"]) == {"1_niveau", "2_crises", "3_stabilite", "4_biais", "5_placebo"}
    # HAR commun tire les titres calmes vers le haut et les agités vers le bas ; le relatif les ramène vers leur propre risque.
    # (Qu'il gagne aussi en QLIKE est la question de l'essai : dans cette simulation, non, car il est plus dispersé.)
    calmes, agites = tr[tr["vol_3m"] <= 0.2], tr[tr["vol_3m"] >= 0.8]
    for g in (calmes, agites):
        assert abs(ex._rapport_variance(g, "lvl_rel") - 1) < abs(ex._rapport_variance(g, "lvl_har") - 1)
    # Placebo : chaque date garde les mêmes valeurs de L, attribuées à d'autres titres
    m = ex._melanger_L(d.dropna(subset=["L"]), 0)
    base = d.dropna(subset=["L"])
    assert np.allclose(np.sort(m["L"].values), np.sort(base["L"].values)) and not np.allclose(m["L"].values, base["L"].values)
    assert ex.verdict_har_relatif(c).startswith(("adopté", "non adopté"))


def test_har_relatif_retrouve_des_coefficients_connus():
    rng = np.random.default_rng(2)
    n = 5000
    df = pd.DataFrame({"L": rng.uniform(1e-5, 1e-3, n)})
    for c in ex.COLS_RELATIF:
        df[c] = df["L"] * rng.uniform(0.5, 2, n)
    vrai = np.array([0.1, 0.05, 0.1, 0.2, 0.5])
    var = df["L"] * (vrai[0] + sum(b * df[c] / df["L"] for b, c in zip(vrai[1:], ex.COLS_RELATIF)))
    df["brut"] = np.sqrt(var * 252)
    np.testing.assert_allclose(ex.har_relatif_ajuster(df), vrai, atol=1e-8)
    np.testing.assert_allclose(ex.har_relatif_prevoir(df, vrai), df["brut"].values, rtol=1e-9)


def test_variables_ia_en_rangs_du_jour():
    raw, syms, compo = _cours(n=55, jours=700)
    data, ret = ex.preparer(raw, syms, compo, h=63)
    d = ex.ajouter_variables_ia(data, ret)
    for c in ex.FEATURES_INFORMEE:
        assert d[c].between(0, 1).all() and d[c].notna().all()
    assert len(d) == len(data)


def test_comparer_informee_regles():
    rng = np.random.default_rng(1)
    dates = pd.bdate_range("2010-01-01", periods=200, freq="W-FRI")
    lignes = []
    for k, dt in enumerate(dates):
        for i in range(50):
            brut = 0.1 + 0.01 * i
            lignes.append({"date": dt, "symbol": f"S{i}", "brut": brut, "fenetre": k * 4 // len(dates), "config": "lineaire",
                           "base": brut + rng.normal(0, 0.15), "plus": brut + rng.normal(0, 0.05), "plc": brut + rng.normal(0, 0.15)})
    t = pd.DataFrame(lignes)
    c = ex.comparer_informee(t.assign(pred=t["base"]), t.assign(pred=t["plus"]), t.assign(pred=t["plc"]), h=126)
    assert c["gain"] > 0.05 and c["regles"]["1_preuve"] and c["regles"]["2_taille"] and c["regles"]["3_placebo"]
    assert c["adopte"] and ex.verdict_informee(c).startswith("adopté")
    c2 = ex.comparer_informee(t.assign(pred=t["base"]), t.assign(pred=t["plc"]), t.assign(pred=t["plc"]), h=126)
    assert not c2["adopte"]


# --- §§ 4.25-4.26 : « HAR relatif protégé en crise » et « IA + climat de marché » -----------------------------
def test_proteger_prend_le_plus_eleve_seulement_en_choc():
    t = pd.DataFrame({"L": [1.0, 1.0, 1.0], "v22": [1.5, 2.5, 3.0],
                      "lvl_rel": [0.20, 0.20, 0.40], "lvl_har": [0.30, 0.30, 0.30]})
    p = ex.proteger(t)
    assert list(p["choc"]) == [False, True, True]
    assert list(p["lvl_prot"]) == pytest.approx([0.20, 0.30, 0.40])     # calme : relatif ; choc : le plus élevé


def test_climat_du_jour_et_placebo_decale():
    dates = pd.bdate_range("2015-01-01", periods=600)
    vix = pd.Series(np.linspace(10, 40, 600), index=dates)
    data = pd.DataFrame({"date": np.repeat(dates[300::50], 3), "symbol": ["A", "B", "C"] * 6})
    d = ex.ajouter_climat(data, vix)
    assert d.groupby("date")["x_ln_vix"].nunique().eq(1).all()                 # même valeur pour tous les titres d'une date
    assert d.loc[d["date"] == dates[300], "x_ln_vix"].iloc[0] == pytest.approx(np.log(vix.iloc[300]))
    p = ex.ajouter_climat(data, vix, decalage=252)
    assert p.loc[p["date"] == dates[300], "x_ln_vix"].iloc[0] == pytest.approx(np.log(vix.iloc[300 - 252]))
    assert len(d) == len(data) and d[ex.FEATURES_CLIMAT].notna().all().all()
