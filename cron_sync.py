# cron_sync.py
# ==============================================================================
# SCRIPT DE SYNCHRONISATION AUTOMATIQUE — exécuté par GitHub Actions (CRON)
#
# Rôle : faire TOUS les calculs (prix, fondamentaux, Z-Score, modèles IA,
# indicateurs, portefeuille) et écrire dans Supabase des tables prêtes à afficher.
# L'appli mobile (APK / PWA) ne fait que LIRE.
# ==============================================================================
import sys
import time

import data_pipeline as dp
import db
import fred
import publish
import universe


def main(log_id):
    t0 = time.time()
    print("[CRON] Démarrage de la synchronisation Thésée...")

    # --- 1. Univers élargi ---
    db.progression(2, "Liste des titres")
    univers_df = universe.get_univers_complet()
    tickers_univers = univers_df["symbol"].tolist()
    print(f"[CRON] {len(tickers_univers)} tickers dans l'univers élargi.")

    # --- 2. Collecte : prix incrémentaux, macro, fondamentaux, Z-Score ---
    db.progression(5, "Cours de bourse")
    data = dp.get_all_data(univers_etendu=tickers_univers)
    n_prix = data["market_data_raw"]["symbol"].nunique() if not data["market_data_raw"].empty else 0
    print(
        f"[CRON] Pipeline terminé — {n_prix} tickers (prix), "
        f"{len(data['fonda_data_clean'])} fondamentaux, {len(data['zscore_df'])} Z-Scores"
    )

    # --- 3. Spreads de crédit FRED ---
    db.progression(55, "Spreads de crédit")
    spreads = fred.get_spreads_hy_ig()
    if spreads["hy_actuel"] is not None:
        print(f"[CRON] Spread HY : {spreads['hy_actuel']:.0f} pb, IG : {spreads['ig_actuel']:.0f} pb")
    else:
        print("[CRON] Spreads FRED indisponibles (clé manquante ou erreur réseau).")

    # --- 4. Tables prêtes à afficher (APK / PWA) ---
    db.progression(60, "Publication des indicateurs")
    resume = publish.publier(data, univers_df, spreads)
    print(f"[CRON] Publication : {resume}")

    duree = time.time() - t0
    statut, msg = statut_passage(n_prix, resume, duree)
    db.sync_log_end(log_id, statut, msg, n_tickers=n_prix)
    print(f"[CRON] Synchronisation terminée ({statut}) : {msg}")


def statut_passage(n_prix: int, resume: dict, duree: float) -> tuple[str, str]:
    """« success » si tout est publié ; « partiel » si une étape non bloquante a échoué
    (volatilité, portefeuille, comptes SEC…) : l'appli le signale au lieu d'afficher « à jour »."""
    avert = resume.get("avertissements") or []
    msg = f"{n_prix} tickers, {resume.get('portefeuille', 0)} lignes de portefeuille, {duree:.0f}s"
    if not avert:
        return "success", msg
    return "partiel", f"{msg} — {len(avert)} avertissement(s) : " + " | ".join(avert)


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
