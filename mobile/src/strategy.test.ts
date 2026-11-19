import { describe, expect, it } from "vitest";
import { choisirPoint, datesTranches, normCdf, planAchat, projection, REGLAGES_DEFAUT } from "./strategy";

const F = [0.06, 0.08, 0.1, 0.12].map((r, i) => ({ cible: r, rendement: r, volatilite: 0.12 + i * 0.03, sharpe: null,
  lignes: [{ symbol: "A", poids: 0.5 }, { symbol: "B", poids: 0.5 }] }));

describe("objectif", () => {
  it("prend le portefeuille le moins risqué qui atteint la cible", () => {
    const c = choisirPoint(F, 0.07)!;
    expect(c.point.rendement).toBe(0.08);
    expect(c.atteignable).toBe(true);
  });
  it("signale une cible hors d'atteinte", () => {
    const c = choisirPoint(F, 0.2)!;
    expect(c.atteignable).toBe(false);
    expect(c.point.rendement).toBe(0.12);
  });
});

describe("projection", () => {
  it("loi normale", () => {
    expect(normCdf(0)).toBeCloseTo(0.5, 6);
    expect(normCdf(1.645)).toBeCloseTo(0.95, 3);
  });
  it("le temps réduit la probabilité de perte", () => {
    const court = projection(200, 0.08, 0.18, 1 / 12, 0.08);
    const long = projection(200, 0.08, 0.18, 5, 0.08);
    expect(long.probPerte).toBeLessThan(court.probPerte);
    expect(long.bas).toBeLessThan(long.median);
    expect(long.median).toBeLessThan(long.haut);
  });
});

describe("plan d'achat", () => {
  const prix = { A: 100, B: 50 };
  it("fractions : tout le capital est investi (hors frais)", () => {
    const p = planAchat(200, F[0].lignes, prix, 1, REGLAGES_DEFAUT);
    expect(p.tranches).toHaveLength(1);
    expect(p.tranches[0].ordres[0].quantite).toBeCloseTo(0.9975, 3); // 100 € - 0,25 % change, à 100 $
    expect(p.nonInvesti).toBeLessThan(0.01);
  });
  it("actions entières : reliquat non investi et ligne trop chère signalée", () => {
    const p = planAchat(200, F[0].lignes, { A: 150, B: 50 }, 1, { ...REGLAGES_DEFAUT, fractions: false, fraisChange: 0 });
    expect(p.lignesNonAchetees).toEqual(["A"]);
    expect(p.tranches[0].ordres[1].quantite).toBe(2);
    expect(p.nonInvesti).toBeCloseTo(100);
  });
  it("achat progressif : frais multipliés par le nombre d'ordres", () => {
    const p = planAchat(200, F[0].lignes, prix, 1, { ...REGLAGES_DEFAUT, fraisOrdre: 1, tranches: 4 });
    expect(p.nbOrdres).toBe(8);
    expect(p.fraisOrdres).toBe(8);
  });
  it("calendrier : jamais un week-end", () => {
    for (const d of datesTranches(8, "semaine", new Date("2026-11-21"))) expect([0, 6]).not.toContain(d.getDay());
  });
});

import { zConfiance } from "./strategy";
describe("niveau de confiance", () => {
  it("quantiles classiques de la loi normale", () => {
    expect(zConfiance(0.9)).toBeCloseTo(1.6449, 3);
    expect(zConfiance(0.95)).toBeCloseTo(1.96, 3);
    expect(zConfiance(0.8)).toBeCloseTo(1.2816, 3);
  });
});

describe("indices en %", () => {
  it("formate corrélations, spreads et rendement / risque", async () => {
    const { corr, pb, ratioPct } = await import("./format");
    expect(corr(0.077)).toBe("7,7 %");
    expect(corr(-0.45, 0)).toBe("-45 %");
    expect(pb(305)).toBe("3,05 %");
    expect(ratioPct(0.06, 0.105)).toBe("57 %");
    expect(corr(null)).toBe("—");
  });
});
