// Fiabilité de l'IA de volatilité : la SEULE prévision montrée dans les écrans de décision.
// Elle n'y apparaît que si son dernier test (re-test mensuel du laboratoire) est probant.
// Le bilan « en conditions réelles » compare ses prévisions enregistrées chaque semaine à la
// volatilité observée 6 mois plus tard (publish.py, table suivi_volatilite).
import { api, type ModelRun } from "./api";
import type { Univers } from "./optim";
import { useData } from "./components";

export interface LaboVol {
  verdict: string | null; t_stat: number | null; seuil_t_global: number | null; cree_le: string | null;
  ic: number | null; ic_base: number | null; gain: number | null; part: number | null;
}
export interface BilanReel {
  verdict?: string; n_dates: number; premier_bilan?: string; premiere_prevision?: string;
  ic_ia?: number; ic_reference?: number; gain?: number; t_stat?: number; seuil?: number;
  part_dates_gagnantes?: number; derniere_date_jugee?: string;
}
export interface FiabiliteVol {
  probant: boolean; verdict: string; t: number | null; seuil: number | null; date: string | null;
  ic: number | null; icBase: number | null; gain: number | null; part: number | null;
  reel: BilanReel | null; prochainTest: Date; connu: boolean;
  source: "ia" | "hybride" | "har";   // méthode publiée (docs/METHODE.md § 4.9)
}

/** Nom court de la méthode qui prévoit le risque. */
export const libelleSource = (s: FiabiliteVol["source"]) => (s === "hybride" ? "IA + HAR" : s === "har" ? "HAR" : "IA");

/** Re-test automatique : le 2 de chaque mois (workflow experiences.yml). */
export function prochainReTest(maintenant = new Date()): Date {
  const d = new Date(Date.UTC(maintenant.getUTCFullYear(), maintenant.getUTCMonth(), 2, 4, 17));
  if (d <= maintenant) d.setUTCMonth(d.getUTCMonth() + 1);
  return d;
}

/** Statut à partir du dernier essai du laboratoire et du bilan publié. Sans test connu : non probant. */
export function lireFiabilite(labo: LaboVol | null | undefined, run: ModelRun | null | undefined, maintenant = new Date()): FiabiliteVol {
  const reel = (run?.diagnostics?.reel ?? null) as BilanReel | null;
  const source = (run?.diagnostics?.labo?.source as FiabiliteVol["source"]) ?? "ia";
  return {
    // HAR seul (décision de l'examen) : méthode de référence, publiée sans dépendre du test de l'IA
    probant: source === "har" ? Boolean(run?.diagnostics?.vol_ia_publiee) : labo?.verdict === "probant",
    verdict: labo?.verdict ?? "jamais testé",
    t: labo?.t_stat ?? null, seuil: labo?.seuil_t_global ?? null, date: labo?.cree_le ?? null,
    ic: labo?.ic ?? null, icBase: labo?.ic_base ?? null, gain: labo?.gain ?? null, part: labo?.part ?? null,
    reel, prochainTest: prochainReTest(maintenant), connu: Boolean(labo),
    source,
  };
}

/** Retire la prévision IA de l'univers quand elle n'est pas (ou plus) prouvée :
 *  tous les écrans reviennent alors d'eux-mêmes à la volatilité historique. */
export function univers(u: Univers | undefined, f: Pick<FiabiliteVol, "probant">): Univers | undefined {
  if (!u || f.probant || !u.vol_ia) return u;
  const { vol_ia: _retiree, ...reste } = u;
  return reste;
}

export function useFiabiliteVol(): FiabiliteVol & { loading: boolean } {
  const r = useData(api.fiabiliteVol);
  return { ...lireFiabilite(r.data?.labo, r.data?.run), loading: r.loading };
}
