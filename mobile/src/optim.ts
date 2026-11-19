// Optimisation de portefeuille sur le téléphone, avec les hypothèses de l'utilisateur.
// Le serveur publie les « ingrédients » des ~500 titres du S&P 500 (rendements
// historiques, bêtas, covariance) ; ici on recalcule rendements attendus et frontière.
// Même algorithme que le serveur (portefeuille.py) : journal des choix dans docs/METHODE.md.
//
// Covariance sous forme factorielle : Σ = B·Bᵀ + diag(D) (20 composantes principales +
// risque propre de chaque titre). Une matrice 500 x 500 pèserait ~3 Mo ; ainsi ~150 Ko,
// et Σw ne coûte que 500 x 20 opérations. Ancien format (`cov` dense) toujours lu.
//
// Méthode : pour une grille de compromis risque/rendement λ, on minimise
//   f(w) = wᵀΣw − λ·wᵀμ   sous   0 ≤ w ≤ plafond, Σw = 1
// par gradient projeté accéléré (FISTA). Chaque λ donne un point de la frontière.
// Puis épuration : au plus N lignes d'au moins p %, en ré-optimisant sur les lignes gardées.

export interface Univers {
  symbols: string[]; mu_hist: number[]; beta: number[]; jours: number;
  facteurs?: number[][];   // B : n x k
  idio?: number[];         // D : risque propre (variance) de chaque titre
  cov?: number[][];        // ancien format : covariance dense (n x n)
  vol_ia?: (number | null)[];   // volatilité annuelle prévue par l'IA de risque (6 mois)
}

export interface HypothesesModele {
  tauxSansRisque: number;   // 0.0435
  primeRisque: number;      // 0.05
  poidsHistorique: number;  // 0.10
  poidsMax: number;         // 0.20
  nMaxLignes: number;       // 12
  poidsMin: number;         // 0.03
  sourceVol?: "historique" | "ia"; // volatilités utilisées : 3 ans d'historique, ou prévues par l'IA
  imposes?: string[];        // titres que l'utilisateur veut garder (au moins le poids minimal)
}

/** Univers sans les titres exclus par l'utilisateur (même ingrédients, mêmes calculs). */
export function sousUnivers(u: Univers, exclus: string[]): Univers {
  if (!exclus.length) return u;
  const garde = u.symbols.map((s, i) => [s, i] as const).filter(([s]) => !exclus.includes(s)).map(([, i]) => i);
  return {
    ...u,
    symbols: garde.map((i) => u.symbols[i]), mu_hist: garde.map((i) => u.mu_hist[i]), beta: garde.map((i) => u.beta[i]),
    ...(u.facteurs ? { facteurs: garde.map((i) => u.facteurs![i]), idio: garde.map((i) => u.idio![i]) }
      : { cov: garde.map((i) => garde.map((j) => u.cov![i][j])) }),
    vol_ia: u.vol_ia ? garde.map((i) => u.vol_ia![i]) : undefined,
  };
}

/** Covariance entre deux titres (forme factorielle ou dense). */
export function covariance(u: Univers, i: number, j: number): number {
  if (u.facteurs) {
    const a = u.facteurs[i], b = u.facteurs[j];
    let s = i === j ? u.idio![i] : 0;
    for (let k = 0; k < a.length; k++) s += a[k] * b[k];
    return s;
  }
  return u.cov![i][j];
}
export const variance = (u: Univers, i: number) => covariance(u, i, i);

/** Volatilité historique (3 ans) de chaque titre : racine de la diagonale de la covariance. */
export const volHistorique = (u: Univers) => u.symbols.map((_, i) => Math.sqrt(Math.max(variance(u, i), 0)));

/** Covariance avec les volatilités prévues par l'IA et les corrélations historiques (3 ans).
 *  Titre sans prévision : volatilité historique conservée. */
export function avecVolIA(u: Univers): Univers {
  if (!u.vol_ia?.length) return u;
  const sdH = volHistorique(u);
  const sd = sdH.map((v, i) => (u.vol_ia![i] != null && u.vol_ia![i]! > 0 ? u.vol_ia![i]! : v));
  const s = sd.map((v, i) => (sdH[i] > 0 ? v / sdH[i] : 1));
  // Σ' = S·Σ·S (S = diag(vol prévue / vol historique)) : corrélations inchangées
  if (u.facteurs) return { ...u, facteurs: u.facteurs.map((r, i) => r.map((x) => x * s[i])), idio: u.idio!.map((d, i) => d * s[i] * s[i]) };
  const cov = u.cov!.map((r, i) => r.map((c, j) => c * s[i] * s[j]));
  return { ...u, cov };
}

export interface Point { rendement: number; volatilite: number; sharpe: number; lignes: { symbol: string; poids: number }[] }

export function rendementsAttendus(u: Univers, h: HypothesesModele): number[] {
  return u.beta.map((b, i) => (1 - h.poidsHistorique) * (h.tauxSansRisque + b * h.primeRisque) + h.poidsHistorique * u.mu_hist[i]);
}

