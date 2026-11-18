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
  // Projection et suivi
  confiance: number;      // part des scénarios dans la fourchette affichée (0.8 / 0.9 / 0.95)
  seuilReequilibrage: number; // rééquilibrer si une ligne dépasse ce poids
  // Mode court terme
  ctNbTitres: number;     // nombre de titres retenus
  ctScoreMin: number;     // score IA minimal (rang 0..1)
  ctRotation: "semaine" | "mois";
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
  confiance: 0.9,
  seuilReequilibrage: 0.25,
  ctNbTitres: 8,
  ctScoreMin: 0.8,
  ctRotation: "mois",
};

const KEY = "thesee:parametres:v1";
const EVT = "thesee:parametres";

export function lireParametres(): Parametres {
  try {
    // Reprend aussi les anciens réglages d'achat (avant la page Paramètres)
    const ancien = JSON.parse(localStorage.getItem("thesee:reglages-achat:v1") ?? "{}");
    const { fraisOrdre, fraisChange, fractions } = ancien;
    const base = { ...PARAMETRES_DEFAUT, ...(fraisOrdre !== undefined ? { fraisOrdre, fraisChange, fractions } : {}) };
    return { ...base, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") };
  } catch { return { ...PARAMETRES_DEFAUT }; }
}

export function ecrireParametres(p: Partial<Parametres> | null) {
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
  return (Object.keys(PARAMETRES_DEFAUT) as (keyof Parametres)[]).filter((k) => p[k] !== PARAMETRES_DEFAUT[k]).length;
}
