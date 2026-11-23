// Stratégie : objectif de rentabilité, horizon de placement, plan d'achat.
// Tout est calculé sur le téléphone à partir de la frontière efficiente
// publiée par le cron (portefeuille.py) : aucun calcul lourd ici.

export interface Horizon { k: string; label: string; annees: number; conseil: string }

export const HORIZONS: Horizon[] = [
  { k: "1m", label: "1 mois", annees: 1 / 12,
    conseil: "Horizon très court : le résultat dépend surtout du hasard. Un portefeuille d'actions peut perdre 10 % en un mois ; ce n'est pas un placement, c'est du trading." },
  { k: "3m", label: "3 mois", annees: 0.25,
    conseil: "Horizon court : les écarts sont encore larges. Vise un objectif modeste et accepte l'idée de finir en perte." },
  { k: "6m", label: "6 mois", annees: 0.5,
    conseil: "Horizon moyen : le portefeuille commence à lisser les mouvements, mais une baisse de marché peut tout effacer." },
  { k: "1a", label: "1 an", annees: 1,
    conseil: "1 an : horizon minimal raisonnable pour des actions. Garde les titres l'année entière sans réagir aux mouvements quotidiens." },
  { k: "3a", label: "3 ans", annees: 3,
    conseil: "Buy and hold : achète puis ne touche plus. Rééquilibre une fois par an (ou si une ligne dépasse 25 %). Le temps réduit fortement la probabilité de perte." },
  { k: "5a", label: "5 ans", annees: 5,
    conseil: "Buy and hold long terme : la meilleure configuration pour des actions. Rééquilibre une fois par an et réinvestis les dividendes." },
];
export const HORIZON_DEFAUT = "1a";

// ---------------------------------------------------------------------------
// Frontière efficiente : choisir le portefeuille le moins risqué qui atteint
// la rentabilité visée (ou le plus rentable possible si elle est hors d'atteinte).
// ---------------------------------------------------------------------------
export interface PointFrontiere {
  cible?: number; rendement: number; volatilite: number; sharpe: number | null;
  lignes: { symbol: string; poids: number }[];
}

export function choisirPoint(frontiere: PointFrontiere[], cible: number) {
  if (!frontiere.length) return null;
  const tri = [...frontiere].sort((a, b) => a.rendement - b.rendement);
  const ok = tri.find((p) => p.rendement >= cible - 1e-9);
  return { point: ok ?? tri[tri.length - 1], atteignable: Boolean(ok), max: tri[tri.length - 1].rendement, min: tri[0].rendement };
}

/** Le portefeuille le plus rentable dont la volatilité ne dépasse pas volMax. */
export function choisirPointRisque(frontiere: PointFrontiere[], volMax: number) {
  if (!frontiere.length) return null;
  const tri = [...frontiere].sort((a, b) => a.volatilite - b.volatilite);
  const ok = tri.filter((p) => p.volatilite <= volMax + 1e-9);
  const point = ok.length ? ok.reduce((b, p) => (p.rendement > b.rendement ? p : b)) : tri[0];
  return { point, atteignable: ok.length > 0, max: tri[tri.length - 1].rendement, min: tri[0].rendement, volMin: tri[0].volatilite };
}

// ---------------------------------------------------------------------------
// Projection à l'horizon (rendements composés, écarts Student à 5 degrés) : fourchette et probabilités.
// ---------------------------------------------------------------------------
function erf(x: number) { // Abramowitz-Stegun 7.1.26, précision ~1e-7
  const s = Math.sign(x); x = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * x);
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
  return s * y;
}
export const normCdf = (z: number) => 0.5 * (1 + erf(z / Math.SQRT2));

/** Quantile de la loi normale pour une fourchette bilatérale (0,8 → 1,2816 ; 0,9 → 1,6449 ; 0,95 → 1,96). */
export function zConfiance(confiance: number): number {
  // Inversion de normCdf par dichotomie (précision 1e-6, largement suffisante)
  const p = 1 - (1 - confiance) / 2;
  let lo = 0, hi = 6;
  for (let k = 0; k < 60; k++) { const m = (lo + hi) / 2; if (normCdf(m) < p) lo = m; else hi = m; }
  return (lo + hi) / 2;
}

