"""Examen approfondi de l'IA de volatilité : références, tests, calibration, placebo, PBO, frais."""
import numpy as np
import pandas as pd

import backtest_risque as bt
import examen_risque as ex


def _garch_simule(n_titres=40, jours=1500, a=0.08, b=0.9, graine=0):
    """Rendements d'un vrai GARCH(1,1) (variance de long terme propre à chaque titre)."""
    rng = np.random.default_rng(graine)
    lt = rng.uniform(0.01, 0.03, n_titres) ** 2
    s2 = lt.copy()
    r = np.empty((jours, n_titres))
    for t in range(jours):
        r[t] = rng.normal(0, np.sqrt(s2))
        s2 = lt * (1 - a - b) + a * r[t] ** 2 + b * s2
    return pd.DataFrame(r, index=pd.bdate_range("2010-01-04", periods=jours), columns=[f"T{i}" for i in range(n_titres)])


def test_garch_retrouve_ses_parametres():
    ret = _garch_simule()
    a, b = ex.garch_parametres(ret, n_titres=40)
    assert abs((a + b) - 0.98) < 0.05 and 0.02 < a < 0.2


def test_references_battent_une_constante():
    ret = _garch_simule(graine=1)
    reel = ret.pow(2).rolling(21).mean().shift(-21).pow(0.5) * np.sqrt(252)   # volatilité du mois suivant
    e = ex.ewma(ret)
    const = pd.DataFrame(np.sqrt(ret.pow(2).mean() * 252).values[None, :].repeat(len(ret), 0), index=ret.index, columns=ret.columns)
    ok = (reel.notna() & e.notna()).values
    q_e = ex.qlike(e.values[ok], reel.values[ok]).mean()
    q_c = ex.qlike(const.values[ok], reel.values[ok]).mean()
    assert q_e < q_c


def test_qlike_nul_si_parfait():
    assert np.allclose(ex.qlike(np.array([0.2, 0.3]), np.array([0.2, 0.3])), 0)
    assert ex.qlike(np.array([0.2]), np.array([0.4]))[0] > 0


def test_diebold_mariano():
    rng = np.random.default_rng(0)
    d = pd.date_range("2015-01-01", periods=300, freq="W")
    a = pd.Series(rng.normal(1, 0.1, 300), index=d)
    egal = ex.diebold_mariano(a, a + rng.normal(0, 0.1, 300), 5)
    meilleur = ex.diebold_mariano(a - 0.2, a, 5)
    assert abs(egal["t"]) < 3
    assert meilleur["t"] < -5


def test_calibration_retrouve_un_biais():
    rng = np.random.default_rng(0)
    reel = rng.uniform(0.1, 0.5, 2000)
    df = pd.DataFrame({"brut": reel, "prevu": reel * 1.2 * np.exp(rng.normal(0, 0.05, 2000))})
    c = ex.calibration(df, "prevu")
    assert abs(c["biais_median"] - 0.2) < 0.02


def test_pbo():
    # Hasard pur : ~50 % en moyenne (un seul tirage varie beaucoup)
    moy = np.mean([ex.pbo(pd.DataFrame(np.random.default_rng(g).normal(0, 0.04, (160, 8))))["pbo"] for g in range(8)])
    assert 0.35 < moy < 0.65
    bruit = pd.DataFrame(np.random.default_rng(0).normal(0, 0.04, (160, 8)))
    vrai = bruit.copy()
    vrai[0] += 0.03                                               # une variante vraiment meilleure
    assert ex.pbo(vrai)["pbo"] < 0.1


def test_frais_et_ordres():
    cout, ordres, rotation = bt.frais_et_ordres({"A": 0.5, "B": 0.5}, {"A": 0.5, "C": 0.5}, 5000)
    assert ordres == 2 and abs(rotation - 1.0) < 1e-12
    assert abs(cout - (2 * bt.FRAIS_ORDRE + 1.0 * 5000 * bt.ECART_PRIX)) < 1e-9   # 2 € + 5 €


def test_choisir_point_risque():
    pts = [{"rendement": 0.05 + 0.02 * i, "volatilite": v, "sharpe": 1.0} for i, v in enumerate([0.08, 0.12, 0.2])]
    assert bt._choisir(pts, 0.15)["volatilite"] == 0.12
    assert bt._choisir(pts, 0.05)["volatilite"] == 0.08
    assert bt._choisir(pts, np.nan)["volatilite"] == 0.08


def _donnees_examen():
    """Marché simulé : volatilité propre persistante par titre -> l'IA a de quoi apprendre."""
    rng = np.random.default_rng(5)
    n, jours = 50, 2300
    dates = pd.bdate_range("2008-01-02", periods=jours)
    marche = rng.normal(0.0003, 0.01, jours)
    rows = []
    for i in range(n):
        niveau = np.repeat(rng.uniform(0.005, 0.03, jours // 250 + 1), 250)[:jours]
        px = 100 * np.cumprod(1 + (0.6 + i / n) * marche + rng.normal(0, 1, jours) * niveau)
        rows += [{"symbol": f"T{i:02d}", "date": d, "close": p, "volume": 1e6 * (1 + i)} for d, p in zip(dates, px)]
    rows += [{"symbol": "SPY", "date": d, "close": p, "volume": 1e7} for d, p in zip(dates, 100 * np.cumprod(1 + marche))]
    return pd.DataFrame(rows), [f"T{i:02d}" for i in range(n)]


def test_walk_forward_references_et_placebo():
    raw, syms = _donnees_examen()
    data, ret = ex.preparer(raw, syms, None, {s: "AB"[i % 2] for i, s in enumerate(syms)})
    t = ex.walk_forward(data, ret, forcer_config="xgb_prudent")
    assert {"lvl_ia", "lvl_garch", "lvl_har", "lvl_ewma", "lvl_vol_3m"} <= set(t.columns)
    c = ex.comparer_references(t)
    assert set(c["dm"]) == {"ewma", "garch", "har"} and c["meilleure_reference"] in c["dm"]
    assert all(np.isfinite(v) for v in c["qlike"].values())
    p = ex.par_periode(t)
    assert "hors_crises" in p and set(p["secteurs"]) == {"A", "B"}
    pl = ex.placebo(data, ret)
    assert abs(pl["ic_cible_melangee"]) < 0.1          # cible mélangée : plus rien à apprendre
    assert pl["ic_fuite_volontaire"] > 0.5              # le test voit une fuite quand il y en a une


def test_backtest_reel_frais_promesse_fourchette():
    raw, syms = _donnees_examen()
    tous = {**bt.PORTEFEUILLES, **bt.PORTEFEUILLES_RISQUE}
    res = bt.backtest(raw, syms, None, debut="2012-01-01", pas_semaines=8, base="sp500",
                      variantes=["hist_3a"], portefeuilles=tous, garder_poids=True)
    assert set(res.loc[res["portefeuille"] != "indice", "portefeuille"]) == set(tous)
    px = raw.pivot_table(index="date", columns="symbol", values="close").sort_index()
    r = bt.backtest_reel(res, px, "risque_15", "hist_3a")
    assert r["rendement_net"] <= r["rendement_brut"] + 1e-12          # les frais coûtent
    assert r["ordres_par_an"] > 0 and r["frais_par_an"] > 0
    assert 0 <= r["part_semestres_au_dessus"] <= 1 and r["limite"] == 0.15
    c = bt.couverture_fourchette(res, px, "sharpe_max", "hist_3a")
    assert c["n"] > 0 and 0 <= c["part_sous_mauvais_cas"] <= 1
