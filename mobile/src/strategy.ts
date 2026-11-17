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
export const HORIZON_DEFAUT = "3a";

// ---------------------------------------------------------------------------
// Frontière efficiente : choisir le portefeuille le moins risqué qui atteint
// la rentabilité visée (ou le plus rentable possible si elle est hors d'atteinte).
// ---------------------------------------------------------------------------
export interface PointFrontiere {
  cible: number; rendement: number; volatilite: number; sharpe: number | null;
  lignes: { symbol: string; poids: number }[];
}

export function choisirPoint(frontiere: PointFrontiere[], cible: number) {
  if (!frontiere.length) return null;
  const tri = [...frontiere].sort((a, b) => a.rendement - b.rendement);
  const ok = tri.find((p) => p.rendement >= cible - 1e-9);
  return { point: ok ?? tri[tri.length - 1], atteignable: Boolean(ok), max: tri[tri.length - 1].rendement, min: tri[0].rendement };
}

// ---------------------------------------------------------------------------
// Projection à l'horizon (modèle log-normal) : fourchette et probabilités.
// ---------------------------------------------------------------------------
function erf(x: number) { // Abramowitz-Stegun 7.1.26, précision ~1e-7
  const s = Math.sign(x); x = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * x);
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
  return s * y;
}
export const normCdf = (z: number) => 0.5 * (1 + erf(z / Math.SQRT2));

export function projection(capital: number, rendement: number, volatilite: number, annees: number, cible: number) {
  const m = (Math.log(1 + rendement) - (volatilite * volatilite) / 2) * annees; // moyenne du log-rendement
  const s = Math.max(1e-9, volatilite * Math.sqrt(annees));
  const q = (z: number) => capital * Math.exp(m + z * s);
  return {
    bas: q(-1.645), median: q(0), haut: q(1.645),               // 90 % des scénarios entre bas et haut
    probPerte: normCdf(-m / s),
    probObjectif: normCdf((m - annees * Math.log(1 + cible)) / s),
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
      return { symbol: l.symbol, montantEur, montantUsd, prix: p, quantite, limite: Math.round(p * (1 + MARGE_LIMITE) * 100) / 100, investiEur };
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
