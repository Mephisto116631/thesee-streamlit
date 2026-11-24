// Statut du dernier passage du cron (table sync_log), écrit par cron_sync.py :
//   running  : calcul en cours
//   success  : tout est publié
//   partiel  : publié, mais une étape non bloquante a échoué (volatilité, portefeuille, comptes SEC…)
//   error    : le passage s'est arrêté
export type StatutSync = "running" | "success" | "partiel" | "error" | string;

/** Le passage est allé au bout (les données affichées sont celles de ce passage). */
export const passageTermine = (s: StatutSync): boolean => s === "success" || s === "partiel";

/** Mots affichés dans l'appli pour chaque statut. */
export function libelleStatut(s: StatutSync): string {
  switch (s) {
    case "running": return "en cours";
    case "success": return "réussi";
    case "partiel": return "terminé avec avertissements";
    case "error": return "en erreur";
    default: return s;
  }
}

/** Ligne d'état de l'accueil (« à jour », ou ce qui cloche). */
export function etatDonnees(s: StatutSync): string {
  if (s === "error") return "⚠️ dernière synchro en erreur";
  if (s === "partiel") return "à jour, avec avertissements (Paramètres › Relancer les calculs)";
  return "à jour";
}
