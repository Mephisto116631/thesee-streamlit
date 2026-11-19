// Révision du portefeuille 1 à 2 fois par an (docs/METHODE.md § 4.9) : le serveur fige l'univers
// (titres, covariance, volatilité prévue) en janvier et en juillet ; l'appli construit le portefeuille
// conseillé à partir de la dernière révision de son rythme, et ne le change donc qu'à ces dates.
// Raison : suivre chaque mois la recommandation du jour coûtait ~180 ordres par an (3 à 5 points de frais).

export interface Revision { date: string; univers_facteurs: any; titres?: any; methode?: string }

/** Dernière révision du rythme choisi : 6 mois -> la plus récente ; 12 mois -> la plus récente de janvier à juin. */
export function choisirRevision(revs: Revision[] | undefined | null, rythme: 6 | 12): Revision | null {
  const tri = [...(revs ?? [])].sort((a, b) => b.date.localeCompare(a.date));
  if (rythme === 6) return tri[0] ?? null;
  return tri.find((r) => new Date(r.date).getUTCMonth() < 6) ?? tri[tri.length - 1] ?? null;
}

/** Prochaine révision : 1er janvier ou 1er juillet (6 mois), 1er janvier (12 mois). */
export function prochaineRevision(rythme: 6 | 12, maintenant = new Date()): Date {
  const a = maintenant.getUTCFullYear();
  const juillet = new Date(Date.UTC(a, 6, 1)), janvier = new Date(Date.UTC(a + 1, 0, 1));
  return rythme === 6 && maintenant < juillet ? juillet : janvier;
}
