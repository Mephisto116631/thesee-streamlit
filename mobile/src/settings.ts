// Paramètres (hypothèses) de l'utilisateur : stockés sur le téléphone, partagés
// par tous les écrans. Un changement prévient les écrans abonnés immédiatement.
import { useEffect, useState } from "preact/hooks";
import type { HypothesesModele } from "./optim";

export interface Parametres extends HypothesesModele {
  // Achat
  fraisOrdre: number;     // € par ordre
  fraisChange: number;    // fraction (0.0025 = 0,25 %)
  fractions: boolean;
  margeLimite: number;    // prix limite = dernier cours x (1 + marge)
  deviseOrdres: "EUR" | "USD"; // devise des prix affichés pour les ordres (Trade Republic : EUR)
  // Projection et suivi
  confiance: number;      // part des scénarios dans la fourchette affichée (0.8 / 0.9 / 0.95)
  seuilReequilibrage: number; // rééquilibrer si une ligne dépasse ce poids
  rythmeRevision: 6 | 12;     // le portefeuille conseillé n'est révisé que tous les 6 ou 12 mois
  // Taux sans risque : suivre celui publié par le serveur (bons du Trésor US à 3 mois, docs/METHODE.md § 2.1),
  // ou garder la valeur saisie par l'utilisateur
  tauxSansRisqueAuto: boolean;
}

// Valeurs par défaut = celles du serveur (portefeuille.py) et d'un courtier sans frais.
export const PARAMETRES_DEFAUT: Parametres = {
  tauxSansRisque: 0.0435,
  primeRisque: 0.05,
  poidsHistorique: 0.1,
  poidsMax: 0.2,
  nMaxLignes: 12,
  poidsMin: 0.03,
  fraisOrdre: 0,
  fraisChange: 0.0025,
  fractions: true,
  margeLimite: 0.003,
  deviseOrdres: "EUR",
  confiance: 0.9,
  seuilReequilibrage: 0.25,
  rythmeRevision: 6,
  sourceVol: "historique",
  tauxSansRisqueAuto: true,
};

const KEY = "thesee:parametres:v1";
const EVT = "thesee:parametres";
const KEY_TAUX = "thesee:taux-marche:v1";

/** Taux sans risque publié par le serveur avec le portefeuille (fraction) et sa date (null = valeur de repli du serveur). */
export interface TauxMarche { taux: number; date: string | null }

export function lireTauxMarche(): TauxMarche | null {
  try {
    const t = JSON.parse(localStorage.getItem(KEY_TAUX) ?? "null");
    return t && Number.isFinite(t.taux) ? t : null;
  } catch { return null; }
}

/** Retient le taux publié (appelé à chaque lecture du portefeuille conseillé) ; prévient les écrans s'il a changé. */
export function definirTauxMarche(taux: number | null | undefined, date: string | null | undefined) {
  if (taux == null || !Number.isFinite(taux) || taux < -0.01 || taux > 0.2) return;
  const avant = lireTauxMarche();
  if (avant && avant.taux === taux && avant.date === (date ?? null)) return;
  try { localStorage.setItem(KEY_TAUX, JSON.stringify({ taux, date: date ?? null })); } catch { /* ignore */ }
  window.dispatchEvent(new CustomEvent(EVT));
}

/** Paramètres effectifs : en mode « suivre le marché », le taux sans risque est celui publié (sinon la valeur gardée). */
export function avecTauxMarche(p: Parametres, marche: TauxMarche | null): Parametres {
  return p.tauxSansRisqueAuto !== false && marche ? { ...p, tauxSansRisque: marche.taux } : p;
}

export function lireParametres(): Parametres {
  try {
    // Reprend aussi les anciens réglages d'achat (avant la page Paramètres)
    const ancien = JSON.parse(localStorage.getItem("thesee:reglages-achat:v1") ?? "{}");
    const { fraisOrdre, fraisChange, fractions } = ancien;
    const base = { ...PARAMETRES_DEFAUT, ...(fraisOrdre !== undefined ? { fraisOrdre, fraisChange, fractions } : {}) };
    return avecTauxMarche({ ...base, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") }, lireTauxMarche());
  } catch { return { ...PARAMETRES_DEFAUT }; }
}

export function ecrireParametres(p: Partial<Parametres> | null) {
  // Saisir un taux sans risque le fige (on ne suit plus celui du marché)
  if (p && "tauxSansRisque" in p && !("tauxSansRisqueAuto" in p)) p = { ...p, tauxSansRisqueAuto: false };
  const n = p === null ? { ...PARAMETRES_DEFAUT } : { ...lireParametres(), ...p };
  try { localStorage.setItem(KEY, JSON.stringify(n)); } catch { /* ignore */ }
  window.dispatchEvent(new CustomEvent(EVT));
  return n;
}

export function useParametres(): Parametres {
  const [p, setP] = useState<Parametres>(lireParametres());
  useEffect(() => {
    const on = () => setP(lireParametres());
    window.addEventListener(EVT, on);
    return () => window.removeEventListener(EVT, on);
  }, []);
  return p;
}

/** Combien de paramètres diffèrent des valeurs par défaut (affiché sur l'écran Portefeuille). */
export function nbModifies(p: Parametres): number {
  return (Object.keys(PARAMETRES_DEFAUT) as (keyof Parametres)[])
    .filter((k) => !(k === "tauxSansRisque" && p.tauxSansRisqueAuto !== false))   // taux du marché : pas une modification
    .filter((k) => p[k] !== PARAMETRES_DEFAUT[k]).length;
}

/** Préréglage Trade Republic : titres US cotés en euros (pas de frais de change séparé), 1 € par ordre. */
export const PRESET_TRADE_REPUBLIC: Partial<Parametres> = { fraisOrdre: 1, fraisChange: 0, fractions: true, deviseOrdres: "EUR" };
