# app.py
# ==============================================================================
# THESEE — TERMINAL QUANTAMENTAL (Streamlit + Supabase)
# Page d'accueil. Les modules sont dans pages/ (navigation auto Streamlit).
# ==============================================================================
import streamlit as st
from theme import apply_theme, palette_selector_sidebar
import data_pipeline as dp
import universe

st.set_page_config(
    page_title="Thésée — Terminal Quantamental",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

with st.sidebar:
    palette_selector_sidebar()
    st.divider()

apply_theme()

st.title("📈 Thésée — Terminal Quantamental")
st.caption("Screener, Portefeuille, Audit IA, Crédit & Bilan — univers S&P 500 + Nasdaq 100 + ETFs")

# Univers élargi (prix uniquement) — utilisé par le Screener pour la recherche
univers_df = universe.get_univers_complet()
tickers_univers = univers_df["symbol"].tolist()

data = dp.get_all_data(univers_etendu=tickers_univers)
st.session_state["thesee_data"] = data
st.session_state["thesee_univers"] = univers_df

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Titres suivis (prix)", len(data["market_data_raw"]["symbol"].unique()) if not data["market_data_raw"].empty else 0)
with col2:
    st.metric("Précision modèle IA", f"{data['model_result']['accuracy']:.1f}%")
with col3:
    st.metric("Fondamentaux à jour", len(data["fonda_data_clean"]))
with col4:
    st.metric("Univers disponible", len(univers_df))

st.divider()
st.markdown(
    """
    Utilise le menu de navigation à gauche pour accéder aux modules :

    - **📊 Screener** — recherche sur l'univers élargi (S&P 500 + Nasdaq 100 + ETFs), filtres sectoriels
    - **💼 Portefeuille** — optimisation Markowitz et simulation Monte-Carlo
    - **🧠 Audit IA** — explicabilité SHAP du modèle XGBoost
    - **🛡️ Crédit & Bilan** — ratings S&P, Z-Score Altman réel, spreads de crédit FRED
    """
)
