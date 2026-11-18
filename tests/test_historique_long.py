"""Historique long : téléchargé pour les modèles horizon, mais rien avant 2020 n'est écrit dans Supabase."""
import sys

import pandas as pd

import _st_shim

sys.modules.setdefault("streamlit", _st_shim)

import data_pipeline as dp  # noqa: E402


def test_stockage_limite_et_historique_long(monkeypatch):
    def faux_yahoo(tickers, start=dp.HISTORIQUE_DEBUT):
        dates = pd.bdate_range(start, "2026-11-17", freq="20B").date
        return pd.DataFrame([{"symbol": t, "date": d, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1}
                             for t in tickers for d in dates])

    ecrit = []
    monkeypatch.setattr(dp, "_telecharger_yahoo", faux_yahoo)
    monkeypatch.setattr(dp.db, "last_dates_by_symbol", lambda table: {"AAA": pd.Timestamp("2026-11-10").date()})
    monkeypatch.setattr(dp.db, "upsert_market_data", lambda df, table: ecrit.append(df))
    monkeypatch.setattr(dp.db, "progression", lambda *a: None)

    court = dp._sync_incremental(["AAA", "BBB"], "market_data")
    long = dp.historique_long()

    tout = pd.concat(ecrit)
    assert tout["date"].min() >= pd.Timestamp(dp.HISTORIQUE_DEBUT).date()          # rien d'ancien en base
    assert tout[tout["symbol"] == "AAA"]["date"].min() >= pd.Timestamp("2026-11-05").date()  # incrémental
    assert court["date"].min() >= pd.Timestamp(dp.HISTORIQUE_DEBUT)                 # le reste du calcul inchangé
    assert long["date"].min() < pd.Timestamp("2006-01-01")                           # modèles : depuis 2005
