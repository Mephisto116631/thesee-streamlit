"""Preuve continue de l'IA de volatilité : bilan en conditions réelles, garde-fou de
publication, valorisation SEC actuelle (PER, ROE...)."""

import numpy as np
import pandas as pd

import fondamentaux_sec as fsec
import modele_risque as mr
import publish


def _marche(n_titres=60, n_jours=520, graine=0):
    """Cours simulés : chaque titre a sa propre volatilité, qui change à mi-parcours pour la moitié."""
    rng = np.random.default_rng(graine)
    dates = pd.bdate_range("2022-01-03", periods=n_jours)
    sig = rng.uniform(0.1, 0.6, n_titres) / np.sqrt(252)
    sig_fut = sig.copy()
    sig_fut[: n_titres // 2] = rng.uniform(0.1, 0.6, n_titres // 2) / np.sqrt(252)
    r = np.vstack([rng.normal(0, sig, (n_jours // 2, n_titres)),
                   rng.normal(0, sig_fut, (n_jours - n_jours // 2, n_titres))])
    px = pd.DataFrame(100 * np.exp(np.cumsum(r, axis=0)), index=dates, columns=[f"T{i}" for i in range(n_titres)])
    return px, sig * np.sqrt(252), sig_fut * np.sqrt(252)


def test_bilan_reel_ia_informee_bat_la_reference():
    px, sig, sig_fut = _marche()
    # Prévisions hebdomadaires dans la 2e moitié... la référence (3 mois passés) se trompe pour les
    # titres dont le régime a changé ; une « IA » qui connaît le nouveau régime doit gagner.
    dates = px.index[200:260:5]
    lignes = []
    for d in dates:
        i = px.index.get_loc(d)
        vol_3m = px.pct_change().iloc[i - 62:i + 1].std() * np.sqrt(252)
        for k, s in enumerate(px.columns):
            lignes.append({"date": d, "symbol": s, "vol_prevue": sig_fut[k], "vol_3m": vol_3m[s]})
    b = mr.bilan_reel(pd.DataFrame(lignes), px)
    assert b["n_dates"] == len(dates)
    assert b["ic_ia"] > b["ic_reference"] and b["gain"] > 0.1
    assert b["premiere_prevision"] == str(dates[0].date())
    assert b["verdict"] in ("probant", "pas encore assez de recul")


def test_bilan_reel_sans_recul_annonce_le_premier_bilan():
    px, _, _ = _marche()
    d = px.index[-10]                           # prévision trop récente pour être jugée
    suivi = pd.DataFrame([{"date": d, "symbol": s, "vol_prevue": 0.2, "vol_3m": 0.2} for s in px.columns])
    b = mr.bilan_reel(suivi, px)
    assert b["n_dates"] == 0 and "verdict" not in b
    assert pd.Timestamp(b["premier_bilan"]) > d + pd.Timedelta(days=170)
    assert mr.bilan_reel(pd.DataFrame(), px, premiere="2026-11-19")["premier_bilan"].startswith("2027-05")


def test_verdict_labo_le_plus_recent_fait_foi():
    lignes = [
        {"nom": "risque_volatilite", "horizon": "6m", "verdict": "probant", "t_stat": 6.5, "cree_le": "2026-10-01"},
        {"nom": "risque_volatilite", "horizon": "6m", "verdict": "non probant", "t_stat": 1.2, "cree_le": "2026-11-02"},
        {"nom": "risque_volatilite", "horizon": "1a", "verdict": "probant", "cree_le": "2026-12-01"},
        {"nom": "risque_volatilite_comptes", "horizon": "6m", "verdict": "probant", "cree_le": "2026-12-01"},
    ]
    v = mr.verdict_labo(lignes)
    assert v["probant"] is False and v["t_stat"] == 1.2
    assert mr.verdict_labo(lignes[:1])["probant"] is True
    assert mr.verdict_labo([])["probant"] is False


def test_garde_fou_vol_ia_non_publiee_si_non_probant():
    vol = pd.Series({"AAA": 0.2, "BBB": np.nan, "CCC": 0.35})
    assert publish.filtrer_vol_ia(vol, {"probant": False}) is None
    assert publish.filtrer_vol_ia(vol, {}) is None
    ok = publish.filtrer_vol_ia(vol, {"probant": True})
    assert list(ok.index) == ["AAA", "CCC"]


FAITS = {"facts": {
    "us-gaap": {
        "Assets": {"units": {"USD": [{"end": "2025-12-31", "val": 1000.0, "filed": "2026-02-20", "form": "10-K"}]}},
        "StockholdersEquity": {"units": {"USD": [{"end": "2025-12-31", "val": 400.0, "filed": "2026-02-20", "form": "10-K"}]}},
        "NetIncomeLoss": {"units": {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": 80.0,
                                             "filed": "2026-02-20", "form": "10-K"}]}},
        "GrossProfit": {"units": {"USD": [{"start": "2025-01-01", "end": "2025-12-31", "val": 300.0,
                                           "filed": "2026-02-20", "form": "10-K"}]}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
            {"start": "2025-01-01", "end": "2025-12-31", "val": 100.0, "filed": "2026-02-20", "form": "10-K"}]}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": [
            {"start": "2025-01-01", "end": "2025-12-31", "val": 8.0, "filed": "2026-02-20", "form": "10-K"}]}},
    },
}}


def test_valorisation_actuelle_et_division_posterieure():
    faits = fsec.extraire(FAITS, "AAA")
    # Division 2 pour 1 APRÈS les comptes : le BPA publié (8 $) vaut 4 $ par action d'aujourd'hui
    splits = pd.DataFrame({"symbol": ["AAA"], "date": [pd.Timestamp("2026-06-01")], "ratio": [2.0]})
    v = fsec.valorisation_actuelle(faits, pd.Series({"AAA": 60.0}), splits).set_index("symbol").loc["AAA"]
    assert v["bpa_sec"] == 4.0                                     # PER = 60 / 4 = 15
    assert abs(v["vc_action_sec"] - 400 / 20) < 1e-9              # 80 / 4 = 20 actions -> 20 $ par action
    assert abs(v["roe_sec"] - 0.2) < 1e-9
    assert abs(v["rentabilite_brute"] - 0.3) < 1e-9
    assert abs(v["endettement"] - 0.6) < 1e-9
    assert abs(v["part_encaissee"] - 1.25) < 1e-9
    assert str(pd.Timestamp(v["comptes_date"]).date()) == "2026-02-20"


def test_valorisation_absurde_ecartee_et_medianes():
    faits = fsec.extraire(FAITS, "AAA")
    v = fsec.valorisation_actuelle(faits, pd.Series({"AAA": 1e6}))  # PER 125 000 : erreur d'unité
    assert pd.isna(v["bpa_sec"].iloc[0])
    valo = pd.DataFrame({"symbol": ["A", "B", "C"], "bpa_sec": [2.0, 4.0, -1.0], "vc_action_sec": [10.0, 10.0, 5.0],
                         "roe_sec": [0.1, 0.3, -0.2], "rentabilite_brute": [0.2] * 3, "endettement": [0.5] * 3,
                         "part_encaissee": [1.0] * 3})
    snap = pd.DataFrame({"symbol": ["A", "B", "C"], "secteur": ["Tech"] * 3, "close": [40.0, 40.0, 40.0],
                         "is_etf": [False] * 3})
    med = publish.medianes_valorisation(valo, snap).set_index("secteur").loc["Tech"]
    assert med["per"] == 15.0                                      # médiane de 20 et 10 ; la perte est exclue
    assert med["cours_vc"] == 4.0


def _faits(eps=None, actions=None, balise_rn="NetIncomeLoss"):
    us = {k: v for k, v in FAITS["facts"]["us-gaap"].items() if k not in ("EarningsPerShareDiluted", "NetIncomeLoss")}
    us[balise_rn] = FAITS["facts"]["us-gaap"]["NetIncomeLoss"]
    if eps is not None:
        us["EarningsPerShareDiluted"] = {"units": {"USD/shares": [
            {"start": "2025-01-01", "end": "2025-12-31", "val": eps, "filed": "2026-02-20", "form": "10-K"}]}}
    f = {"facts": {"us-gaap": us}}
    if actions is not None:
        f["facts"]["dei"] = {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
            {"end": "2026-02-01", "val": actions, "filed": "2026-02-20", "form": "10-K"}]}}}
    return fsec.extraire(f, "AAA")


