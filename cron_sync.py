# cron_sync.py
# ==============================================================================
# SCRIPT DE SYNCHRONISATION AUTOMATIQUE — exécuté par GitHub Actions (CRON)
# Réutilise data_pipeline.py / db.py / fred.py / universe.py TELS QUELS (mêmes
# fonctions que l'app Streamlit), mais hors serveur : on remplace le module
# `streamlit` par un shim minimaliste (_st_shim.py) AVANT tout import, pour que
# les appels st.cache_data / st.secrets / st.progress / etc. ne plantent pas
# en l'absence de contexte serveur.
#
# Objectif : rafraîchir Supabase en arrière-plan, indépendamment des visites
# sur l'app — l'app Streamlit ne fait plus alors que LIRE des données à jour.
# ==============================================================================
import sys

# --- Injection du shim AVANT tout import de nos modules internes ---
import _st_shim
sys.modules["streamlit"] = _st_shim

import data_pipeline as dp   # noqa: E402  (import après l'injection du shim, volontaire)
import fred                  # noqa: E402
import universe              # noqa: E402


def main():
    print("[CRON] Démarrage de la synchronisation Thésée...")

    # --- 1. Univers élargi (prix uniquement) ---
    print("[CRON] Récupération de l'univers de tickers (S&P 500 + Nasdaq 100 + ETFs)...")
    univers_df = universe.get_univers_complet()
    tickers_univers = univers_df["symbol"].tolist()
    print(f"[CRON] {len(tickers_univers)} tickers dans l'univers élargi.")

    # --- 2. Pipeline complet (prix, fondamentaux, Z-Score, features, modèle) ---
    print("[CRON] Exécution du pipeline ETL complet (get_all_data)...")
    data = dp.get_all_data(univers_etendu=tickers_univers)
    n_prix = len(data["market_data_raw"]["symbol"].unique()) if not data["market_data_raw"].empty else 0
    print(
        f"[CRON] Terminé — {n_prix} tickers (prix), "
        f"{len(data['fonda_data_clean'])} fondamentaux, "
        f"{len(data['zscore_df'])} Z-Scores, "
        f"accuracy modèle: {data['model_result']['accuracy']}%"
    )

    # --- 3. Spreads de crédit FRED ---
    print("[CRON] Synchronisation des spreads FRED (HY/IG)...")
    spreads = fred.get_spreads_hy_ig()
    if spreads["hy_actuel"] is not None:
        print(f"[CRON] Spread HY actuel : {spreads['hy_actuel']:.0f} pb, IG : {spreads['ig_actuel']:.0f} pb")
    else:
        print("[CRON] Spreads FRED indisponibles (clé manquante ou erreur réseau).")

    print("[CRON] Synchronisation terminée avec succès.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[CRON] ERREUR FATALE : {e}", file=sys.stderr)
        sys.exit(1)
