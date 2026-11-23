import { describe, expect, it } from "vitest";
import { rejouerCrises, risqueMois, volPortefeuille, JOURS_MOIS } from "./chocs";
import { zStudent5 } from "./strategy";
import type { Univers } from "./optim";

const chocs = {
  crises: [
    { nom: "2020 (Covid)", debut: "2020-02-19", fin: "2020-03-23", marche: -0.34, retour_jours: 103 },
    { nom: "2008 (crise financière)", debut: "2007-10-09", fin: "2009-03-09", marche: -0.55, retour_jours: 1000 },
  ],
  rendements: [[-0.2, -0.6], [-0.4, null], [-0.1, -0.3]],
};

describe("stress test", () => {
  it("somme pondérée des chutes réelles, la pire crise du marché d'abord", () => {
    const r = rejouerCrises(chocs, ["A", "B", "C"], [1, 1.2, 0.8], [{ symbol: "A", poids: 0.5 }, { symbol: "C", poids: 0.5 }]);
    expect(r[0].nom).toContain("2008");
    expect(r[0].portefeuille).toBeCloseTo(0.5 * -0.6 + 0.5 * -0.3, 12);
    expect(r[1].portefeuille).toBeCloseTo(0.5 * -0.2 + 0.5 * -0.1, 12);
    expect(r[0].partEstimee).toBe(0);
  });
  it("titre absent à l'époque : bêta × chute du marché, part estimée affichée", () => {
    const r = rejouerCrises(chocs, ["A", "B", "C"], [1, 1.2, 0.8], [{ symbol: "A", poids: 0.75 }, { symbol: "B", poids: 0.25 }]);
    const c2008 = r.find((c) => c.nom.startsWith("2008"))!;
    expect(c2008.portefeuille).toBeCloseTo(0.75 * -0.6 + 0.25 * 1.2 * -0.55, 12);
    expect(c2008.partEstimee).toBeCloseTo(0.25, 12);
  });
  it("sans données : rien", () => {
    expect(rejouerCrises(null, [], [], [{ symbol: "A", poids: 1 }])).toEqual([]);
  });
});

const u: Univers & { vol_1m?: (number | null)[] } = {
  symbols: ["A", "B"], mu_hist: [0, 0], beta: [1, 1], jours: 756,
  cov: [[0.04, 0.01], [0.01, 0.09]],
};

describe("risque du mois", () => {
  it("volatilité du portefeuille = √(wᵀΣw)", () => {
    const v = volPortefeuille(u, [{ symbol: "A", poids: 0.5 }, { symbol: "B", poids: 0.5 }])!;
    expect(v.vol).toBeCloseTo(Math.sqrt(0.25 * 0.04 + 0.25 * 0.09 + 2 * 0.25 * 0.01), 12);
  });
  it("vol prévue doublée → risque doublé, corrélations gardées ; mauvais cas Student-5 sur 22 séances", () => {
    const r = risqueMois({ ...u, vol_1m: [0.4, 0.6] }, [{ symbol: "A", poids: 0.5 }, { symbol: "B", poids: 0.5 }])!;
    expect(r.rapport).toBeCloseTo(2, 12);
    const z = zStudent5(0.9);
    expect(z).toBeCloseTo(2.015, 3);
    expect(r.mauvaisCas).toBeCloseTo(1 - Math.exp(-z * r.volAn * Math.sqrt(JOURS_MOIS / 252)), 12);
  });
  it("non publié : rien", () => {
    expect(risqueMois(u, [{ symbol: "A", poids: 1 }])).toBeNull();
  });
});
