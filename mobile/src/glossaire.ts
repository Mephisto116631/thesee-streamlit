// Glossaire : fiches sans seuils (glossaire.json) + indicateurs à seuils (ranges.json). Source des boutons d'aide « ? ».
import raw from "./glossaire.json";
import { RANGES } from "./ranges";

export interface Fiche { categorie: string; titre: string; def: string; lecture: string; limites: string }
export const GLOSSAIRE = Object.fromEntries(Object.entries(raw).filter(([k]) => !k.startsWith("_"))) as unknown as Record<string, Fiche>;

// Indicateurs de ranges.json qui ne sont plus affichés nulle part (ancien modèle de classement, retiré) : hors glossaire
const RETIRES = new Set(["gain_pts", "proba_hausse"]);

/** Toutes les entrées, triées A → Z : fiches du glossaire et indicateurs (définition de ranges.json). */
export function entrees(): { cle: string; titre: string; categorie: string; texte: string }[] {
  const g = Object.entries(GLOSSAIRE).map(([cle, f]) => ({ cle, titre: f.titre, categorie: f.categorie, texte: `${f.def} ${f.lecture} ${f.limites}` }));
  const r = Object.entries(RANGES).filter(([cle]) => !RETIRES.has(cle)).map(([cle, x]) => ({ cle, titre: x.label, categorie: "Indicateurs", texte: x.definition }));
  return [...g, ...r].sort((a, b) => a.titre.localeCompare(b.titre, "fr"));
}

/** Recherche sans accents ni majuscules. */
export function chercher(q: string) {
  const n = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  const m = n(q.trim());
  return m ? entrees().filter((e) => n(`${e.titre} ${e.texte}`).includes(m)) : entrees();
}

export const existe = (k: string) => k in GLOSSAIRE || k in RANGES;
