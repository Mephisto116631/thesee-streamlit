"""Fondamentaux SEC : lecture XBRL, date de publication respectée, divisions d'actions."""
import numpy as np
import pandas as pd

import fondamentaux_sec as fsec


def _fait(end, val, filed, start=None, form="10-K"):
    e = {"end": end, "val": val, "filed": filed, "form": form}
    if start:
        e["start"] = start
    return e


FAITS = {"facts": {
    "us-gaap": {
        "Assets": {"units": {"USD": [
            _fait("2019-12-31", 100.0, "2020-02-20"),
            _fait("2020-12-31", 120.0, "2021-02-20"),
            _fait("2020-12-31", 999.0, "2022-02-20"),          # correction tardive : ignorée
        ]}},
        "StockholdersEquity": {"units": {"USD": [_fait("2020-12-31", 60.0, "2021-02-20")]}},
        "NetIncomeLoss": {"units": {"USD": [
            _fait("2020-12-31", 12.0, "2021-02-20", start="2020-01-01"),
            _fait("2020-06-30", 3.0, "2020-08-01", start="2020-04-01", form="10-Q"),   # trimestre : ignoré
        ]}},
        "GrossProfit": {"units": {"USD": [_fait("2020-12-31", 48.0, "2021-02-20", start="2020-01-01")]}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [
            _fait("2020-12-31", 10.0, "2021-02-20", start="2020-01-01")]}},
    },
    "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        _fait("2020-01-31", 10.0, "2020-02-20"),
        _fait("2021-01-31", 40.0, "2021-02-20"),     # division 4 pour 1 entre les deux : pas d'émission
    ]}}},
}}


def test_extraire_premiere_publication_et_annuel():
    df = fsec.extraire(FAITS, "AAA")
    a = df[(df["variable"] == "actifs") & (df["end"] == "2020-12-31")]
    assert len(a) == 1 and a["val"].iloc[0] == 120.0                 # pas la correction de 2022
    rn = df[df["variable"] == "resultat_net"]
    assert list(rn["val"]) == [12.0]                                  # le trimestriel est écarté


def test_facteurs_point_in_time_et_divisions():
    faits = fsec.extraire(FAITS, "AAA")
    dates = pd.DatetimeIndex(["2021-01-15", "2021-03-01"])
    px = pd.DataFrame({"AAA": [5.0, 5.0]}, index=dates)              # cours ajusté
    splits = pd.DataFrame({"symbol": ["AAA"], "date": [pd.Timestamp("2020-07-01")], "ratio": [4.0]})
    fd = fsec.caracteristiques_fondamentales(faits, px, splits, dates).set_index("date")
    avant, apres = fd.loc["2021-01-15"], fd.loc["2021-03-01"]
    assert np.isnan(avant["fd_rentabilite"])                          # comptes 2020 pas encore publiés
    assert apres["fd_rentabilite"] == 48.0 / 120.0
    assert abs(apres["fd_croissance_actifs"] - 0.2) < 1e-9
    assert abs(apres["fd_emissions"]) < 1e-9                          # 10 -> 40 actions = division, pas émission
    assert apres["fd_rendement_benef"] == 12.0 / (5.0 * 40.0)         # cours après division × actions
    assert abs(apres["fd_accruals"] - (12.0 - 10.0) / 120.0) < 1e-9


def test_facteur_splits():
    dates = pd.DatetimeIndex(["2020-01-01", "2021-01-01"])
    sp = pd.DataFrame({"symbol": ["AAA"], "date": [pd.Timestamp("2020-07-01")], "ratio": [4.0]})
    f = fsec.facteur_splits(sp, dates, ["AAA", "BBB"])
    assert list(f["AAA"]) == [4.0, 1.0] and list(f["BBB"]) == [1.0, 1.0]


def test_types_apres_concatenation():
    """Régression : une entreprise sans données laissait des dates en type « object »."""
    vide = fsec.extraire({}, "VIDE")
    plein = fsec.extraire(FAITS, "AAA")
    tout = pd.concat([vide.astype(object), plein.astype(object)], ignore_index=True)
    tout["end"] = pd.to_datetime(tout["end"])
    tout["filed"] = pd.to_datetime(tout["filed"])
    tout["val"] = pd.to_numeric(tout["val"])
    dates = pd.DatetimeIndex(["2021-03-01"])
    fd = fsec.caracteristiques_fondamentales(tout, pd.DataFrame({"AAA": [5.0]}, index=dates), None, dates)
    assert fd["fd_rentabilite"].iloc[0] == 0.4