def test_bpa_d_une_autre_categorie_d_actions_ecarte():
    # BPA de l'action A (≈ 1 500 actions B) : PER 0,0075 et cours / valeur comptable absurde -> non disponible
    v = fsec.valorisation_actuelle(_faits(eps=8000.0), pd.Series({"AAA": 60.0})).iloc[0]
    assert pd.isna(v["bpa_sec"]) and pd.isna(v["vc_action_sec"])
    assert abs(v["roe_sec"] - 0.2) < 1e-9                      # les ratios sans action restent justes


def test_sans_bpa_publie_non_disponible_et_balise_de_repli():
    # Pas de BPA publié : le nombre d'actions en couverture ne compte souvent qu'une catégorie
    # d'actions (Visa) -> PER et cours / valeur comptable « non disponible » plutôt que faux
    v = fsec.valorisation_actuelle(_faits(actions=20.0), pd.Series({"AAA": 60.0})).iloc[0]
    assert pd.isna(v["bpa_sec"]) and pd.isna(v["vc_action_sec"])
    assert abs(v["roe_sec"] - 0.2) < 1e-9
    # Bénéfice publié sous une balise de repli (résultat des activités poursuivies)
    v = fsec.valorisation_actuelle(_faits(eps=4.0, balise_rn="IncomeLossFromContinuingOperations"),
                                   pd.Series({"AAA": 60.0})).iloc[0]
    assert abs(v["roe_sec"] - 0.2) < 1e-9 and v["bpa_sec"] == 4.0
