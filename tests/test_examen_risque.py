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


def test_hybride_revision_marge():
    """Hybride : ordre de l'IA, niveaux HAR. Révision semestrielle : moins d'ordres. Marge apprise sur le passé."""
    raw, syms = _donnees_examen()
    data, ret = ex.preparer(raw, syms, None)
    t = ex.walk_forward(data, ret, forcer_config="xgb_prudent")
    tt = t.assign(rel=t["brut"])
    ic_ia = ex.mh._ic_par_date(tt, "lvl_ia").mean()
    ic_hyb = ex.mh._ic_par_date(tt.dropna(subset=["lvl_hybride"]), "lvl_hybride").mean()
    assert abs(ic_ia - ic_hyb) < 0.02                                  # même ordre que l'IA
    med = lambda c: float((t[c] / t["brut"]).median())
    assert abs(med("lvl_hybride") - med("lvl_har")) < 0.1              # niveau de HAR
    c = ex.comparer_hybride(t)
    assert c["decision"] in ("hybride", "har") and set(c["qlike"]) == {"hybride", "har", "ia"}

    tous = {**bt.PORTEFEUILLES, **bt.PORTEFEUILLES_RISQUE}
    res = bt.backtest(raw, syms, None, debut="2011-01-01", pas_semaines=4, base="sp500", variantes=["hybride"],
                      portefeuilles=tous, garder_poids=True, garder_frontieres=True)
    assert (res["variante"] == "hybride").any() and res.attrs["frontieres"]
    px = raw.pivot_table(index="date", columns="symbol", values="close").sort_index()
    mensuel = bt.backtest_reel(res, px, "sharpe_max", "hybride", revision_mois=1)
    semestre = bt.backtest_reel(res, px, "sharpe_max", "hybride", revision_mois=6)
    assert semestre["ordres_par_an"] < mensuel["ordres_par_an"]
    m = bt.marge_walk_forward(res, px, 0.15, "hybride", min_hist=2)
    assert 0.5 <= m["marge_actuelle"] <= 1.5 and m["n_semestres"] > 0


