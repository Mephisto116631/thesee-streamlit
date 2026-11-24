"""Tests des ratios calculés depuis les bilans Alpha Vantage (sans réseau)."""

import data_pipeline as dp

BS = {
    "totalAssets": "1000", "totalLiabilities": "600", "totalShareholderEquity": "400",
    "totalCurrentAssets": "300", "totalCurrentLiabilities": "200", "retainedEarnings": "250",
    "commonStockSharesOutstanding": "10", "cashAndCashEquivalentsAtCarryingValue": "50",
    "shortLongTermDebtTotal": "200",
}
INC = {"totalRevenue": "800", "ebit": "120", "ebitda": "150", "netIncome": "80", "operatingIncome": "100"}


def test_ratios_fondamentaux():
    r = dp.ratios_depuis_bilans(BS, INC, prix=30.0)
    assert r["roe"] == 0.2            # 80 / 400
    assert r["margin"] == 0.125       # 100 / 800
    assert r["debt_eq"] == 0.5        # 200 / 400
    assert r["ev_ebitda"] == 3.0      # (300 + 200 - 50) / 150


def test_z_score_altman():
    r = dp.ratios_depuis_bilans(BS, INC, prix=30.0)
    # 1.2*0.1 + 1.4*0.25 + 3.3*0.12 + 0.6*0.5 + 1.0*0.8
    assert r["z_score"] == round(0.12 + 0.35 + 0.396 + 0.3 + 0.8, 3)


def test_valeurs_manquantes():
    bs = dict(BS, totalShareholderEquity="None", shortLongTermDebtTotal="None",
              longTermDebt="150", shortTermDebt="30")
    r = dp.ratios_depuis_bilans(bs, dict(INC, ebitda="None"), prix=0.0)
    assert r["roe"] is None and r["debt_eq"] is None   # pas de fonds propres -> pas de ratio
    assert r["ev_ebitda"] is None                      # pas de prix ni d'EBITDA
    assert dp.ratios_depuis_bilans({"totalAssets": "0"}, INC, 10.0) is None


def test_message_alpha_vantage():
    assert "premium" in dp._av_message({"Information": "This is a premium endpoint."})
