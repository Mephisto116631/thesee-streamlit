import { describe, expect, it } from "vitest";
import { lireFiabilite, prochainReTest, univers } from "./fiabilite";
import { avecVolIA, type Univers } from "./optim";
import { coursVC, enPerte, per } from "./valorisation";

const U: Univers = {
  symbols: ["A", "B"], mu_hist: [0.1, 0.1], beta: [1, 1], jours: 750,
  cov: [[0.04, 0.01], [0.01, 0.09]], vol_ia: [0.1, 0.5],
};
const labo = (verdict: string) => ({ verdict, t_stat: 6.5, seuil_t_global: 2.7, cree_le: "2026-11-18T23:33:36Z",
  ic: 0.76, ic_base: 0.72, gain: 0.045, part: 0.91 });

describe("fiabilité de la volatilité IA", () => {
  it("probant seulement si le dernier test l'est", () => {
    expect(lireFiabilite(labo("probant"), null).probant).toBe(true);
    expect(lireFiabilite(labo("non probant"), null).probant).toBe(false);
    const f = lireFiabilite(null, null);
    expect(f.probant).toBe(false);
    expect(f.connu).toBe(false);
  });

  it("retire la prévision de l'univers quand elle n'est pas prouvée", () => {
    const sans = univers(U, { probant: false })!;
    expect(sans.vol_ia).toBeUndefined();
    // le portefeuille revient alors à la volatilité historique
    expect(avecVolIA(sans).cov!).toEqual(U.cov);
    expect(univers(U, { probant: true })!.vol_ia).toEqual([0.1, 0.5]);
    expect(avecVolIA(univers(U, { probant: true })!).cov![1][1]).toBeCloseTo(0.25);
  });

  it("bilan réel lu depuis model_runs, prochain re-test le 2 du mois", () => {
    const run = { kind: "risque_volatilite_reel", diagnostics: { reel: { n_dates: 0, premier_bilan: "2027-05-19" } } } as any;
    expect(lireFiabilite(labo("probant"), run).reel?.premier_bilan).toBe("2027-05-19");
    expect(prochainReTest(new Date("2026-11-19T10:00:00Z")).toISOString().slice(0, 10)).toBe("2026-12-02");
    expect(prochainReTest(new Date("2026-12-01T10:00:00Z")).toISOString().slice(0, 10)).toBe("2026-12-02");
  });
});

describe("valorisation SEC", () => {
  it("PER et cours / valeur comptable au cours du jour", () => {
    expect(per({ close: 60, bpa_sec: 4 })).toBe(15);
    expect(per({ close: 60, bpa_sec: -2 })).toBeNull();
    expect(enPerte({ bpa_sec: -2 })).toBe(true);
    expect(per({ close: 60, bpa_sec: null })).toBeNull();
    expect(coursVC({ close: 60, vc_action_sec: 20 })).toBe(3);
  });
});
