# pages/1_Screener.py
# ==============================================================================
# MODULE : SCREENER QUANTAMENTAL
# ==============================================================================
import streamlit as st
import pandas as pd
from theme import apply_theme
import data_pipeline as dp
import utils

st.set_page_config(page_title="Screener — Thésée", page_icon="📊", layout="wide")
apply_theme()

st.title("📊 Screener Quantamental")

if "thesee_data" not in st.session_state:
    st.session_state["thesee_data"] = dp.get_all_data()
data = st.session_state["thesee_data"]

with st.sidebar:
    st.subheader("Filtres stratégiques")
    secteur = st.selectbox("Secteur économique :", ["Tous"] + list(utils.dict_secteurs.keys()))

market_clean = data["market_data_clean"]

if market_clean.empty:
    st.warning("Aucune donnée de marché disponible.")
else:
    df = market_clean.groupby("symbol").last().reset_index()

    cols_market = ["symbol", "close", "rsi_14", "mom_5j", "mom_20j", "volatility", "macd_diff"]
    df = df[cols_market].rename(columns={
        "symbol": "Ticker",
        "close": "Dernier Prix",
        "rsi_14": "RSI 14",
        "mom_5j": "Mom. 5j (%)",
        "mom_20j": "Mom. 20j (%)",
        "volatility": "Volatilité",
        "macd_diff": "MACD Diff",
    })

    df["Mom. 5j (%)"] = (df["Mom. 5j (%)"] * 100).round(2)
    df["Mom. 20j (%)"] = (df["Mom. 20j (%)"] * 100).round(2)

    fonda = data["fonda_data_clean"]
    if not fonda.empty:
        f = fonda.rename(columns={
            "symbol": "Ticker", "roe": "ROE (%)",
            "margin": "Marge Op. (%)", "ev_ebitda": "EV/EBITDA",
        })
        df = df.merge(f[["Ticker", "ROE (%)", "Marge Op. (%)", "EV/EBITDA"]], on="Ticker", how="left")

    if secteur != "Tous":
        tickers_sec = utils.dict_secteurs[secteur]
        df = df[df["Ticker"].isin(tickers_sec)]

    st.dataframe(df.round(2), use_container_width=True, hide_index=True)
