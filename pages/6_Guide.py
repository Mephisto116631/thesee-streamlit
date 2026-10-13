# pages/6_Guide.py
# ==============================================================================
# MODULE : GUIDE UTILISATEUR — documentation de Thésée (portage de mod_guide.R)
# ==============================================================================
import streamlit as st
import pandas as pd
from theme import apply_theme, palette_selector_sidebar
from glossaire import FICHES, render_fiche

st.set_page_config(page_title="Guide — Thésée", page_icon="📖", layout="wide")
apply_theme()

with st.sidebar:
    palette_selector_sidebar()

st.title("📖 Guide utilisateur")


def grille_fiches(cles: list[str], colonnes: int = 3):
    """Affiche des fiches côte à côte, chacune dans un expander."""
    cols = st.columns(colonnes)
    for i, cle in enumerate(cles):
        with cols[i % colonnes]:
            with st.expander(f"ℹ️ {FICHES[cle]['titre']}"):
                render_fiche(cle)


tab_start, tab_ind, tab_ia, tab_credit, tab_tech = st.tabs([
    "🚀 Démarrage", "📊 Indicateurs", "🧠 Modèles IA", "🛡️ Crédit & Bilan", "⚙️ Données & architecture",
])

# ------------------------------------------------------------------------------
with tab_start:
    st.subheader("Qu'est-ce que Thésée ?")
    st.write(
        "Terminal d'analyse quantamentale sur un univers élargi (S&P 500, Nasdaq-100 et ETFs). "
        "Il combine des prix de marché (Yahoo Finance), des fondamentaux (Alpha Vantage), "
        "des spreads de crédit (FRED) et des modèles XGBoost, pour screener des titres, "
        "construire un portefeuille et auditer honnêtement le pouvoir prédictif des modèles."
    )

    st.subheader("Les pages")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**📊 Screener**")
        st.caption("Recherche d'un ticker ou d'une société, filtre par indice et secteur, "
                   "indicateurs techniques et fondamentaux.")
        st.markdown("**💼 Portefeuille**")
        st.caption("Pondération équipondérée ou Markowitz, simulation Monte-Carlo sur 252 jours.")
    with c2:
        st.markdown("**🤖 Audit IA**")
        st.caption("Diagnostic honnête du modèle actions : baseline, log loss, calibration, "
                   "walk-forward, SHAP, comparaison des seuils, modèle relatif et IC.")
        st.markdown("**🛡️ Crédit & Bilan**")
        st.caption("Z-Score d'Altman, ratings, spreads HY et IG issus de FRED.")
    with c3:
        st.markdown("**🌐 Audit ETF**")
        st.caption("Modèle séparé pour les ETFs : écart à l'indice de référence, dollar-volume relatif.")
        st.markdown("**📖 Guide**")
        st.caption("Vous êtes ici. Les boutons ℹ️ des autres pages ouvrent les mêmes fiches.")

    st.subheader("Workflow recommandé")
    st.markdown(
        "1. **Screener** — repérez des titres selon leurs indicateurs techniques et fondamentaux.\n"
        "2. **Crédit & Bilan** — vérifiez le Z-Score et le contexte de crédit (spreads).\n"
        "3. **Portefeuille** — choisissez 5 à 12 titres, testez Markowitz et la simulation.\n"
        "4. **Audit IA** — avant de faire confiance à un signal, vérifiez qu'il bat la baseline "
        "et que l'IC est stable dans le temps."
    )
    st.info("Le but de l'audit est de mesurer ce que les modèles savent faire, pas de leur faire dire "
            "ce qu'on voudrait. Un modèle qui ne bat pas sa baseline est signalé comme tel.")

# ------------------------------------------------------------------------------
with tab_ind:
    st.subheader("Indicateurs techniques")
    grille_fiches(["rsi_14", "pct_vs_ma50", "macd_diff", "mom_5j", "mom_20j", "mom_60j",
                   "mom_12_1", "volatility", "vol_relative"])
    st.subheader("Macro et crédit de marché")
    grille_fiches(["vix_regime", "rsi_rank_sec", "spread_hy", "spread_ig"], colonnes=2)
    st.subheader("Fondamentaux")
    grille_fiches(["roe", "margin", "ev_ebitda", "debt_eq"], colonnes=2)
    st.subheader("Spécifiques aux ETFs")
    grille_fiches(["tracking_vs_ref", "dollar_volume_relatif"], colonnes=2)