/** Projection euclidienne sur {min_i ≤ w_i ≤ cap, Σw = 1} (recherche du seuil par dichotomie).
 *  `min` : poids minimal par titre (0 par défaut ; > 0 pour un titre imposé par l'utilisateur). */
export function projeterSimplexePlafonne(v: Float64Array, cap: number, min?: Float64Array): Float64Array {
  const n = v.length;
  const bas = (i: number) => (min ? min[i] : 0);
  const somme = (t: number) => { let s = 0; for (let i = 0; i < n; i++) s += Math.min(cap, Math.max(bas(i), v[i] - t)); return s; };
  const remplir = (t: number) => { const w = new Float64Array(n); for (let i = 0; i < n; i++) w[i] = Math.min(cap, Math.max(bas(i), v[i] - t)); return w; };
  // Σ clip(v − τ) est affine par morceaux en τ : Newton tombe sur la valeur exacte en quelques pas
  let t = 0; for (let i = 0; i < n; i++) t += v[i]; t = t / n - 1 / n;
  for (let k = 0; k < 30; k++) {
    let s = 0, actifs = 0;
    for (let i = 0; i < n; i++) { const x = v[i] - t; s += Math.min(cap, Math.max(bas(i), x)); if (x > bas(i) && x < cap) actifs++; }
    if (Math.abs(s - 1) < 1e-13) return remplir(t);
    if (actifs === 0) break;
    t += (s - 1) / actifs;
  }
  // Repli : dichotomie
  let lo = Math.min(...v) - cap - 1, hi = Math.max(...v) + 1;
  for (let k = 0; k < 80; k++) { const mid = (lo + hi) / 2; if (somme(mid) > 1) lo = mid; else hi = mid; }
  return remplir((lo + hi) / 2);
}

/** Opérateur de covariance : matrice dense, ou forme factorielle B·Bᵀ + diag(D). */
export type Risque = Float64Array[] | { B: Float64Array[]; D: Float64Array };

function mulRisque(S: Risque, w: Float64Array): Float64Array {
  if (Array.isArray(S)) return matVec(S, w);
  const n = w.length, k = n ? S.B[0].length : 0, z = new Float64Array(k), out = new Float64Array(n);
  for (let i = 0; i < n; i++) { const r = S.B[i]; for (let j = 0; j < k; j++) z[j] += r[j] * w[i]; }
  for (let i = 0; i < n; i++) { const r = S.B[i]; let s = S.D[i] * w[i]; for (let j = 0; j < k; j++) s += r[j] * z[j]; out[i] = s; }
  return out;
}

/** Majorant de la plus grande valeur propre de Σ (pas de FISTA). */
function normeRisque(S: Risque): number {
  if (Array.isArray(S)) { let fro = 0; for (const r of S) for (const x of r) fro += x * x; return Math.sqrt(fro); }
  // ‖B·Bᵀ‖ = plus grande valeur propre de Bᵀ·B (k x k) : itération de la puissance, majorée de 1 %
  const n = S.B.length, k = n ? S.B[0].length : 0;
  const G = Array.from({ length: k }, () => new Float64Array(k));
  for (const r of S.B) for (let a = 0; a < k; a++) for (let b = 0; b < k; b++) G[a][b] += r[a] * r[b];
  let x: Float64Array = new Float64Array(k).fill(1), lam = 0;
  for (let it = 0; it < 100; it++) {
    const y = new Float64Array(k);
    for (let a = 0; a < k; a++) { let s = 0; for (let b = 0; b < k; b++) s += G[a][b] * x[b]; y[a] = s; }
    const nrm = Math.hypot(...y) || 1; lam = nrm / (Math.hypot(...x) || 1); x = y.map((v) => v / nrm);
  }
  let maxD = 0; for (const d of S.D) maxD = Math.max(maxD, d);
  return lam * 1.01 + maxD;
}

function matVec(S: Float64Array[], w: Float64Array): Float64Array {
  const n = w.length, out = new Float64Array(n);
  for (let i = 0; i < n; i++) { let s = 0; const r = S[i]; for (let j = 0; j < n; j++) s += r[j] * w[j]; out[i] = s; }
  return out;
}

/** min wᵀΣw − λ wᵀμ sur le simplexe plafonné (FISTA). */
export function resoudre(S: Risque, mu: Float64Array, lambda: number, cap: number, iters = 400, min?: Float64Array): Float64Array {
  const n = mu.length;
  // Constante de Lipschitz du gradient 2Σw : 2 × (majorant de la plus grande valeur propre)
  const pas = 1 / (2 * normeRisque(S) + 1e-12);
  let w = projeterSimplexePlafonne(new Float64Array(n).fill(1 / n), cap, min);
  let y = w, t = 1;
  for (let k = 0; k < iters; k++) {
    const g = mulRisque(S, y);
    const v = new Float64Array(n);
    for (let i = 0; i < n; i++) v[i] = y[i] - pas * (2 * g[i] - lambda * mu[i]);
    const wNext = projeterSimplexePlafonne(v, cap, min);
    const tNext = (1 + Math.sqrt(1 + 4 * t * t)) / 2;
    const yNext = new Float64Array(n);
    for (let i = 0; i < n; i++) yNext[i] = wNext[i] + ((t - 1) / tNext) * (wNext[i] - w[i]);
    w = wNext; y = yNext; t = tNext;
  }
  return w;
}

