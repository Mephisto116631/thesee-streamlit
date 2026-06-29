# app.py
# ==============================================================================
# THESEE — TERMINAL QUANTAMENTAL (Streamlit + Supabase)
# Page d'accueil. Les modules sont dans pages/ (navigation auto Streamlit).
# ==============================================================================
import streamlit as st
from theme import apply_theme
import data_pipeline as dp

st.set_page_config(
    page_title="Thésée — Terminal Quantamental",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()

st.title("📈 Thésée — Terminal Quantamental")
st.caption("Migration Streamlit + Supabase — Screener, Portefeuille, Audit IA, Crédit & Bilan")

with st.spinner("Initialisation du pipeline de données..."):
    data = dp.get_all_data()
    st.session_state["thesee_data"] = data

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Titres suivis", len(data["market_data_raw"]["symbol"].unique()) if not data["market_data_raw"].empty else 0)
with col2:
    st.metric("Précision modèle IA", f"{data['model_result']['accuracy']:.1f}%")
with col3:
    st.metric("Fondamentaux à jour", len(data["fonda_data_clean"]))

st.divider()
st.markdown(
    """
    Utilise le menu de navigation à gauche pour accéder aux modules :

    - **📊 Screener** — vue d'ensemble des titres et filtres sectoriels
    - **💼 Portefeuille** — optimisation Markowitz et simulation Monte-Carlo
    - **🧠 Audit IA** — explicabilité SHAP du modèle XGBoost
    - **🛡️ Crédit & Bilan** — ratings S&P, Z-Score, spreads de crédit
    """
)