# ------------------------------------------------------------------------------
with tab_ia:
    st.subheader("Trois modèles XGBoost")
    st.dataframe(pd.DataFrame([
        {"Modèle": "Actions (jour)", "Cible": "Hausse demain, hors zone neutre",
         "Features": "Techniques + vix_regime + rsi_rank_sec + 4 fondamentaux"},
        {"Modèle": "Actions (relatif)", "Cible": "Bat la médiane de l'univers sur 5 jours",
         "Features": "Rangs cross-sectionnels par date (momentum 5/20/60j, 12-1, volume relatif, RSI...)"},
        {"Modèle": "ETF", "Cible": "Hausse demain, hors zone neutre",
         "Features": "Techniques + tracking vs indice de référence + dollar-volume relatif"},
    ]), use_container_width=True, hide_index=True)

    st.subheader("Comment lire les métriques")
    grille_fiches(["accuracy", "roc_auc", "logloss", "ic", "walk_forward", "zone_neutre", "cible_relative"])

    st.subheader("Que vaut une accuracy ?")
    st.dataframe(pd.DataFrame([
        {"Écart à la baseline": "≤ 0 pt", "Lecture": "Le modèle n'apprend rien d'exploitable"},
        {"Écart à la baseline": "0 à 2 pts", "Lecture": "Dans la marge du bruit"},
        {"Écart à la baseline": "2 à 5 pts, stable entre fenêtres", "Lecture": "Signal plausible, à confirmer par l'IC"},
        {"Écart à la baseline": "> 8 pts", "Lecture": "Suspect : chercher une fuite d'information (data leakage)"},
    ]), use_container_width=True, hide_index=True)
    st.write(
        "Les marchés sont adaptatifs : un signal exploitable est vite arbitré. Sur des données "
        "quotidiennes, des ICs de 0,01 à 0,03 sont réalistes. Une accuracy de 70 % durable serait "
        "bien plus probablement un défaut de méthode qu'une découverte."
    )

    st.subheader("Garde-fous méthodologiques")
    st.markdown(
        "- **Split temporel** par date de coupure unique : jamais de test sur une période déjà vue.\n"
        "- **Embargo de 5 jours** pour la cible à 5 jours (évite le chevauchement train/test).\n"
        "- **Baseline naïve** et **log loss** de référence systématiques.\n"
        "- **Walk-forward** sur 5 fenêtres pour juger la stabilité.\n"
        "- **Fondamentaux = instantanés actuels** appliqués à tout l'historique : risque de légère "
        "surestimation si l'edge vient surtout de ces colonnes.\n"
        "- **Biais de survie** : l'univers est composé des membres actuels des indices."
    )

# ------------------------------------------------------------------------------
with tab_credit:
    st.subheader("Principes")
    st.write(
        "L'analyse crédit évalue la capacité d'une entreprise à rembourser ses dettes. Elle complète "
        "l'analyse technique (court terme) et fondamentale (valorisation) par une dimension de risque "
        "de défaut : un titre peut avoir un bon momentum et un bilan fragile."
    )
    grille_fiches(["zscore", "rating_sp", "debt_eq", "margin", "spread_hy", "spread_ig"])

    st.subheader("Zones du Z-Score")
    st.dataframe(pd.DataFrame([
        {"Z-Score": "> 2,99", "Zone": "Sûre"},
        {"Z-Score": "1,81 à 2,99", "Zone": "Grise"},
        {"Z-Score": "< 1,81", "Zone": "Détresse"},
    ]), use_container_width=True, hide_index=True)

    st.subheader("Échelle des ratings S&P")
    st.dataframe(pd.DataFrame([
        {"Catégorie": "Investment Grade", "Notes": "AAA, AA+, AA, AA−, A+, A, A−, BBB+, BBB, BBB−"},
        {"Catégorie": "High Yield (spéculatif)", "Notes": "BB+, BB, BB−, B+, B, B−, CCC et en dessous"},
    ]), use_container_width=True, hide_index=True)

# ------------------------------------------------------------------------------
with tab_tech:
    st.subheader("Sources de données")
    st.dataframe(pd.DataFrame([
        {"Donnée": "Prix OHLCV (univers élargi)", "Source": "Yahoo Finance (yfinance)", "Fréquence": "3 fois par jour (CRON)"},
        {"Donnée": "VIX, SPY", "Source": "Yahoo Finance", "Fréquence": "3 fois par jour (CRON)"},
        {"Donnée": "Fondamentaux", "Source": "Alpha Vantage OVERVIEW", "Fréquence": "TTL 7 jours"},
        {"Donnée": "Z-Score d'Altman", "Source": "Alpha Vantage BALANCE_SHEET + INCOME_STATEMENT", "Fréquence": "TTL 7 jours"},
        {"Donnée": "Spreads HY / IG", "Source": "FRED", "Fréquence": "Quotidienne"},
        {"Donnée": "Univers S&P 500 / Nasdaq-100 / ETFs", "Source": "CSV GitHub datasets, Wikipedia, liste statique", "Fréquence": "À chaque chargement"},
    ]), use_container_width=True, hide_index=True)

    st.subheader("Persistance et cache")
    st.markdown(
        "- **Supabase** (PostgreSQL) est la source de vérité : prix, macro, fondamentaux, Z-Scores, spreads.\n"
        "- **GitHub Actions** (CRON, jours ouvrés) rafraîchit Supabase indépendamment des visites : "
        "l'app ne fait que lire des données à jour.\n"
        "- **Cache Streamlit** de 1 heure pour les lectures ; modèles entraînés mis en cache par jeu de données."
    )

    st.subheader("Stack")
    st.markdown("Python 3.11 · Streamlit · pandas · XGBoost · scikit-learn · SHAP · Supabase · yfinance · Alpha Vantage · FRED")

    st.subheader("Limites connues")
    st.markdown(
        "- Alpha Vantage (plan gratuit) : quota strict et pause de 13 s entre appels, donc les fondamentaux "
        "ne portent que sur la liste « core » de 12 titres.\n"
        "- Ratings S&P renseignés manuellement.\n"
        "- Liste Nasdaq-100 : repli statique si la source en ligne est indisponible.\n"
        "- Aucune de ces données ne constitue un conseil en investissement."
    )
