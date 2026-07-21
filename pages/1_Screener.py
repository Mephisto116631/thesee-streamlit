# pages/1_Screener.py
# ==============================================================================
# MODULE : SCREENER QUANTAMENTAL — univers élargi S&P 500 + Nasdaq 100 + ETFs
# ==============================================================================
import streamlit as st
import pandas as pd
from theme import apply_theme, palette_selector_sidebar
import data_pipeline as dp
import universe
import utils

st.set_page_config(page_title="Screener — Thésée", page_icon="📊", layout="wide")
apply_theme()

st.title("📊 Screener Quantamental")

if "thesee_univers" not in st.session_state:
    st.session_state["thesee_univers"] = universe.get_univers_complet()
if "thesee_data" not in st.session_state:
    univers_df = st.session_state["thesee_univers"]
    st.session_state["thesee_data"] = dp.get_all_data(univers_etendu=univers_df["symbol"].tolist())

data = st.session_state["thesee_data"]
univers_df = st.session_state["thesee_univers"]

with st.sidebar:
    palette_selector_sidebar()
    st.divider()
    st.subheader("Filtres stratégiques")

    recherche = st.text_input("🔍 Rechercher un ticker ou une société :", placeholder="ex: AAPL, Apple, XLK...")

    indices_dispo = ["Tous"] + sorted(univers_df["indice"].unique().tolist())
    filtre_indice = st.selectbox("Indice / Type :", indices_dispo)

    secteur = st.selectbox("Secteur économique (liste core) :", ["Tous"] + list(utils.dict_secteurs.keys()))

    st.caption(f"Univers total : {len(univers_df)} tickers (S&P 500 + Nasdaq 100 + ETFs)")

market_clean = data["market_data_clean"]

if market_clean.empty:
    st.warning("Aucune donnée de marché disponible.")
else:
    df_prix = market_clean.groupby("symbol").last().reset_index()

    cols_market = ["symbol", "close", "rsi_14", "mom_5j", "mom_20j", "volatility", "macd_diff"]
    df_prix = df_prix[[c for c in cols_market if c in df_prix.columns]]
    df_prix = df_prix.rename(columns={
        "symbol": "Ticker",
        "close": "Dernier Prix",
        "rsi_14": "RSI 14",
        "mom_5j": "Mom. 5j (%)",
        "mom_20j": "Mom. 20j (%)",
        "volatility": "Volatilité",
        "macd_diff": "MACD Diff",
    })

    if "Mom. 5j (%)" in df_prix.columns:
        df_prix["Mom. 5j (%)"] = (df_prix["Mom. 5j (%)"] * 100).round(2)
    if "Mom. 20j (%)" in df_prix.columns:
        df_prix["Mom. 20j (%)"] = (df_prix["Mom. 20j (%)"] * 100).round(2)

    # Jointure avec l'univers (nom, secteur GICS, indice d'appartenance)
    univers_renamed = univers_df.rename(columns={"symbol": "Ticker", "nom": "Nom", "secteur": "Secteur GICS", "indice": "Indice"})
    df = univers_renamed.merge(df_prix, on="Ticker", how="inner")

    # Fondamentaux Alpha Vantage — disponibles seulement pour la liste "core" suivie activement
    fonda = data["fonda_data_clean"]
    if not fonda.empty:
        f = fonda.rename(columns={
            "symbol": "Ticker", "roe": "ROE (%)",
            "margin": "Marge Op. (%)", "ev_ebitda": "EV/EBITDA",
        })
        df = df.merge(f[["Ticker", "ROE (%)", "Marge Op. (%)", "EV/EBITDA"]], on="Ticker", how="left")

    # --- Filtres ---
    if recherche:
        df = universe.search_tickers(recherche, df.rename(columns={"Ticker": "symbol", "Nom": "nom"})) \
                       .rename(columns={"symbol": "Ticker", "nom": "Nom"})
    if filtre_indice != "Tous":
        df = df[df["Indice"] == filtre_indice]
    if secteur != "Tous":
        tickers_sec = utils.dict_secteurs[secteur]
        df = df[df["Ticker"].isin(tickers_sec)]

    st.caption(f"{len(df)} résultat(s)")
    st.dataframe(df.round(2), use_container_width=True, hide_index=True, height=560)
