# pages/3_Audit_IA.py
# ==============================================================================
# MODULE : EXPLICABILITE IA (SHAP)
# ==============================================================================
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import shap
from theme import apply_theme, palette_selector_sidebar, get_active_palette
from glossaire import info_button
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

    bi1, bi2, bi3, bi4, _ = st.columns([1, 1, 1, 1, 6])
    with bi1: info_button("accuracy")
    with bi2: info_button("roc_auc")
    with bi3: info_button("logloss")
    with bi4: info_button("zone_neutre")

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

    with st.expander("🔬 Comparer différents seuils de zone neutre"):
        st.caption(
            "Teste plusieurs seuils d'exclusion des mouvements faibles pour voir "
            "lequel maximise le delta vs baseline sur tes données réelles actuelles. "
            "Entraîne plusieurs modèles — prend quelques secondes à ~1 minute."
        )
        if st.button("Lancer la comparaison", key="btn_comparer_seuils"):
            with st.spinner("Entraînement de plusieurs modèles avec différents seuils..."):
                comparaison = dp.comparer_seuils_neutres(
                    market_clean, model_result["features"],
                    seuils=[0.001, 0.003, 0.005, 0.01, 0.015, 0.02],
                )
            if not comparaison.empty:
                comp_display = comparaison.rename(columns={
                    "seuil_pct": "Seuil (%)", "accuracy": "Accuracy (%)",
                    "baseline_accuracy": "Baseline (%)", "delta_vs_baseline": "Delta (pts)",
                    "roc_auc": "ROC AUC (%)", "n_train": "N train", "n_test": "N test",
                    "n_exclus": "N exclus",
                })
                st.dataframe(comp_display, use_container_width=True, hide_index=True)
                meilleur = comparaison.iloc[0]
                st.caption(
                    f"Meilleur seuil testé : {meilleur['seuil_pct']}% "
                    f"(delta {meilleur['delta_vs_baseline']:+.1f} pts vs baseline). "
                    "Si tous les deltas restent proches de 0 ou négatifs, le seuil n'est "
                    "pas le facteur limitant — le signal manque plutôt côté features/données."
                )
                if meilleur["n_test"] < 200:
                    st.caption(
                        f"⚠️ Attention : ce résultat repose sur seulement {meilleur['n_test']} "
                        "observations de test. Un échantillon aussi petit peut donner un delta "
                        "élevé par pur hasard statistique — méfiance avant de le considérer fiable."
                    )
            else:
                st.warning("Comparaison impossible — données insuffisantes.")

# ------------------------------------------------------------------------------
# MODELE RELATIF — cible : battre la médiane de l'univers sur 5 jours
# ------------------------------------------------------------------------------
st.subheader("🎯 Modèle relatif (cross-sectionnel, 5 jours)")
res_rel = data.get("model_result_relatif")
diag_rel = res_rel.get("diagnostics") if res_rel else None

if diag_rel is None:
    st.info("Modèle relatif indisponible — historique insuffisant (≥ 1 an requis pour mom_12_1).")
else:
    st.caption(
        "Cible : le titre bat-il la médiane de l'univers sur les 5 prochains jours ? "
        "Features en rang percentile par date, embargo de 5 jours entre train et test. "
        "Retire l'effet de marché commun, qui domine la cible « hausse demain »."
    )
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("IC moyen", f"{diag_rel['ic_moyen']}" if diag_rel["ic_moyen"] is not None else "N/A",
              help="Corrélation de rang par date entre proba prédite et rendement réalisé. "
                   "0.02-0.05 = signal exploitable en pratique.")
    c2.metric("t-stat IC", f"{diag_rel['ic_t']}" if diag_rel["ic_t"] is not None else "N/A",
              help="|t| > 2 = significatif (hors chevauchement des fenêtres à 5 jours).")
    c3.metric("ROC AUC", f"{diag_rel['roc_auc']}%" if diag_rel["roc_auc"] else "N/A")
    c4.metric("Log loss", f"{diag_rel['logloss_modele']}",
              f"{diag_rel['logloss_modele'] - diag_rel['logloss_baseline']:+.4f} vs baseline",
              delta_color="inverse")
    bj1, bj2, bj3, _ = st.columns([1, 1, 1, 7])
    with bj1: info_button("ic")
    with bj2: info_button("cible_relative")
    with bj3: info_button("walk_forward")
    wf_rel = diag_rel.get("walk_forward") or {}
    if wf_rel.get("accuracy_moyenne") is not None:
        st.caption(
            f"Walk-forward : accuracy moyenne {wf_rel['accuracy_moyenne']}% "
            f"(± {wf_rel['accuracy_ecart_type']} pt sur {len(wf_rel['fenetres'])} fenêtres) — "
            f"{diag_rel['n_test']} observations de test sur {diag_rel['ic_n_jours']} jours."
        )
    if diag_rel["logloss_modele"] >= diag_rel["logloss_baseline"]:
        st.warning("Log loss ≥ baseline : les probabilités ne valent pas un simple taux de base. "
                   "Se fier à l'IC et à sa stabilité dans le temps, pas à l'accuracy.")

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
        fig.patch.set_facecolor(get_active_palette()["card"])
        ax.set_facecolor(get_active_palette()["card"])
        shap.plots.waterfall(shap_data["shap_obj"], show=False)
        for t in plt.gcf().findobj(plt.Text):
            t.set_color(get_active_palette()["text"])
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
    fig.patch.set_facecolor(get_active_palette()["card"])
    ax.set_facecolor(get_active_palette()["card"])
    ax.barh(importance["Feature"], importance["Importance"], color=get_active_palette()["accent"])
    ax.tick_params(colors=get_active_palette()["text_muted"])
    st.pyplot(fig, use_container_width=True)
else:
    st.info("Modèle non entraîné — données insuffisantes.")
