// Valorisation à partir des comptes officiels déposés à la SEC (Securities and Exchange
// Commission) : des FAITS publiés, recalculés au cours du jour. Pas un signal d'achat :
// au laboratoire, ces ratios n'ont pas prédit la performance sur 2012-2026.
import type { Snapshot } from "./api";

/** PER (Price Earnings Ratio) = cours / bénéfice par action annuel. null si perte ou inconnu. */
export function per(r: Pick<Snapshot, "close" | "bpa_sec">): number | null {
  return r.bpa_sec != null && r.bpa_sec > 0 && r.close > 0 ? r.close / r.bpa_sec : null;
}
/** Cours / valeur comptable (fonds propres par action). */
export function coursVC(r: Pick<Snapshot, "close" | "vc_action_sec">): number | null {
  return r.vc_action_sec != null && r.vc_action_sec > 0 && r.close > 0 ? r.close / r.vc_action_sec : null;
}
/** L'entreprise a-t-elle perdu de l'argent sur son dernier exercice ? */
export const enPerte = (r: Pick<Snapshot, "bpa_sec">) => r.bpa_sec != null && r.bpa_sec <= 0;

