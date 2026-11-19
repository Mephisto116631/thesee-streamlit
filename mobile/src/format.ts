export const pct = (v: number | null | undefined, d = 1, signed = true) => {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  // Arrondi d'abord : évite « -0 % » / « +0 % » pour une variation quasi nulle
  const r = Math.round(v * 100 * 10 ** d) / 10 ** d || 0;
  return `${signed && r > 0 ? "+" : ""}${r.toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d })} %`;
};

export const num = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : v.toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });

export const prix = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${num(v, 2)} $`);

export function dateFr(iso: string | null | undefined, avecHeure = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("fr-FR", avecHeure
    ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }
    : { day: "numeric", month: "short", year: "numeric" });
}

export function ilYA(iso: string | null | undefined): string {
  if (!iso) return "jamais";
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 60) return `il y a ${min} min`;
  const h = Math.round(min / 60);
  if (h < 48) return `il y a ${h} h`;
  return `il y a ${Math.round(h / 24)} jours`;
}

export const signClass = (v: number | null | undefined) =>
  v === null || v === undefined ? "" : v > 0 ? "up" : v < 0 ? "down" : "";

/** Corrélation ou IC affiché en % (0,077 -> « 7,7 % »). */
export const corr = (v: number | null | undefined, d = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${(v * 100).toLocaleString("fr-FR", { maximumFractionDigits: d, minimumFractionDigits: d })} %`;
/** Spread en points de base affiché en % (305 pb -> « 3,05 % »). */
export const pb = (v: number | null | undefined) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `${(v / 100).toLocaleString("fr-FR", { maximumFractionDigits: 2, minimumFractionDigits: 2 })} %`;
/** Rendement / risque en % (0,57 -> « 57 % »). */
export const ratioPct = (rendement: number, vol: number) => `${Math.round((rendement / Math.max(vol, 1e-9)) * 100)} %`;
