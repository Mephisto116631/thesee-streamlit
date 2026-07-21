# pages/4_Credit_Bilan.py
# ==============================================================================
# MODULE : CREDIT & BILAN — Z-Score Altman réel + spreads FRED réels
# ==============================================================================
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from theme import apply_theme, palette_selector_sidebar
import data_pipeline as dp
import fred
import utils

st.set_page_config(page_title="Crédit & Bilan — Thésée", page_icon="🛡️", layout="wide")
apply_theme()

st.title("🛡️ Crédit & Bilan")

if "thesee_data" not in st.session_state:
    st.session_state["thesee_data"] = dp.get_all_data()
data = st.session_state["thesee_data"]

ratings_df = data["ratings_df"] if not data["ratings_df"].empty else pd.DataFrame(columns=["symbol", "rating_sp"])


def get_rating_cat(rating):
    if rating in ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-"]:
        return "IG"
    if rating in ["NR"]:
        return "NR"
    return "HY"


if not ratings_df.empty:
    ratings_df["rating_cat"] = ratings_df["rating_sp"].apply(get_rating_cat)

# --- Spreads réels depuis FRED (avec repli si clé absente) ---
spreads = fred.get_spreads_hy_ig()

if spreads["hy_actuel"] is None:
    st.warning(
        "Clé FRED_API_KEY absente ou erreur de récupération — spreads non disponibles. "
        "Ajoute FRED_API_KEY dans tes secrets (https://fredaccount.stlouisfed.org/apikeys, gratuit)."
    )

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Spread HY", f"{spreads['hy_actuel']:.0f} pb" if spreads["hy_actuel"] else "N/A")
with col2:
    st.metric("Spread IG", f"{spreads['ig_actuel']:.0f} pb" if spreads["ig_actuel"] else "N/A")
with col3:
    n_ig = len(ratings_df[ratings_df["rating_cat"] == "IG"]) if not ratings_df.empty else 0
    st.metric("Univers IG (S&P)", f"{n_ig} / {len(ratings_df)}")
with col4:
    n_hy = len(ratings_df[ratings_df["rating_cat"] == "HY"]) if not ratings_df.empty else 0
    st.metric("Univers HY (S&P)", f"{n_hy} / {len(ratings_df)}")

st.divider()

col_g, col_d = st.columns([7, 5])

with col_g:
    st.subheader("📈 Historique Spreads (source : FRED)")
    if not spreads["hy"].empty and not spreads["ig"].empty:
        fig, ax = plt.subplots(figsize=(8, 4))
        fig.patch.set_facecolor("#1e293b")
        ax.set_facecolor("#1e293b")
        ax.plot(spreads["hy"]["date"], spreads["hy"]["valeur"] * 100, color="#e74c3c", label="High Yield (HY)")
        ax.plot(spreads["ig"]["date"], spreads["ig"]["valeur"] * 100, color="#3498db", label="Investment Grade (IG)")
        ax.tick_params(colors="#cbd5e1")
        ax.set_ylabel("Spread (pb)", color="#cbd5e1")
        ax.legend(facecolor="#0f172a", edgecolor="#334155", labelcolor="#ffffff")
        for spine in ax.spines.values():
            spine.set_color("#475569")
        st.pyplot(fig, use_container_width=True)
    else:
        st.info("Données FRED indisponibles — vérifie ta clé FRED_API_KEY.")

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
    palette_selector_sidebar()
    st.divider()
    st.subheader("Filtres Crédit")
    filtre_secteur = st.selectbox("Secteur :", ["Tous"] + list(utils.dict_secteurs.keys()), key="credit_secteur")
    filtre_cat = st.selectbox("Catégorie :", ["Tous", "IG", "HY"], key="credit_cat")
    st.caption("Z-Score Altman réel (5 ratios), calculé depuis les bilans Alpha Vantage.")

fonda = data["fonda_data_clean"]
market = data["market_data_raw"]
zscore_df = data.get("zscore_df", pd.DataFrame())

if not ratings_df.empty:
    df_fonda = fonda.copy() if not fonda.empty else pd.DataFrame(columns=["symbol", "roe", "ev_ebitda", "debt_eq", "margin"])
    df_market = market.groupby("symbol").last().reset_index()[["symbol", "close"]] if not market.empty else pd.DataFrame(columns=["symbol", "close"])
    df_zscore = zscore_df[["symbol", "z_score"]] if not zscore_df.empty else pd.DataFrame(columns=["symbol", "z_score"])

    df = ratings_df.merge(df_fonda, on="symbol", how="left") \
                    .merge(df_market, on="symbol", how="left") \
                    .merge(df_zscore, on="symbol", how="left")

    df["Entreprise"] = df["symbol"].map(utils.dict_noms)
    df["Secteur"] = df["symbol"].apply(lambda x: next((k for k, v in utils.dict_secteurs.items() if x in v), "Inconnu"))
    df["Rating_full"] = df["rating_sp"] + " (" + df["rating_cat"] + ")"

    if filtre_secteur != "Tous":
        df = df[df["Secteur"] == filtre_secteur]
    if filtre_cat != "Tous":
        df = df[df["rating_cat"] == filtre_cat]

    res = df[["symbol", "Entreprise", "Secteur", "Rating_full", "z_score", "debt_eq", "margin", "close"]].copy()
    res.columns = ["Ticker", "Entreprise", "Secteur", "Rating S&P", "Z-Score Altman", "D/E", "Marge Op%", "Prix ($)"]
    st.dataframe(res.round(2), use_container_width=True, hide_index=True)

    st.caption(
        "Zones Z-Score Altman : > 2.99 = zone sûre · 1.81–2.99 = zone grise · < 1.81 = zone de détresse financière."
    )
else:
    st.info("Table des ratings vide — vérifie la table `ratings_sp` dans Supabase.")
