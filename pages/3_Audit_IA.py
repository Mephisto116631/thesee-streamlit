# pages/3_Audit_IA.py
# ==============================================================================
# MODULE : EXPLICABILITE IA (SHAP)
# ==============================================================================
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import shap
from theme import apply_theme, palette_selector_sidebar
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
    "roe": "ROE", "margin": "Marge Opérationnelle",
    "ev_ebitda": "EV/EBITDA", "debt_eq": "Dette/Capitaux Propres",
}

market_clean = data["market_data_clean"]
model_result = data["model_result"]
model_ia = data["model_ia"]
diag = model_result.get("diagnostics")

with st.sidebar:
    palette_selector_sidebar()
    st.divider()
    st.subheader("Audit Intelligence Artificielle")
    tickers_dispo = sorted(market_clean["symbol"].unique().tolist()) if not market_clean.empty else []
    ticker = st.selectbox("Sélectionner un actif pour audit :", tickers_dispo) if tickers_dispo else None
    st.caption("Interprétation mathématique fine de la structure de décision du modèle.")

# ------------------------------------------------------------------------------
# SECTION DIAGNOSTIC — la question centrale : le modèle apprend-il un vrai signal ?
# ------------------------------------------------------------------------------
st.subheader("📊 Diagnostic du modèle")

if diag is None:
    st.warning("Diagnostics indisponibles — modèle non entraîné ou données insuffisantes.")
else:
    # Le chiffre qui compte le plus : le modèle bat-il une baseline naïve
    # (toujours prédire la classe majoritaire) ? Si non, il n'apprend rien.
    delta = diag["amelioration_vs_baseline"]
    if delta <= 0:
        st.error(
            f"⚠️ Le modèle ({diag['accuracy']}%) ne bat PAS la baseline naïve "
            f"({diag['baseline_accuracy']}%, qui prédit toujours la classe majoritaire). "
            "Il n'a probablement appris aucun signal exploitable sur cette période."
        )
    elif delta < 2:
        st.warning(
            f"Le modèle ({diag['accuracy']}%) ne bat que très légèrement la baseline "
            f"({diag['baseline_accuracy']}%). Gain de {delta} points — reste dans la marge du bruit."
        )
    else:
        st.success(
            f"Le modèle ({diag['accuracy']}%) bat la baseline naïve "
            f"({diag['baseline_accuracy']}%) de {delta} points."
        )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Accuracy", f"{diag['accuracy']}%", f"{delta:+.1f} pts vs baseline")
    col2.metric("Précision", f"{diag['precision']}%", help="Parmi les hausses prédites, combien étaient réelles")
    col3.metric("Rappel", f"{diag['recall']}%", help="Parmi les vraies hausses, combien ont été détectées")
    col4.metric("ROC AUC", f"{diag['roc_auc']}%" if diag["roc_auc"] else "N/A",
                help="50% = hasard, 100% = discrimination parfaite")

    with st.expander("Détails techniques (matrice de confusion, répartition des classes)"):
        cm = diag["confusion_matrix"]
        st.markdown(f"""
        **Matrice de confusion** (sur {diag['n_test']} observations de test) :

        |                    | Prédit Baisse | Prédit Hausse |
        |--------------------|:---:|:---:|
        | **Réel Baisse**    | {cm[0][0]} | {cm[0][1]} |
        | **Réel Hausse**    | {cm[1][0]} | {cm[1][1]} |

        **Répartition des classes** — révèle un biais structurel du marché :
        - Train : {diag['taux_hausse_train']}% de hausses
        - Test : {diag['taux_hausse_test']}% de hausses
        - Taille : {diag['n_train']} obs. train / {diag['n_test']} obs. test
        - {diag['n_exclus_zone_neutre']} observations exclues (mouvement < {diag['seuil_neutre']*100:.1f}%, zone neutre trop bruitée)
        """)
        if abs(diag["taux_hausse_train"] - 50) > 10:
            st.caption(
                "⚠️ Le marché monte nettement plus souvent qu'il ne baisse sur la période "
                "d'entraînement — le modèle est pondéré (scale_pos_weight) pour compenser ce biais."
            )

    # --- Log loss & Brier score : qualité des probabilités, pas juste du 0/1 ---
    st.markdown("##### Qualité des probabilités (log loss / Brier score)")
    lc1, lc2 = st.columns(2)
    delta_logloss = round(diag["logloss_baseline"] - diag["logloss_modele"], 4)
    lc1.metric(
        "Log loss du modèle", diag["logloss_modele"],
        f"{delta_logloss:+.4f} vs baseline ({diag['logloss_baseline']})",
        help="Plus bas = mieux. Pénalise les prédictions confiantes et fausses.",
    )
    lc2.metric(
        "Brier score", diag["brier_score"],
        help="Plus bas = mieux (0 = parfait, 0.25 = équivalent à toujours prédire 50%).",
    )
    if delta_logloss <= 0:
        st.caption("⚠️ Le log loss du modèle est pire que la baseline constante — ses probabilités sont peu fiables.")

    # --- Calibration ---
    if diag["calibration_bins"]:
        st.markdown("##### Calibration (proba prédite vs taux réel observé)")
        calib_df = pd.DataFrame(diag["calibration_bins"])
        calib_df.columns = ["Tranche de proba", "Proba moyenne prédite (%)", "Taux réel observé (%)", "N observations"]
        st.dataframe(calib_df, use_container_width=True, hide_index=True)
        st.caption("Un modèle bien calibré a une proba prédite proche du taux réellement observé dans chaque tranche.")

    # --- Performance par régime de marché ---
    if diag["perf_par_regime"]:
        st.markdown("##### Performance par régime de marché (VIX)")
        regime_df = pd.DataFrame(diag["perf_par_regime"])
        regime_df.columns = ["Régime", "Accuracy (%)", "N observations"]
        st.dataframe(regime_df, use_container_width=True, hide_index=True)

    # --- Performance par ticker ---
    if diag["perf_par_ticker"]:
        with st.expander("Performance détaillée par ticker"):
            ticker_df = pd.DataFrame(diag["perf_par_ticker"])
            ticker_df.columns = ["Ticker", "Accuracy (%)", "N observations"]
            st.dataframe(ticker_df, use_container_width=True, hide_index=True)

    # --- Walk-forward validation : stabilité dans le temps ---
    wf = diag.get("walk_forward")
    if wf and wf.get("fenetres"):
        st.markdown("##### Walk-forward validation (stabilité dans le temps)")
        st.caption(
            f"Accuracy moyenne sur {len(wf['fenetres'])} fenêtres temporelles indépendantes : "
            f"**{wf['accuracy_moyenne']}% ± {wf['accuracy_ecart_type']}**"
        )
        wf_df = pd.DataFrame(wf["fenetres"])
        wf_df = wf_df.rename(columns={
            "fenetre": "Fenêtre", "date_debut": "Début", "date_fin": "Fin",
            "accuracy": "Accuracy (%)", "n_test": "N test",
        })
        st.dataframe(wf_df, use_container_width=True, hide_index=True)
        if wf["accuracy_ecart_type"] and wf["accuracy_ecart_type"] > 8:
            st.caption(
                "⚠️ Écart-type élevé entre fenêtres — l'accuracy fluctue beaucoup selon la "
                "période testée, ce qui suggère un signal instable plutôt qu'un edge stable."
            )

st.divider()


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
