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

# Lecture seule : le CRON GitHub Actions télécharge les prix, entraîne les modèles
# et publie les résultats dans Supabase. L'app n'entraîne plus rien.
univers_df = universe.get_univers_complet()
data = dp.get_app_data()
st.session_state["thesee_data"] = data
st.session_state["thesee_univers"] = univers_df

meta = data.get("meta") or {}
diag = (data.get("model_result") or {}).get("diagnostics")
if not meta:
    st.warning("Aucun résultat publié pour l'instant : lance le workflow « sync » (GitHub → Actions → Run workflow).")
else:
    st.caption(f"Données au {meta.get('date_donnees', '?')} · dernière synchronisation (UTC) : "
               f"{str(meta.get('synchro_utc', '?'))[:16].replace('T', ' ')}")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Titres suivis (prix)", int(meta.get("n_symboles", 0)))
with col2:
    if diag:
        st.metric("Précision modèle IA", f"{diag['accuracy']:.1f}%",
                  f"{diag['amelioration_vs_baseline']:+.1f} pts vs baseline")
    else:
        st.metric("Précision modèle IA", "N/A")
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
