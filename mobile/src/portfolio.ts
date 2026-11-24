// Calculs de portefeuille — légers, faits sur le téléphone (1 an de cours).
import type { PricePoint } from "./api";

export const RF = 0.0435; // taux sans risque de repli (le serveur publie celui du jour : docs/METHODE.md § 2.1)

/** Matrice de rendements quotidiens alignée sur les dates communes à tous les titres. */
export function returnsMatrix(points: PricePoint[], symbols: string[]) {
  const bySym = new Map<string, Map<string, number>>();
  for (const p of points) {
    if (!bySym.has(p.symbol)) bySym.set(p.symbol, new Map());
    bySym.get(p.symbol)!.set(p.date, p.close);
  }
  const syms = symbols.filter((s) => bySym.has(s));
  if (!syms.length) return { syms, dates: [] as string[], R: [] as number[][] };
  const dates = [...bySym.get(syms[0])!.keys()].filter((d) => syms.every((s) => bySym.get(s)!.has(d))).sort();
  const R: number[][] = [];
  for (let i = 1; i < dates.length; i++) {
    R.push(syms.map((s) => bySym.get(s)!.get(dates[i])! / bySym.get(s)!.get(dates[i - 1])! - 1));
  }
  return { syms, dates: dates.slice(1), R };
}

const mean = (a: number[]) => a.reduce((x, y) => x + y, 0) / (a.length || 1);

export function covariance(R: number[][]): number[][] {
  const n = R[0]?.length ?? 0;
  const mu = Array.from({ length: n }, (_, j) => mean(R.map((r) => r[j])));
  return Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j) =>
    R.reduce((acc, r) => acc + (r[i] - mu[i]) * (r[j] - mu[j]), 0) / Math.max(1, R.length - 1)));
}

/** Inverse par Gauss-Jordan ; null si la matrice est singulière. */
export function inverse(M: number[][]): number[][] | null {
  const n = M.length;
  const A = M.map((row, i) => [...row, ...Array.from({ length: n }, (_, j) => (i === j ? 1 : 0))]);
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(A[r][c]) > Math.abs(A[p][c])) p = r;
    if (Math.abs(A[p][c]) < 1e-14) return null;
    [A[c], A[p]] = [A[p], A[c]];
    const d = A[c][c];
    for (let j = 0; j < 2 * n; j++) A[c][j] /= d;
    for (let r = 0; r < n; r++) if (r !== c) {
      const f = A[r][c];
      for (let j = 0; j < 2 * n; j++) A[r][j] -= f * A[c][j];
    }
  }
  return A.map((row) => row.slice(n));
}

/** Poids : équipondéré, ou Markowitz (portefeuille tangent, ventes à découvert interdites). */
/** Plafonne chaque poids à `cap` en redistribuant l'excédent sur les autres. */
export function capWeights(w: number[], cap: number): number[] {
  let out = [...w];
  if (cap * out.length < 1) return out; // plafond impossible à respecter
  for (let it = 0; it < 20; it++) {
    const over = out.map((v) => v > cap + 1e-12);
    if (!over.some(Boolean)) break;
    const surplus = out.reduce((a, v, i) => a + (over[i] ? v - cap : 0), 0);
    const rest = out.reduce((a, v, i) => a + (over[i] ? 0 : v), 0);
    out = out.map((v, i) => over[i] ? cap : rest > 0 ? v + surplus * v / rest : v + surplus / out.filter((_, j) => !over[j]).length);
  }
  return out;
}

export const POIDS_MAX = 0.2; // même plafond que le portefeuille recommandé (portefeuille.py)

export function weights(R: number[][], mode: "equal" | "markowitz", rf = RF): number[] {
  const n = R[0]?.length ?? 0;
  const eq = Array(n).fill(1 / n);
  if (mode === "equal" || n < 2) return eq;
  const cov = covariance(R).map((r) => r.map((v) => v * 252));
  const inv = inverse(cov);
  if (!inv) return eq;
  const ex = Array.from({ length: n }, (_, j) => mean(R.map((r) => r[j])) * 252 - rf);
  let w = inv.map((row) => row.reduce((acc, v, j) => acc + v * ex[j], 0)).map((v) => Math.max(0, v));
  const s = w.reduce((a, b) => a + b, 0);
  return s > 0 ? capWeights(w.map((v) => v / s), POIDS_MAX) : eq;
}

export function portfolioStats(R: number[][], w: number[], rf = RF) {
  const pr = R.map((r) => r.reduce((acc, v, j) => acc + v * w[j], 0));
  const mu = mean(pr) * 252;
  const vol = Math.sqrt(pr.reduce((a, v) => a + (v - mean(pr)) ** 2, 0) / Math.max(1, pr.length - 1)) * Math.sqrt(252);
  let peak = 1, val = 1, mdd = 0;
  const curve = pr.map((r) => { val *= 1 + r; peak = Math.max(peak, val); mdd = Math.min(mdd, val / peak - 1); return val; });
  return { returns: pr, annReturn: mu, annVol: vol, sharpe: vol > 0 ? (mu - rf) / vol : 0, maxDrawdown: mdd, curve };
}

/** Monte-Carlo par ré-échantillonnage des rendements historiques (bootstrap). */
export function monteCarlo(pr: number[], capital: number, days = 252, sims = 1000, seed = 42) {
  let s = seed;
  const rand = () => ((s = (s * 1664525 + 1013904223) % 4294967296) / 4294967296);
  const paths: Float64Array[] = [];
  for (let k = 0; k < sims; k++) {
    const p = new Float64Array(days);
    let v = capital;
    for (let d = 0; d < days; d++) { v *= 1 + pr[Math.floor(rand() * pr.length)]; p[d] = v; }
    paths.push(p);
  }
  const q = (arr: number[], x: number) => { const a = [...arr].sort((m, n) => m - n); return a[Math.min(a.length - 1, Math.floor(x * a.length))]; };
  const p5: number[] = [], p50: number[] = [], p95: number[] = [];
  for (let d = 0; d < days; d++) {
    const col = paths.map((p) => p[d]);
    p5.push(q(col, 0.05)); p50.push(q(col, 0.5)); p95.push(q(col, 0.95));
  }
  const finals = paths.map((p) => p[days - 1]);
  return { p5, p50, p95, probPerte: finals.filter((v) => v < capital).length / sims, final5: p5[days - 1], final50: p50[days - 1], final95: p95[days - 1] };
}
