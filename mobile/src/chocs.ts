// Face aux chocs (docs/METHODE.md §§ 13 à 15).
// 1. Stress test : les crises passées rejouées sur le portefeuille d'aujourd'hui. Ce n'est PAS une prévision :
//    c'est ce qui s'est passé, avec des poids fixes pendant la chute. Titre absent à l'époque : bêta × chute du marché.
// 2. Risque du mois à venir : volatilité prévue à 22 séances par HAR-X (HAR + VIX), publiée par le serveur
//    seulement si sa confirmation sur des titres jamais utilisés (S&P MidCap 400) est réussie.
import { covariance, type Univers } from "./optim";
import { zStudent5 } from "./strategy";

export interface Crise { nom: string; debut: string; fin: string; marche: number; retour_jours: number | null }
export interface Chocs { crises: Crise[]; rendements: (number | null)[][] }
export interface CriseRejouee extends Crise { portefeuille: number; partEstimee: number }
export interface LignePoids { symbol: string; poids: number }

/** Perte de chaque crise pour le portefeuille (poids fixes), la plus forte chute du marché d'abord. */
export function rejouerCrises(chocs: Chocs | null | undefined, symbols: string[], beta: number[], lignes: LignePoids[]): CriseRejouee[] {
  if (!chocs?.crises?.length || !lignes.length) return [];
  const idx = new Map(symbols.map((s, i) => [s, i]));
  const total = lignes.reduce((a, l) => a + l.poids, 0) || 1;
  return chocs.crises.map((c, k) => {
    let r = 0, estime = 0;
    for (const l of lignes) {
      const i = idx.get(l.symbol);
      const reel = i != null ? chocs.rendements[i]?.[k] : null;
      if (reel != null && Number.isFinite(reel)) r += l.poids * reel;
      else { r += l.poids * (i != null ? beta[i] : 1) * c.marche; estime += l.poids; }
    }
    return { ...c, portefeuille: r / total, partEstimee: estime / total };
  }).sort((a, b) => a.marche - b.marche);
}

/** Volatilité annuelle du portefeuille √(wᵀΣw), corrélations de l'univers ; `vols` (facultatif) remplace la
 *  volatilité de chaque titre (Σ' = S·Σ·S, comme `avecVolIA`). Lignes absentes de l'univers : ignorées (part couverte). */
export function volPortefeuille(u: Univers, lignes: LignePoids[], vols?: (number | null)[]): { vol: number; couverture: number } | null {
  const idx = new Map(u.symbols.map((s, i) => [s, i]));
  const ls = lignes.map((l) => ({ ...l, i: idx.get(l.symbol) })).filter((l): l is LignePoids & { i: number } => l.i != null);
  if (!ls.length) return null;
  const ech = (i: number) => {
    const v = vols?.[i], sdH = Math.sqrt(Math.max(covariance(u, i, i), 0));
    return v != null && v > 0 && sdH > 0 ? v / sdH : 1;
  };
  let s = 0;
  for (const a of ls) for (const b of ls) s += a.poids * b.poids * covariance(u, a.i, b.i) * ech(a.i) * ech(b.i);
  const couverture = ls.reduce((x, l) => x + l.poids, 0);
  return { vol: Math.sqrt(Math.max(s, 0)) / (couverture || 1), couverture };
}

export const JOURS_MOIS = 22;

/** Risque du mois à venir : volatilité sur 22 séances et « mauvais cas 5 % » (loi de Student à 5 degrés, échelle σ,
 *  rendement moyen supposé nul, comme le protocole § 4.16), comparés au risque habituel (3 ans). */
export function risqueMois(u: Univers & { vol_1m?: (number | null)[] }, lignes: LignePoids[]) {
  if (!u.vol_1m?.length) return null;
  const prevu = volPortefeuille(u, lignes, u.vol_1m), habituel = volPortefeuille(u, lignes);
  if (!prevu || !habituel) return null;
  const f = Math.sqrt(JOURS_MOIS / 252);
  const z = zStudent5(0.9);                       // 5 % de chances de faire pire (une seule queue)
  const perte = (v: number) => 1 - Math.exp(-z * v * f);
  return { volAn: prevu.vol, volHabituelle: habituel.vol, mauvaisCas: perte(prevu.vol), mauvaisCasHabituel: perte(habituel.vol),
    rapport: prevu.vol / habituel.vol, couverture: prevu.couverture };
}