/** Loi de Student à 5 degrés de liberté (forme exacte pour ν = 5). */
export function studentCdf5(t: number): number {
  const th = Math.atan(t / Math.sqrt(5)), c = Math.cos(th);
  return 0.5 + (th + Math.sin(th) * c * (1 + (2 / 3) * c * c)) / Math.PI;
}
export function zStudent5(confiance: number): number {
  const p = 1 - (1 - confiance) / 2;
  let lo = 0, hi = 20;
  for (let k = 0; k < 80; k++) { const m = (lo + hi) / 2; if (studentCdf5(m) < p) lo = m; else hi = m; }
  return (lo + hi) / 2;
}

/** Loi des écarts de la projection (docs/METHODE.md § 4.9, règle 5) : la fourchette « mauvais cas 5 % » de la
 *  loi normale a été touchée 8,8 % des fois au backtest 2006-2026 (> 7,5 %) : on passe à une loi de Student
 *  à 5 degrés de liberté, d'échelle σ (queues plus épaisses : 90 % des scénarios dans ±2,02 σ au lieu de ±1,64 σ). */
export const LOI_PROJECTION: "normale" | "student5" = "student5";

export function projection(capital: number, rendement: number, volatilite: number, annees: number, cible: number, confiance = 0.9,
  loi: "normale" | "student5" = LOI_PROJECTION) {
  const m = (Math.log(1 + rendement) - (volatilite * volatilite) / 2) * annees; // moyenne du log-rendement
  const s = Math.max(1e-9, volatilite * Math.sqrt(annees));
  const q = (z: number) => capital * Math.exp(m + z * s);
  const z = loi === "student5" ? zStudent5(confiance) : zConfiance(confiance);
  const F = loi === "student5" ? studentCdf5 : normCdf;
  return {
    bas: q(-z), median: q(0), haut: q(z), m, s, z, loi,          // `confiance` des scénarios entre bas et haut
    probPerte: F(-m / s),
    probObjectif: F((m - annees * Math.log(1 + cible)) / s),
    valeurObjectif: capital * Math.pow(1 + cible, annees),
  };
}

// ---------------------------------------------------------------------------
// Plan d'achat : quantités, prix limites, calendrier (DCA) et frais.
// ---------------------------------------------------------------------------
export interface Reglages {
  fraisOrdre: number;   // € par ordre
  fraisChange: number;  // fraction (0.0025 = 0,25 %) prélevée à la conversion EUR -> USD
  fractions: boolean;   // le courtier accepte les fractions d'actions
  tranches: number;     // 1 = tout de suite ; >1 = achat progressif
  frequence: "semaine" | "mois";
  margeLimite?: number; // prix limite = dernier cours x (1 + marge) ; défaut MARGE_LIMITE
}
export const REGLAGES_DEFAUT: Reglages = { fraisOrdre: 0, fraisChange: 0.0025, fractions: true, tranches: 1, frequence: "mois" };

export const MARGE_LIMITE = 0.003; // prix limite = dernier cours + 0,3 %

export interface Ordre { symbol: string; montantEur: number; montantUsd: number; prix: number; quantite: number; limite: number; investiEur: number }
export interface Tranche { date: Date; ordres: Ordre[] }

export function datesTranches(n: number, frequence: "semaine" | "mois", depart = new Date()): Date[] {
  const out: Date[] = [];
  for (let i = 0; i < n; i++) {
    const d = new Date(depart);
    if (frequence === "semaine") d.setDate(d.getDate() + 7 * i); else d.setMonth(d.getMonth() + i);
    while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1); // jours de bourse
    out.push(d);
  }
  return out;
}

