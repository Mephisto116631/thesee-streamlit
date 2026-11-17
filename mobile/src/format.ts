export const pct = (v: number | null | undefined, d = 1, signed = true) =>
  v === null || v === undefined || Number.isNaN(v)
    ? "—"
    : `${signed && v > 0 ? "+" : ""}${(v * 100).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d })} %`;

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
