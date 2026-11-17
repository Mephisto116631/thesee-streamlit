// Fourchettes d'interprétation — source unique : ranges.json à la racine du
// dépôt (aussi lu par le cron Python). Ne pas dupliquer les seuils ici.
import raw from "../../ranges.json";

export type Ton = "good" | "neutral" | "bad" | "info";
export type Unite = "pct" | "x" | "pts";
export interface Zone { nom: string; ton: Ton; aide: string }
export interface Range {
  label: string;
  unite: Unite;
  bornes: [number, number];
  zones: [Zone, Zone, Zone];
  definition: string;
}

export const RANGES = Object.fromEntries(
  Object.entries(raw).filter(([k]) => !k.startsWith("_"))
) as unknown as Record<string, Range>;

export type RangeKey = keyof typeof RANGES & string;

/** Zone d'une valeur : < b1 -> 0, [b1, b2] -> 1, > b2 -> 2. null si valeur absente. */
export function zoneIndex(key: string, v: number | null | undefined): 0 | 1 | 2 | null {
  const r = RANGES[key];
  if (!r || v === null || v === undefined || Number.isNaN(v)) return null;
  const [b1, b2] = r.bornes;
  if (v < b1) return 0;
  if (v > b2) return 2;
  return 1;
}

export function zoneOf(key: string, v: number | null | undefined): Zone | null {
  const i = zoneIndex(key, v);
  return i === null ? null : RANGES[key].zones[i];
}

/** Texte des bornes : "< 30 · 30–70 · > 70" */
export function bornesTexte(key: string): string[] {
  const r = RANGES[key];
  // Autant de décimales que nécessaire (1,81 ; 0,5x ; 5 %) mais pas plus de 2
  const dec = (x: number) => {
    const v = r.unite === "pct" ? x * 100 : x;
    for (let d = 0; d <= 2; d++) if (Math.abs(Math.round(v * 10 ** d) - v * 10 ** d) < 1e-9) return d;
    return 2;
  };
  const f = (x: number) => formatValue(x, r.unite, dec(x));
  const [b1, b2] = r.bornes;
  return [`< ${f(b1)}`, `${f(b1)} – ${f(b2)}`, `> ${f(b2)}`];
}

export function formatValue(v: number | null | undefined, unite: Unite, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  if (unite === "pct") return `${(v * 100).toLocaleString("fr-FR", { maximumFractionDigits: digits, minimumFractionDigits: digits })} %`;
  if (unite === "x") return `${v.toLocaleString("fr-FR", { maximumFractionDigits: digits, minimumFractionDigits: digits })}x`;
  return v.toLocaleString("fr-FR", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function fmt(key: string, v: number | null | undefined, digits = 1): string {
  return formatValue(v, RANGES[key]?.unite ?? "pts", digits);
}