export function planAchat(
  capital: number, lignes: { symbol: string; poids: number }[], prix: Record<string, number | null | undefined>,
  eurusd: number, r: Reglages, depart = new Date(),
) {
  const n = Math.max(1, Math.round(r.tranches));
  const nbOrdresPrevus = lignes.length * n;
  const fraisOrdres = nbOrdresPrevus * r.fraisOrdre;
  const aInvestir = Math.max(0, capital - fraisOrdres);
  const tranches: Tranche[] = datesTranches(n, r.frequence, depart).map((date) => ({
    date,
    ordres: lignes.map((l) => {
      const p = prix[l.symbol] ?? 0;
      const montantEur = (aInvestir / n) * l.poids;
      const montantUsd = montantEur * (1 - r.fraisChange) * eurusd;
      const brut = p > 0 ? montantUsd / p : 0;
      const quantite = r.fractions ? Math.floor(brut * 10000) / 10000 : Math.floor(brut);
      const investiEur = p > 0 ? (quantite * p) / eurusd / (1 - r.fraisChange) : 0;
      return { symbol: l.symbol, montantEur, montantUsd, prix: p, quantite, limite: Math.round(p * (1 + (r.margeLimite ?? MARGE_LIMITE)) * 100) / 100, investiEur };
    }),
  }));
  const investi = tranches.reduce((a, t) => a + t.ordres.reduce((b, o) => b + o.investiEur, 0), 0);
  const nonInvesti = Math.max(0, aInvestir - investi);
  const fraisChangeEur = investi * r.fraisChange;
  const nbOrdres = tranches.reduce((a, t) => a + t.ordres.filter((o) => o.quantite > 0).length, 0);
  const totalFrais = nbOrdres * r.fraisOrdre + fraisChangeEur;
  return {
    tranches, nbOrdres, fraisOrdres: nbOrdres * r.fraisOrdre, fraisChangeEur, totalFrais,
    nonInvesti, partFrais: capital > 0 ? totalFrais / capital : 0,
    lignesNonAchetees: tranches[0]?.ordres.filter((o) => o.quantite === 0).map((o) => o.symbol) ?? [],
  };
}

/** Rentabilité annuelle perdue à cause des frais d'entrée (et de sortie au change), sur l'horizon. */
export function coutAnnualise(partFraisEntree: number, fraisChange: number, annees: number) {
  const garde = (1 - partFraisEntree) * (1 - fraisChange); // change à nouveau à la revente
  return 1 - Math.pow(garde, 1 / Math.max(annees, 1 / 12));
}

// ---------------------------------------------------------------------------
// Marge de sécurité du mode « Je limite le risque » (docs/METHODE.md § 7.4, correction du 23/11/2026) :
// celle de la SOURCE choisie (historique 3 ans ou IA + HAR) et de la limite testée la plus proche de celle de l'utilisateur.
// ---------------------------------------------------------------------------
export interface StatMarge { part_respectee_avec_marge?: number | null; marge_actuelle?: number | null }
export interface InfoMarge { m: number; part?: number; limiteTestee?: number; exacte: boolean; parSource: boolean }

export function choisirMarge(diag: any, source: "hist_3a" | "hybride", volMax: number): InfoMarge {
  const borne = (x: unknown) => Math.min(1.5, Math.max(0.5, Number(x) || 1));
  const table = diag?.marges_par_source?.[source] as Record<string, StatMarge> | undefined;
  const parSource = Boolean(table && Object.keys(table).length);
  const marges = (parSource ? table : diag?.marges) as Record<string, StatMarge> | undefined;
  const cles = Object.keys(marges ?? {});
  if (!cles.length) return { m: borne(diag?.marge), exacte: false, parSource: false };
  const cle = cles.sort((a, b) => Math.abs(+a / 100 - volMax) - Math.abs(+b / 100 - volMax))[0];
  const st = marges![cle];
  const limiteTestee = +cle / 100;
  const exacte = Math.abs(limiteTestee - volMax) <= 0.015;     // à 1,5 point près : on l'annonce comme la même limite
  // Ancien format (une seule source, 10 à 18 %) : marge globale, et la part tenue seulement si la limite est proche
  return parSource
    ? { m: borne(st?.marge_actuelle), part: st?.part_respectee_avec_marge ?? undefined, limiteTestee, exacte, parSource }
    : { m: borne(diag?.marge), part: exacte ? st?.part_respectee_avec_marge ?? undefined : undefined, limiteTestee, exacte, parSource };
}

/** Seuil de rentabilité : hausse nécessaire pour retrouver sa mise après les frais d'achat ET de revente,
 *  et temps estimé pour l'atteindre à la rentabilité de long terme (hypothèse, pas une prévision). */
export function seuilRentabilite(capital: number, fraisEntree: number, nbOrdres: number, fraisOrdre: number, fraisChange: number,
  rendement: number) {
  const investi = Math.max(capital - fraisEntree, 1e-9);
  const fraisSortie = nbOrdres * fraisOrdre + capital * fraisChange;   // revente : mêmes ordres, change sur ~ la mise
  const hausse = (capital + fraisSortie) / investi - 1;
  const mois = rendement > 0 ? (12 * Math.log(1 + hausse)) / Math.log(1 + rendement) : null;
  return { hausse, montant: capital * hausse, fraisSortie, fraisTotal: fraisEntree + fraisSortie, mois };
}
