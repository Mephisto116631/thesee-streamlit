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

// ---------------------------------------------------------------------------
// Bouton « Ré-entraîner » de l'en-tête : état et minuteur (mêmes délais que la fonction relancer-calcul)
// ---------------------------------------------------------------------------
export const DELAI_ENTRE_RELANCES_MS = 10 * 60_000;   // pas de relance moins de 10 min après le dernier démarrage
export const DUREE_MAX_CALCUL_MS = 45 * 60_000;       // au-delà, un « en cours » est considéré comme abandonné

export type EtatRelance =
  | { phase: "libre" }
  | { phase: "demande"; secondes: number }   // relance envoyée, calcul pas encore démarré : temps écoulé
  | { phase: "calcul"; secondes: number }    // calcul en cours : temps écoulé
  | { phase: "pause"; secondes: number };    // calcul fini depuis peu : temps avant de pouvoir relancer

export function etatRelance(dernier: { started_at: string; status: string } | null, maintenant: number,
                            demandeA: number | null = null): EtatRelance {
  const debut = dernier ? new Date(dernier.started_at).getTime() : NaN;
  const age = maintenant - debut;
  if (dernier?.status === "running" && age >= 0 && age < DUREE_MAX_CALCUL_MS) return { phase: "calcul", secondes: Math.floor(age / 1000) };
  // Demande envoyée et pas encore de passage plus récent qu'elle (2 min de marge d'horloge)
  if (demandeA != null && !(debut >= demandeA - 120_000) && maintenant - demandeA < 15 * 60_000) {
    return { phase: "demande", secondes: Math.floor((maintenant - demandeA) / 1000) };
  }
  if (Number.isFinite(age) && age >= 0 && age < DELAI_ENTRE_RELANCES_MS) {
    return { phase: "pause", secondes: Math.ceil((DELAI_ENTRE_RELANCES_MS - age) / 1000) };
  }
  return { phase: "libre" };
}

/** 75 -> « 1:15 » */
export function chrono(secondes: number): string {
  const s = Math.max(0, Math.round(secondes));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