function sousRisque(u: Univers, idx: number[]): Risque {
  if (u.facteurs) return { B: idx.map((i) => Float64Array.from(u.facteurs![i])), D: Float64Array.from(idx.map((i) => u.idio![i])) };
  return idx.map((i) => Float64Array.from(idx.map((j) => u.cov![i][j])));
}

/** Résout puis épure (≤ nMax lignes ≥ poidsMin) en ré-optimisant sur les lignes gardées. */
function resoudreEpure(u: Univers, mu: number[], lambda: number, h: HypothesesModele): { idx: number[]; w: Float64Array } {
  let idx = u.symbols.map((_, i) => i);
  const nMin = Math.ceil(1 / h.poidsMax - 1e-9);
  // Titres imposés : poids minimal garanti (poidsMin, au moins 1 %), jamais retirés à l'épuration
  const imposes = new Set((h.imposes ?? []).map((s) => u.symbols.indexOf(s)).filter((i) => i >= 0));
  const plancher = Math.max(h.poidsMin, 0.01);
  const mins = (ids: number[]) => (imposes.size ? Float64Array.from(ids.map((i) => (imposes.has(i) ? plancher : 0))) : undefined);
  const res = (ids: number[]) => resoudre(sousRisque(u, ids), Float64Array.from(ids.map((i) => mu[i])), lambda, h.poidsMax, 400, mins(ids));
  let w = res(idx);
  for (let tour = 0; tour < 4; tour++) {
    const ordre = [...w.keys()].sort((a, b) => w[b] - w[a]);
    const forces = ordre.filter((k) => imposes.has(idx[k]));
    let garder = [...forces, ...ordre.filter((k) => !imposes.has(idx[k]) && w[k] >= h.poidsMin)].slice(0, Math.max(h.nMaxLignes, forces.length));
    if (garder.length < nMin) garder = [...new Set([...forces, ...ordre])].slice(0, Math.max(nMin, Math.min(h.nMaxLignes, ordre.length)));
    if (garder.length === idx.length) break;
    idx = garder.sort((a, b) => a - b).map((k) => idx[k]);
    w = res(idx);
  }
  return { idx, w };
}

export function frontiere(u0: Univers, h: HypothesesModele, nPoints = 18): Point[] {
  const u = h.sourceVol === "ia" ? avecVolIA(u0) : u0;
  const n = u.symbols.length;
  if (n === 0 || h.poidsMax * Math.min(n, h.nMaxLignes) < 1 - 1e-9) return [];
  const mu = rendementsAttendus(u, h);
  // Échelle de λ : rapport entre variance typique et rendement typique
  const diag = u.symbols.map((_, i) => variance(u, i));
  const echelle = (diag.reduce((a, b) => a + b, 0) / n) / (Math.max(...mu.map(Math.abs)) || 1);
  const lambdas = [0, ...Array.from({ length: nPoints - 1 }, (_, k) => echelle * Math.pow(10, -2 + (3.5 * k) / (nPoints - 2)))];

  const pts: Point[] = [];
  for (const lambda of lambdas) {
    const { idx, w } = resoudreEpure(u, mu, lambda, h);
    let r = 0, v = 0;
    for (let a = 0; a < idx.length; a++) {
      r += w[a] * mu[idx[a]];
      for (let b = 0; b < idx.length; b++) v += w[a] * w[b] * covariance(u, idx[a], idx[b]);
    }
    const vol = Math.sqrt(Math.max(v, 0));
    const lignes = idx.map((i, a) => ({ symbol: u.symbols[i], poids: w[a] }))
      .filter((l) => l.poids > 1e-6).sort((x, y) => y.poids - x.poids);
    const tot = lignes.reduce((s, l) => s + l.poids, 0);
    lignes.forEach((l) => (l.poids /= tot));
    pts.push({ rendement: r, volatilite: vol, sharpe: vol > 0 ? (r - h.tauxSansRisque) / vol : 0, lignes });
  }
  // Frontière au sens strict : ni doublons, ni points dominés (2 % de tolérance sur le risque)
  pts.sort((a, b) => a.rendement - b.rendement);
  const garde = pts.filter((a) => !pts.some((b) => b !== a && b.rendement > a.rendement + 1e-6 && b.volatilite <= a.volatilite * 1.02));
  return garde.filter((p, i) => i === 0 || p.rendement - garde[i - 1].rendement > 1e-5);
}

/** Portefeuille au meilleur ratio de Sharpe sur la frontière. */
export function tangent(points: Point[]): Point | null {
  return points.reduce<Point | null>((best, p) => (!best || p.sharpe > best.sharpe ? p : best), null);
}
