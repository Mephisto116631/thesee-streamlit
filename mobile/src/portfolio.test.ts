import { describe, expect, it } from "vitest";
import { inverse, monteCarlo, portfolioStats, returnsMatrix, weights } from "./portfolio";
import { zoneIndex } from "./ranges";

describe("ranges", () => {
  it("classe aux bornes (bornes incluses dans la zone centrale)", () => {
    expect(zoneIndex("rsi_14", 29.9)).toBe(0);
    expect(zoneIndex("rsi_14", 30)).toBe(1);
    expect(zoneIndex("rsi_14", 70)).toBe(1);
    expect(zoneIndex("rsi_14", 70.1)).toBe(2);
    expect(zoneIndex("z_score", 1.5)).toBe(0);
    expect(zoneIndex("z_score", null)).toBe(null);
  });
});

describe("portefeuille", () => {
  const pts = ["A", "B"].flatMap((s, k) =>
    Array.from({ length: 60 }, (_, i) => ({ symbol: s, date: `2026-01-${String(i).padStart(3, "0")}`, close: 100 * (1 + 0.001 * (k + 1)) ** i * (1 + 0.01 * Math.sin(i * (k + 2))) })));
  it("aligne les dates et calcule les rendements", () => {
    const { syms, R } = returnsMatrix(pts, ["A", "B", "ZZZ"]);
    expect(syms).toEqual(["A", "B"]);
    expect(R.length).toBe(59);
  });
  it("inverse une matrice", () => {
    const inv = inverse([[2, 0], [0, 4]])!;
    expect(inv[0][0]).toBeCloseTo(0.5);
    expect(inv[1][1]).toBeCloseTo(0.25);
    expect(inverse([[1, 1], [1, 1]])).toBeNull();
  });
  it("poids positifs et sommant à 1", () => {
    const { R } = returnsMatrix(pts, ["A", "B"]);
    for (const mode of ["equal", "markowitz"] as const) {
      const w = weights(R, mode);
      expect(w.reduce((a, b) => a + b, 0)).toBeCloseTo(1);
      expect(Math.min(...w)).toBeGreaterThanOrEqual(0);
    }
  });
  it("Monte-Carlo ordonne les quantiles", () => {
    const { R } = returnsMatrix(pts, ["A", "B"]);
    const st = portfolioStats(R, [0.5, 0.5]);
    expect(st.maxDrawdown).toBeLessThanOrEqual(0);
    const mc = monteCarlo(st.returns, 1000, 50, 200);
    expect(mc.final5).toBeLessThanOrEqual(mc.final50);
    expect(mc.final50).toBeLessThanOrEqual(mc.final95);
  });
});

import { bornesTexte } from "./ranges";
describe("libellés des bornes", () => {
  it("garde les décimales utiles", () => {
    expect(bornesTexte("z_score")[0]).toBe("< 1,81");
    expect(bornesTexte("debt_eq")[1]).toBe("0,5x – 1,5x");
    expect(bornesTexte("chg_20d")[2]).toBe("> 5 %");
  });
});

import { capWeights } from "./portfolio";
describe("plafond des poids", () => {
  it("plafonne à 20 % et garde une somme de 1", () => {
    const w = capWeights([0.6, 0.1, 0.1, 0.1, 0.05, 0.05], 0.2);
    expect(Math.max(...w)).toBeLessThanOrEqual(0.2 + 1e-9);
    expect(w.reduce((a, b) => a + b, 0)).toBeCloseTo(1);
  });
});

import { pct } from "./format";
describe("format", () => {
  it("n'affiche pas -0 %", () => {
    expect(pct(-0.001, 0)).toBe("0 %");
    expect(pct(0.054, 0)).toBe("+5 %");
  });
});

import { probaAuDessus } from "./portfolio";
import { echeance, probaTexte } from "./screens/MonteCarlo";
describe("Monte-Carlo interactif", () => {
  const pr = Array.from({ length: 250 }, (_, i) => 0.01 * Math.sin(i * 1.7) + 0.0003);
  const mc = monteCarlo(pr, 1000, 60, 500);
  it("la grille des centiles va du minimum au maximum, sans décroître", () => {
    const g = mc.grille[59];
    expect(g.length).toBe(101);
    for (let i = 1; i < g.length; i++) expect(g[i]).toBeGreaterThanOrEqual(g[i - 1]);
    expect(g[50]).toBeCloseTo(mc.p50[59], -1);
  });
  it("la probabilité d'avoir plus vaut 50 % à la médiane, 0 et 1 aux extrêmes, et décroît", () => {
    expect(probaAuDessus(mc.grille, 59, mc.grille[59][50])).toBeCloseTo(0.5, 1);
    expect(probaAuDessus(mc.grille, 59, 0)).toBe(1);
    expect(probaAuDessus(mc.grille, 59, 1e9)).toBe(0);
    expect(probaAuDessus(mc.grille, 59, mc.p5[59])).toBeGreaterThan(probaAuDessus(mc.grille, 59, mc.p95[59]));
    expect(probaAuDessus(mc.grille, 999, mc.grille[59][50])).toBeCloseTo(0.5, 1);   // jour hors bornes : dernier jour
  });
  it("cohérente avec la probabilité de perte", () => {
    expect(1 - probaAuDessus(mc.grille, 59, 1000)).toBeCloseTo(mc.probPerte, 1);
  });
  it("libellés", () => {
    expect(echeance(20)).toBe("dans 1 mois");
    expect(echeance(21 * 30 - 1)).toBe("dans 2,5 ans");
    expect(probaTexte(0.004)).toBe("< 1 %");
    expect(probaTexte(0.995)).toBe("> 99 %");
    expect(probaTexte(0.64)).toBe("64 %");
  });
});
