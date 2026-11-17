// Optimisation de portefeuille sur le téléphone, avec les hypothèses de l'utilisateur.
// Le serveur publie les « ingrédients » (rendements historiques, bêtas, covariance
// des ~40 candidats) ; ici on recalcule rendements attendus et frontière efficiente.
//
// Méthode : pour une grille de compromis risque/rendement λ, on minimise
//   f(w) = wᵀΣw − λ·wᵀμ   sous   0 ≤ w ≤ plafond, Σw = 1
// par gradient projeté accéléré (FISTA). Chaque λ donne un point de la frontière.
// Puis épuration : au plus N lignes d'au moins p %, en ré-optimisant sur les lignes gardées.

export interface Univers { symbols: string[]; mu_hist: number[]; beta: number[]; cov: number[][]; jours: number }

export interface HypothesesModele {
  tauxSansRisque: number;   // 0.0435
  primeRisque: number;      // 0.05
  poidsHistorique: number;  // 0.10
  poidsMax: number;         // 0.20
  nMaxLignes: number;       // 12
  poidsMin: number;         // 0.03
}

export interface Point { rendement: number; volatilite: number; sharpe: number; lignes: { symbol: string; poids: number }[] }

export function rendementsAttendus(u: Univers, h: HypothesesModele): number[] {
  return u.beta.map((b, i) => (1 - h.poidsHistorique) * (h.tauxSansRisque + b * h.primeRisque) + h.poidsHistorique * u.mu_hist[i]);
}

/** Projection euclidienne sur {0 ≤ w ≤ cap, Σw = 1} (recherche du seuil par dichotomie). */
export function projeterSimplexePlafonne(v: Float64Array, cap: number): Float64Array {
  const n = v.length;
  const somme = (t: number) => { let s = 0; for (let i = 0; i < n; i++) s += Math.min(cap, Math.max(0, v[i] - t)); return s; };
  let lo = Math.min(...v) - cap, hi = Math.max(...v);
  for (let k = 0; k < 60; k++) { const mid = (lo + hi) / 2; if (somme(mid) > 1) lo = mid; else hi = mid; }
  const t = (lo + hi) / 2;
  const w = new Float64Array(n);
  for (let i = 0; i < n; i++) w[i] = Math.min(cap, Math.max(0, v[i] - t));
  return w;
}

function matVec(S: Float64Array[], w: Float64Array): Float64Array {
  const n = w.length, out = new Float64Array(n);
  for (let i = 0; i < n; i++) { let s = 0; const r = S[i]; for (let j = 0; j < n; j++) s += r[j] * w[j]; out[i] = s; }
  return out;
}

/** min wᵀΣw − λ wᵀμ sur le simplexe plafonné (FISTA). */
export function resoudre(S: Float64Array[], mu: Float64Array, lambda: number, cap: number, iters = 400): Float64Array {
  const n = mu.length;
  // Constante de Lipschitz du gradient 2Σw : 2 × (norme de Frobenius ≥ plus grande valeur propre)
  let fro = 0; for (const r of S) for (const x of r) fro += x * x;
  const pas = 1 / (2 * Math.sqrt(fro) + 1e-12);
  let w = projeterSimplexePlafonne(new Float64Array(n).fill(1 / n), cap);
  let y = w, t = 1;
  for (let k = 0; k < iters; k++) {
    const g = matVec(S, y);
    const v = new Float64Array(n);
    for (let i = 0; i < n; i++) v[i] = y[i] - pas * (2 * g[i] - lambda * mu[i]);
    const wNext = projeterSimplexePlafonne(v, cap);
    const tNext = (1 + Math.sqrt(1 + 4 * t * t)) / 2;
    const yNext = new Float64Array(n);
    for (let i = 0; i < n; i++) yNext[i] = wNext[i] + ((t - 1) / tNext) * (wNext[i] - w[i]);
    w = wNext; y = yNext; t = tNext;
  }
  return w;
}

function sousMatrice(cov: number[][], idx: number[]): Float64Array[] {
  return idx.map((i) => Float64Array.from(idx.map((j) => cov[i][j])));
}

/** Résout puis épure (≤ nMax lignes ≥ poidsMin) en ré-optimisant sur les lignes gardées. */
function resoudreEpure(u: Univers, mu: number[], lambda: number, h: HypothesesModele): { idx: number[]; w: Float64Array } {
  let idx = u.symbols.map((_, i) => i);
  const nMin = Math.ceil(1 / h.poidsMax - 1e-9);
  let w = resoudre(sousMatrice(u.cov, idx), Float64Array.from(idx.map((i) => mu[i])), lambda, h.poidsMax);
  for (let tour = 0; tour < 4; tour++) {
    const ordre = [...w.keys()].sort((a, b) => w[b] - w[a]);
    let garder = ordre.slice(0, h.nMaxLignes).filter((k) => w[k] >= h.poidsMin);
    if (garder.length < nMin) garder = ordre.slice(0, Math.max(nMin, Math.min(h.nMaxLignes, ordre.length)));
    if (garder.length === idx.length) break;
    idx = garder.sort((a, b) => a - b).map((k) => idx[k]);
    w = resoudre(sousMatrice(u.cov, idx), Float64Array.from(idx.map((i) => mu[i])), lambda, h.poidsMax);
  }
  return { idx, w };
}

export function frontiere(u: Univers, h: HypothesesModele, nPoints = 18): Point[] {
  const n = u.symbols.length;
  if (n === 0 || h.poidsMax * Math.min(n, h.nMaxLignes) < 1 - 1e-9) return [];
  const mu = rendementsAttendus(u, h);
  // Échelle de λ : rapport entre variance typique et rendement typique
  const diag = u.cov.map((r, i) => r[i]);
  const echelle = (diag.reduce((a, b) => a + b, 0) / n) / (Math.max(...mu.map(Math.abs)) || 1);
  const lambdas = [0, ...Array.from({ length: nPoints - 1 }, (_, k) => echelle * Math.pow(10, -2 + (3.5 * k) / (nPoints - 2)))];

  const pts: Point[] = [];
  for (const lambda of lambdas) {
    const { idx, w } = resoudreEpure(u, mu, lambda, h);
    let r = 0, v = 0;
    for (let a = 0; a < idx.length; a++) {
      r += w[a] * mu[idx[a]];
      for (let b = 0; b < idx.length; b++) v += w[a] * w[b] * u.cov[idx[a]][idx[b]];
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
