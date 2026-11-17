# cron_sync.py
# ==============================================================================
# SCRIPT DE SYNCHRONISATION AUTOMATIQUE — exécuté par GitHub Actions (CRON)
# Réutilise data_pipeline.py / db.py / fred.py / universe.py hors serveur : on
# remplace le module `streamlit` par un shim (_st_shim.py) AVANT tout import.
#
# Rôle : faire TOUS les calculs (prix, fondamentaux, Z-Score, modèles IA,
# signaux, indicateurs) et écrire dans Supabase des tables prêtes à afficher.
# L'appli mobile et l'app Streamlit ne font plus que LIRE.
# ==============================================================================
import sys
import time

import _st_shim
sys.modules["streamlit"] = _st_shim

import data_pipeline as dp   # noqa: E402  (import après l'injection du shim, volontaire)
import db                    # noqa: E402
import fred                  # noqa: E402
import publish               # noqa: E402
import universe              # noqa: E402


def main(log_id):
    t0 = time.time()
    print("[CRON] Démarrage de la synchronisation Thésée...")

    # --- 1. Univers élargi ---
    univers_df = universe.get_univers_complet()
    tickers_univers = univers_df["symbol"].tolist()
    print(f"[CRON] {len(tickers_univers)} tickers dans l'univers élargi.")

    # --- 2. Pipeline complet en mode écriture (prix incrémentaux, fondamentaux, Z-Score, modèles) ---
    data = dp.get_all_data(univers_etendu=tickers_univers, telecharger=True)
    n_prix = data["market_data_raw"]["symbol"].nunique() if not data["market_data_raw"].empty else 0
    print(
        f"[CRON] Pipeline terminé — {n_prix} tickers (prix), "
        f"{len(data['fonda_data_clean'])} fondamentaux, {len(data['zscore_df'])} Z-Scores, "
        f"accuracy actions: {data['model_result']['accuracy']}%, ETF: {data['model_result_etf']['accuracy']}%"
    )

    # --- 3. Spreads de crédit FRED ---
    spreads = fred.get_spreads_hy_ig()
    if spreads["hy_actuel"] is not None:
        print(f"[CRON] Spread HY : {spreads['hy_actuel']:.0f} pb, IG : {spreads['ig_actuel']:.0f} pb")
    else:
        print("[CRON] Spreads FRED indisponibles (clé manquante ou erreur réseau).")

    # --- 4. Tables prêtes à afficher (APK / PWA) ---
    resume = publish.publier(data, univers_df, spreads)
    print(f"[CRON] Publication : {resume}")

    duree = time.time() - t0
    msg = f"{n_prix} tickers, {resume['signaux']} signaux, {duree:.0f}s"
    db.sync_log_end(log_id, "success", msg, n_tickers=n_prix)
    print(f"[CRON] Synchronisation terminée avec succès ({msg}).")


if __name__ == "__main__":
    log_id = db.sync_log_start()
    try:
        main(log_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.sync_log_end(log_id, "error", f"{type(e).__name__}: {e}")
        print(f"[CRON] ERREUR FATALE : {e}", file=sys.stderr)
        sys.exit(1)
