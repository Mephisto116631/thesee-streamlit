# pages/3_Audit_IA.py
# ==============================================================================
# MODULE : EXPLICABILITE IA (SHAP)
# ==============================================================================
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import shap
from theme import apply_theme
import data_pipeline as dp

st.set_page_config(page_title="Audit IA — Thésée", page_icon="🧠", layout="wide")
apply_theme()

st.title("🧠 Audit Intelligence Artificielle")

if "thesee_data" not in st.session_state:
    st.session_state["thesee_data"] = dp.get_all_data()
data = st.session_state["thesee_data"]

DICT_FEATURES_NOMS = {
    "daily_return": "Rendement Quotidien", "pct_vs_ma50": "Écart Moyenne 50j",
    "macd_diff": "Convergence MACD", "mom_5j": "Momentum Court (5j)",
    "mom_20j": "Momentum Moyen (20j)", "vol_relative": "Volume Relatif",
    "rsi_14": "Indice de Force RSI", "volatility": "Volatilité Vol (20j)",
    "vix_regime": "Régime Macro VIX", "rsi_rank_sec": "Force Relative Sectorielle",
}

market_clean = data["market_data_clean"]
model_result = data["model_result"]
model_ia = data["model_ia"]

with st.sidebar:
    st.subheader("Audit Intelligence Artificielle")
    tickers_dispo = sorted(market_clean["symbol"].unique().tolist()) if not market_clean.empty else []
    ticker = st.selectbox("Sélectionner un actif pour audit :", tickers_dispo) if tickers_dispo else None
    st.caption("Interprétation mathématique fine de la structure de décision du modèle.")


def get_shap_data(ticker):
    if not ticker or model_ia is None:
        return None
    row = market_clean[market_clean["symbol"] == ticker].tail(1)
    X_raw = row[model_result["features"]].values
    X_sc = model_result["scaler"].transform(model_result["imputer"].transform(X_raw))
    explainer = shap.TreeExplainer(model_ia)
    shap_values = explainer(X_sc)

    df = pd.DataFrame({
        "Indicateur": [DICT_FEATURES_NOMS.get(f, f) for f in model_result["features"]],
        "Valeur Observée": np.round(X_raw[0], 4),
        "Impact sur le Signal": np.round(shap_values.values[0], 4),
    }).sort_values("Impact sur le Signal", key=abs, ascending=False)

    shap_values.feature_names = [DICT_FEATURES_NOMS.get(f, f) for f in model_result["features"]]
    return {"df": df, "shap_obj": shap_values[0]}


col1, col2 = st.columns([1, 1])

shap_data = get_shap_data(ticker) if ticker else None

with col1:
    st.subheader("Vecteurs de Données et Impacts SHAP")
    if shap_data:
        st.dataframe(shap_data["df"], use_container_width=True, hide_index=True)
    else:
        st.info("Sélectionne un actif dans la barre latérale.")

with col2:
    st.subheader("Décomposition des Forces Locales (Waterfall)")
    if shap_data:
        plt.style.use("dark_background")
        fig, ax = plt.subplots(figsize=(8, 5))
        fig.patch.set_facecolor("#1e293b")
        ax.set_facecolor("#1e293b")
        shap.plots.waterfall(shap_data["shap_obj"], show=False)
        for t in plt.gcf().findobj(plt.Text):
            t.set_color("#f8fafc")
        st.pyplot(fig, use_container_width=True)
    else:
        st.info("En attente d'une sélection.")

st.subheader("Hiérarchie Globale des Métriques Prédictives")
importance_df = data["importance_df"]
if not importance_df.empty:
    importance = importance_df.copy()
    importance["Feature"] = importance["Feature"].map(DICT_FEATURES_NOMS)

    plt.style.use("dark_background")
    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor("#1e293b")
    ax.set_facecolor("#1e293b")
    ax.barh(importance["Feature"], importance["Importance"], color="#3b82f6")
    ax.tick_params(colors="#cbd5e1")
    st.pyplot(fig, use_container_width=True)
else:
    st.info("Modèle non entraîné — données insuffisantes.")
