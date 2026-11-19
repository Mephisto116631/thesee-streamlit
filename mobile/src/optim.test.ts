import { describe, expect, it } from "vitest";
import { frontiere, projeterSimplexePlafonne, rendementsAttendus, resoudre, tangent, type Univers } from "./optim";
import fx from "./fixtures/univers-test.json";

const u = fx.univers as Univers;
const h = fx.hypotheses;

describe("projection", () => {
  it("respecte somme = 1 et plafond", () => {
    const w = projeterSimplexePlafonne(Float64Array.from([0.9, 0.5, -0.2, 0.1, 0.3, 0.05]), 0.25);
    expect(w.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 9);
    expect(Math.max(...w)).toBeLessThanOrEqual(0.25 + 1e-12);
    expect(Math.min(...w)).toBeGreaterThanOrEqual(0);
  });
});

describe("optimisation", () => {
  it("variance minimale de 2 titres non corrélés : poids ∝ 1/variance", () => {
    const S = [Float64Array.from([0.04, 0]), Float64Array.from([0, 0.01])];
    const w = resoudre(S, Float64Array.from([0, 0]), 0, 1, 2000);
    expect(w[0]).toBeCloseTo(0.2, 3);
    expect(w[1]).toBeCloseTo(0.8, 3);
  });

  it("rendements attendus = mêmes formules que le serveur", () => {
    const mu = rendementsAttendus(u, h);
    expect(mu[0]).toBeCloseTo((1 - h.poidsHistorique) * (h.tauxSansRisque + u.beta[0] * h.primeRisque) + h.poidsHistorique * u.mu_hist[0], 12);
  });

  it("frontière cohérente avec celle du serveur (scipy)", () => {
    const f = frontiere(u, h);
    expect(f.length).toBeGreaterThanOrEqual(4);
    for (let i = 1; i < f.length; i++) expect(f[i].rendement).toBeGreaterThan(f[i - 1].rendement);
    for (const p of f) {
      expect(p.lignes.length).toBeLessThanOrEqual(h.nMaxLignes);
      expect(Math.max(...p.lignes.map((l) => l.poids))).toBeLessThanOrEqual(h.poidsMax + 1e-6);
      expect(p.lignes.reduce((a, l) => a + l.poids, 0)).toBeCloseTo(1, 6);
    }
    const srv = fx.serveur;
    // Extrémités : même risque minimal (±1 pt) et même rendement maximal (±1 pt)
    expect(Math.abs(f[0].volatilite - srv[0].volatilite)).toBeLessThan(0.01);
    expect(Math.abs(f[f.length - 1].rendement - srv[srv.length - 1].rendement)).toBeLessThan(0.01);
    expect(tangent(f)).not.toBeNull();
  });

  it("change bien quand on change les hypothèses", () => {
    const prudent = frontiere(u, { ...h, primeRisque: 0.03 });
    const optimiste = frontiere(u, { ...h, primeRisque: 0.07 });
    expect(optimiste[optimiste.length - 1].rendement).toBeGreaterThan(prudent[prudent.length - 1].rendement);
    expect(frontiere(u, { ...h, poidsMax: 0.05, nMaxLignes: 12 })).toEqual([]); // 12 x 5 % < 100 % : impossible
  });
});

describe("volatilité prévue par l'IA", () => {
  it("garde les corrélations, remplace les volatilités", async () => {
    const { avecVolIA, volHistorique } = await import("./optim");
    const u = { symbols: ["A", "B"], mu_hist: [0.1, 0.1], beta: [1, 1], jours: 756,
      cov: [[0.04, 0.012], [0.012, 0.09]], vol_ia: [0.1, null] };
    const v = avecVolIA(u);
    expect(volHistorique(v)[0]).toBeCloseTo(0.1, 9);          // 20 % -> 10 % prévu
    expect(volHistorique(v)[1]).toBeCloseTo(0.3, 9);          // pas de prévision : historique
    const corr = (c: number[][]) => c[0][1] / Math.sqrt(c[0][0] * c[1][1]);
    expect(corr(v.cov)).toBeCloseTo(corr(u.cov), 9);
  });
  it("choisit le plus rentable sous le plafond de volatilité", async () => {
    const { choisirPointRisque } = await import("./strategy");
    const f = [0.08, 0.12, 0.2].map((vol, i) => ({ rendement: 0.05 + i * 0.02, volatilite: vol, sharpe: null, lignes: [] }));
    expect(choisirPointRisque(f, 0.15)!.point.volatilite).toBe(0.12);
    const trop = choisirPointRisque(f, 0.05)!;
    expect(trop.atteignable).toBe(false);
    expect(trop.point.volatilite).toBe(0.08);
  });
});
