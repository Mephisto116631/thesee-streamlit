# pages/4_Credit_Bilan.py
# ==============================================================================
# MODULE : CREDIT & BILAN
# ==============================================================================
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from theme import apply_theme
import data_pipeline as dp
import utils

st.set_page_config(page_title="Crédit & Bilan — Thésée", page_icon="🛡️", layout="wide")
apply_theme()

st.title("🛡️ Crédit & Bilan")

if "thesee_data" not in st.session_state:
    st.session_state["thesee_data"] = dp.get_all_data()
data = st.session_state["thesee_data"]

ratings_df = data["ratings_df"].rename(columns={"rating_sp": "rating_sp"}) if not data["ratings_df"].empty else pd.DataFrame(columns=["symbol", "rating_sp"])


def get_rating_cat(rating):
    if rating in ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-"]:
        return "IG"
    if rating in ["NR"]:
        return "NR"
    return "HY"


if not ratings_df.empty:
    ratings_df["rating_cat"] = ratings_df["rating_sp"].apply(get_rating_cat)

# Simulation des spreads (comme dans la version Shiny)
spread_hy_actuel = 400
spread_ig_actuel = 120

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Spread HY", f"{spread_hy_actuel} pb")
with col2:
    st.metric("Spread IG", f"{spread_ig_actuel} pb")
with col3:
    n_ig = len(ratings_df[ratings_df["rating_cat"] == "IG"]) if not ratings_df.empty else 0
    st.metric("Univers IG (S&P)", f"{n_ig} / {len(ratings_df)}")
with col4:
    n_hy = len(ratings_df[ratings_df["rating_cat"] == "HY"]) if not ratings_df.empty else 0
    st.metric("Univers HY (S&P)", f"{n_hy} / {len(ratings_df)}")

st.divider()

col_g, col_d = st.columns([7, 5])

with col_g:
    st.subheader("📈 Historique Spreads")
    rng = np.random.default_rng(seed=42)
    x = pd.date_range(start="2020-01-01", periods=100, freq="W")
    y_hy = rng.normal(400, 20, 100)
    y_ig = rng.normal(120, 10, 100)

    fig, ax = plt.subplots(figsize=(8, 4))
    fig.patch.set_facecolor("#1e293b")
    ax.set_facecolor("#1e293b")
    ax.plot(x, y_hy, color="#e74c3c", label="High Yield (HY)")
    ax.plot(x, y_ig, color="#3498db", label="Investment Grade (IG)")
    ax.fill_between(x, y_ig, y_hy, color="#f39c12", alpha=0.1)
    ax.tick_params(colors="#cbd5e1")
    ax.legend(facecolor="#0f172a", edgecolor="#334155", labelcolor="#ffffff")
    for spine in ax.spines.values():
        spine.set_color("#475569")
    st.pyplot(fig, use_container_width=True)

with col_d:
    st.subheader("🥧 Distribution Ratings S&P")
    if not ratings_df.empty:
        fig, ax = plt.subplots(figsize=(6, 4))
        fig.patch.set_facecolor("#1e293b")
        ax.set_facecolor("#1e293b")
        counts = ratings_df["rating_sp"].value_counts()
        ax.bar(counts.index, counts.values, color="#3498db")
        ax.tick_params(colors="#cbd5e1")
        for spine in ax.spines.values():
            spine.set_color("#475569")
        st.pyplot(fig, use_container_width=True)
    else:
        st.info("Aucune donnée de rating disponible.")

st.divider()
st.subheader("📋 Tableau Crédit & Bilan")

with st.sidebar:
    st.subheader("Filtres Crédit")
    filtre_secteur = st.selectbox("Secteur :", ["Tous"] + list(utils.dict_secteurs.keys()), key="credit_secteur")
    filtre_cat = st.selectbox("Catégorie :", ["Tous", "IG", "HY"], key="credit_cat")
    st.caption("Z-Score proxy Altman calculé depuis Alpha Vantage.")

fonda = data["fonda_data_clean"]
market = data["market_data_raw"]

if not ratings_df.empty:
    df_fonda = fonda.copy() if not fonda.empty else pd.DataFrame(columns=["symbol", "roe", "ev_ebitda", "debt_eq", "margin"])
    df_market = market.groupby("symbol").last().reset_index()[["symbol", "close"]] if not market.empty else pd.DataFrame(columns=["symbol", "close"])

    df = ratings_df.merge(df_fonda, on="symbol", how="left").merge(df_market, on="symbol", how="left")
    df["Entreprise"] = df["symbol"].map(utils.dict_noms)
    df["Secteur"] = df["symbol"].apply(lambda x: next((k for k, v in utils.dict_secteurs.items() if x in v), "Inconnu"))
    df["Z-Score"] = np.where(df["debt_eq"] > 0, (df["margin"] * 5) / df["debt_eq"], 3.0)
    df["Rating_full"] = df["rating_sp"] + " (" + df["rating_cat"] + ")"

    if filtre_secteur != "Tous":
        df = df[df["Secteur"] == filtre_secteur]
    if filtre_cat != "Tous":
        df = df[df["rating_cat"] == filtre_cat]

    res = df[["symbol", "Entreprise", "Secteur", "Rating_full", "Z-Score", "debt_eq", "margin", "close"]].copy()
    res.columns = ["Ticker", "Entreprise", "Secteur", "Rating S&P", "Z-Score", "D/E", "Marge Op%", "Prix ($)"]
    st.dataframe(res.round(2), use_container_width=True, hide_index=True)
else:
    st.info("Table des ratings vide — vérifie la table `ratings_sp` dans Supabase.")