def test_dates_revision():
    d = pd.date_range("2020-01-06", periods=30, freq="4W")
    r6 = bt.dates_revision(d, 6)
    assert all(x.month in (1, 2, 7, 8) for x in r6) and len(r6) == len({(x.year, (x.month - 1) // 6) for x in d})
    assert len(bt.dates_revision(d, 12)) == len({x.year for x in d})


def test_ia_contre_har_et_variante_har():
    raw, syms = _donnees_examen()
    data, ret = ex.preparer(raw, syms, None)
    t = ex.walk_forward(data, ret, forcer_config="xgb_prudent")
    c = ex.ia_contre_har(t)
    assert c["decision"] in ("hybride", "har") and c["seuil"] > 0 and -1 <= c["gain"] <= 1
    res = bt.backtest(raw, syms, None, debut="2011-01-01", pas_semaines=8, base="sp500", variantes=["har"],
                      portefeuilles={"sharpe_max": None}, garder_poids=True)
    assert (res["variante"] == "har").any()


def _echantillon_niveau(n_titres=60, n_dates=260, graine=0):
    """Panel synthétique : la volatilité future dépend du niveau passé ET d'un facteur de marché caché
    que les variables de niveau (médiane du jour) permettent de voir."""
    import modele_horizon as mh
    rng = np.random.default_rng(graine)
    dates = pd.bdate_range("1999-01-04", periods=n_dates * 5, freq="B")[::5][:n_dates]
    lignes = []
    marche = np.cumsum(rng.normal(0, 0.15, n_dates))
    for i, d in enumerate(dates):
        base = rng.normal(np.log(0.25), 0.4, n_titres)
        v3 = np.exp(base + 0.5 * marche[i])
        for j in range(n_titres):
            futur = np.exp(base[j] + 0.5 * marche[min(i + 3, n_dates - 1)] + rng.normal(0, 0.15))
            ligne = {"date": d, "symbol": f"T{j}", "brut": futur, "lvl_vol_3m": v3[j], "lvl_ewma": v3[j] * 1.02,
                     "v1": v3[j] ** 2 / 252, "v5": v3[j] ** 2 / 252, "v22": v3[j] ** 2 / 252, "v63": v3[j] ** 2 / 252}
            ligne.update({f: rng.normal() for f in mh.FEATURES})
            lignes.append(ligne)
    df = pd.DataFrame(lignes)
    df["y"] = df.groupby("date")["brut"].rank(pct=True)
    return df


def test_niveau_xgb_tourne_et_le_placebo_ne_gagne_pas():
    data = _echantillon_niveau()
    tb = ex.walk_forward_niveau(data, "B", h=10)
    tp = ex.walk_forward_niveau(data, "B", h=10, melange=True)
    assert not tb.empty and tb["lvl_xgb"].notna().all() and (tb["lvl_xgb"] > 0).all()
    c = ex.comparer_niveau(tb, None, tp, h=10)
    assert {"B", "placebo", "regles", "candidate"} <= set(c)
    assert c["placebo"]["qlike"] >= c["B"]["qlike"] - 1e-9      # une cible mélangée ne peut pas mieux faire que la vraie


def test_echelle_mecanique_et_optimalite_du_facteur():
    """lvl_echelle = lvl_har × k ; et le facteur de forme fermée minimise bien la QLIKE sur l'échantillon où il est appris."""
    data = _echantillon_niveau(graine=3)
    t = ex.walk_forward_echelle(data, h=10)
    assert not t.empty and np.allclose(t["lvl_echelle"], t["lvl_har"] * t["k"])
    c = ex.comparer_echelle(t, h=10)
    assert {"force", "regles", "candidate", "par_fenetre"} <= set(c) and len(c["par_fenetre"]) == t["fenetre"].nunique()
    r, p = t["brut"].values ** 2, t["lvl_har"].values ** 2
    k_opt = np.sqrt(np.mean(r / p))
    q = lambda k: ex.qlike(np.sqrt(p) * k, np.sqrt(r)).mean()
    assert q(k_opt) <= min(q(k_opt * 0.9), q(k_opt * 1.1), q(1.0)) + 1e-12


def test_multi_horizon_mecanique_et_placebo():
    data = _echantillon_niveau(graine=5)
    par_h = {h: ex.walk_forward_niveau(data, "B", h=h) for h in (5, 22)}
    plc = {h: ex.walk_forward_niveau(data, "B", h=h, melange=True) for h in (5, 22)}
    c = ex.comparer_multi(par_h, plc)
    assert {"aspa", "par_horizon", "holm", "regles", "blocs_negatifs", "placebo"} <= set(c)
    assert set(c["par_horizon"]) == {5, 22} and c["aspa"]["mde_80"] > 0
    assert not (c["regles"]["1_piste"] and c["regles"]["2_fuite_probable"])


def _marche_vix(graine: int = 0, n_titres: int = 40, n_dates: int = 900):
    """Échantillon hebdomadaire : la variance future du marché est connue du VIX (options), pas des cours passés."""
    rng = np.random.default_rng(graine)
    dates = pd.date_range("2000-01-07", periods=n_dates, freq="W-FRI")
    sig_m = np.clip(0.01 * np.exp(rng.normal(0, 0.5, n_dates)), 0.004, 0.05)        # vol quotidienne du marché à venir
    vix = pd.Series(100 * sig_m * np.sqrt(252), index=dates)
    syms = [f"T{i:02d}" for i in range(n_titres)]
    betas = rng.uniform(0.5, 1.6, n_titres)
    idio = rng.uniform(0.008, 0.02, n_titres)
    rows = []
    for k, d in enumerate(dates):
        passe = sig_m[max(0, k - 1)]                                                   # les cours ne voient que le passé
        for s, b, e in zip(syms, betas, idio):
            v_passe = b ** 2 * passe ** 2 + e ** 2
            v_fut = b ** 2 * sig_m[k] ** 2 + e ** 2
            bruit = lambda: np.exp(rng.normal(0, 0.2))
            rows.append({"date": d, "symbol": s, "v1": v_passe * bruit() ** 3, "v5": v_passe * bruit() ** 2,
                         "v22": v_passe * bruit(), "v63": v_passe, "brut": np.sqrt(v_fut * 252) * bruit()})
    beta = pd.DataFrame(np.tile(betas, (n_dates, 1)), index=dates, columns=syms)
    return pd.DataFrame(rows), beta, vix


def test_harx_detecte_un_vix_informatif_et_pas_le_placebo():
    data, beta, vix = _marche_vix()
    d0 = ex.ajouter_x_vix(data, beta, vix)
    dp = ex.ajouter_x_vix(data, beta, vix, decalage=ex.DECALAGE_PLACEBO_VIX)
    assert np.isclose(d0["x_vix"].iloc[0], beta.iloc[0, 0] ** 2 * (vix.iloc[0] / 100) ** 2 / 252)
    t0 = ex.walk_forward_harx(d0, h=22)
    tp = ex.walk_forward_harx(dp, h=22)
    assert {"lvl_har", "lvl_harx", "fenetre", "coef_vix"} <= set(t0.columns)
    c = ex.comparer_harx({22: t0}, {22: tp})
    r = c["horizons"][22]
    assert r["dm"]["t"] < -2 and r["fenetres_negatives"] >= 3          # le vrai VIX aide nettement
    assert r["placebo"]["t"] > r["dm"]["t"]                             # le VIX d'un an plus tôt aide beaucoup moins
    assert c["regles"][22]["1_piste"] and c["regles"][22]["coef_vix_signe_stable"]
    assert "22 j : piste" in ex.verdict_harx(c)


def test_harx_vix_sans_information_ne_fait_pas_mieux():
    data, beta, vix = _marche_vix(graine=3)
    rng = np.random.default_rng(9)
    bidon = pd.Series(rng.permutation(vix.values), index=vix.index)    # même loi, aucun lien avec l'avenir
    t = ex.walk_forward_harx(ex.ajouter_x_vix(data, beta, bidon), h=22)
    c = ex.comparer_harx({22: t}, {})
    assert c["horizons"][22]["dm"]["t"] > -2 and not c["regles"][22]["1_piste"]


def test_beta_brut_retrouve_le_beta():
    rng = np.random.default_rng(1)
    rm = pd.Series(rng.normal(0, 0.01, 600))
    ret = pd.DataFrame({"SPY": rm, "A": 1.5 * rm + rng.normal(0, 0.002, 600)})
    assert abs(ex.beta_brut(ret)["A"].iloc[-1] - 1.5) < 0.05


def test_har_etendu_mecanique():
    import json
    raw, syms = _donnees_examen()
    data, _ = ex.preparer(raw, syms, None, {s: "ABC"[i % 3] for i, s in enumerate(syms)})
    tables = ex.variables_cours(raw, syms)
    jours = tables["beta"].index
    rng = np.random.default_rng(2)
    vix = pd.Series(20 + rng.normal(0, 3, len(jours)), index=jours)
    macro = pd.DataFrame({"credit": 2 + rng.normal(0, 0.3, len(jours)), "pente": rng.normal(0, 1, len(jours))}, index=jours)
    d, modeles = ex.modeles_etendus(ex.ajouter_etendu(data, tables, vix, macro))
    dp, _ = ex.modeles_etendus(ex.ajouter_etendu(data, tables, vix, macro, decalage=ex.DECALAGE_PLACEBO_VIX))
    assert {"sect_B", "sect_C"} <= set(modeles["m1"]) and set(ex.COLS_MARCHE) <= set(modeles["m2"])
    # semivariance négative : jamais plus grande que la variance totale sur la même fenêtre
    v22 = ex.har_entrees(raw.pivot_table(index="date", columns="symbol", values="close").pct_change())["v22"]
    rsm, v22 = tables["rsm22"].align(v22, join="inner")
    assert ((rsm <= v22 + 1e-12) | rsm.isna()).all().all() and rsm.notna().any().any()
    t = ex.walk_forward_lineaire(d, modeles)
    tp = ex.walk_forward_lineaire(dp, modeles)
    assert {"lvl_har", "lvl_m1", "lvl_m2"} <= set(t.columns) and t.attrs["coefs"]
    c = ex.comparer_etendu(t, tp)
    assert {"1_piste", "3_placebo_ne_bat_pas_m1", "2abcd"} <= set(c["regles"])
    assert isinstance(ex.verdict_etendu(c), str)
    json.dumps(c, default=float)


def _comparaison_1m(graine: int, permuter: bool):
    data, beta, vix = _marche_vix(graine=graine)
    if permuter:
        vix = pd.Series(np.random.default_rng(9).permutation(vix.values), index=vix.index)
    t = ex.walk_forward_harx(ex.ajouter_x_vix(data, beta, vix), h=ex.H_MOIS)
    tp = ex.walk_forward_harx(ex.ajouter_x_vix(data, beta, vix, decalage=ex.DECALAGE_PLACEBO_VIX), h=ex.H_MOIS)
    return ex.comparer_harx({ex.H_MOIS: t}, {ex.H_MOIS: tp})


def test_harx_1m_confirme_si_le_vix_informe():
    v, cond = ex.verdict_harx_1m(_comparaison_1m(0, False))
    assert v == "confirmé" and all(cond.values())


def test_harx_1m_non_confirme_si_vix_sans_information():
    v, cond = ex.verdict_harx_1m(_comparaison_1m(3, True))
    assert v.startswith("non confirmé") and not cond["a_t_et_ecart"]


def test_couverture_1m():
    rng = np.random.default_rng(4)
    n = 20000
    sig = rng.uniform(0.15, 0.4, n)
    t = pd.DataFrame({"lvl": sig, "ret_futur": rng.standard_t(5, n) * sig * np.sqrt(22 / 252)})
    c = ex.couverture_1m(t, "lvl")
    assert abs(c["part_depassements"] - 0.05) < 0.01 and not c["avertissement"]   # loi juste : 5 %
    t["ret_futur"] *= 2                                                                # risque sous-estimé de moitié
    assert ex.couverture_1m(t, "lvl")["avertissement"]


def test_ajouter_rendement_futur():
    raw, syms = _donnees_examen()
    t = pd.DataFrame({"date": [pd.Timestamp("2008-01-02")], "symbol": ["T00"]})
    r = ex.ajouter_rendement_futur(t, raw, 22)["ret_futur"].iloc[0]
    px = raw[raw["symbol"] == "T00"].set_index("date")["close"]
    assert np.isclose(r, px.iloc[22] / px.iloc[0] - 1)


def test_nettoyer_retire_cours_aberrants_et_petits_cours():
    jours = pd.bdate_range("2020-01-01", periods=200)
    lignes = []
    for i, d in enumerate(jours):
        lignes.append({"symbol": "OK", "date": d, "close": 50 + 0.01 * i})
        lignes.append({"symbol": "SAUT", "date": d, "close": 30.0 if i != 100 else 90.0})   # +200 % puis −67 % : aberrant
        lignes.append({"symbol": "PENNY", "date": d, "close": 2.0})
    raw = pd.DataFrame(lignes)
    data = pd.DataFrame([{"date": d, "symbol": s} for d in jours[::5] for s in ["OK", "SAUT", "PENNY"]])
    out, part = ex.nettoyer(data, raw, h=22)
    assert set(out["symbol"]) >= {"OK"} and (out["symbol"] == "OK").sum() == (data["symbol"] == "OK").sum()
    assert "PENNY" not in set(out["symbol"])
    gardes = out.loc[out["symbol"] == "SAUT", "date"]
    saut = jours[100]
    # retiré si le saut est dans [t − 63, t + 22] séances, gardé loin du saut
    assert not any((jours.get_loc(d) >= 100 - 22) and (jours.get_loc(d) <= 100 + 64) for d in gardes)
    assert any(jours.get_loc(d) < 100 - 22 for d in gardes)
    assert 0 < part < 1


def test_perte_winsorisee_limite_les_extremes():
    t = pd.DataFrame({"date": [pd.Timestamp("2020-01-03")] * 200, "lvl": [0.2] * 200,
                      "brut": [0.2] * 199 + [20.0]})                                   # un titre aberrant
    brute = ex._pertes_par_date(t, "lvl").iloc[0]
    w = ex._pertes_par_date(t, "lvl", winsor=True).iloc[0]
    assert w < brute / 10


def test_etape_2_declenchee_par_le_seul_mde(monkeypatch):
    appels = []
    vrai = ex.comparer_harx

    def faux(par_h, placebo_h, n_essais_total=10, winsor=False):
        appels.append(winsor)
        c = vrai(par_h, placebo_h, n_essais_total, winsor)
        c["horizons"][ex.H_MOIS]["dm"]["mde_80"] = 0.5 if not winsor else 0.02   # étape 1 non informative
        return c
    monkeypatch.setattr(ex, "comparer_harx", faux)
    raw, syms = _donnees_examen()
    d = pd.bdate_range("2007-01-01", "2017-12-31")
    vix = pd.Series(20 + np.random.default_rng(1).random(len(d)) * 5, index=d)
    c = ex.essai_harx_1m(raw, syms, vix, nettoyage=True)
    assert c["etape"] == 2 and appels == [False, True] and c["mde_etape_1"] == 0.5
    appels.clear()
    c = ex.essai_harx_1m(raw, syms, vix, nettoyage=True, winsor=False)       # S&P 500 : étape imposée
    assert c["etape"] == 1 and appels == [False]


def test_risque_du_mois_du_jour():
    import modele_risque as mr
    raw, syms = _donnees_examen()
    jours = pd.bdate_range("2007-01-01", "2017-12-31")
    vix = pd.Series(20 + np.random.default_rng(1).random(len(jours)) * 5, index=jours)
    v, info = mr.niveaux_harx_1m_du_jour(raw, syms, vix)
    derniere = pd.Timestamp(raw["date"].max())
    assert len(v) == len(syms) and (v > 0).all() and np.isfinite(v).all()
    assert info["date"] == derniere.date().isoformat() and info["vix"] == float(vix.loc[derniere])   # pas de VIX postérieur
    # VIX du jour plus haut : seule x_vix change, la prévision bouge dans le sens du coefficient appris
    haut = vix.copy()
    haut.loc[derniere] = 60.0
    v2, info2 = mr.niveaux_harx_1m_du_jour(raw, syms, haut)
    assert np.isclose(info2["coef_vix"], info["coef_vix"], rtol=1e-3)     # l'ajustement ne dépend presque pas du dernier jour
    assert np.sign((v2 ** 2 - v ** 2).mean()) == np.sign(info["coef_vix"])
