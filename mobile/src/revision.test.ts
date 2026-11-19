import { describe, expect, it } from "vitest";
import { choisirRevision, prochaineRevision } from "./revision";
import { choisirPointRisque } from "./strategy";

const revs = [{ date: "2026-07-01", univers_facteurs: { v: 2 } }, { date: "2026-01-02", univers_facteurs: { v: 1 } }];

describe("révision du portefeuille", () => {
  it("6 mois : la plus récente ; 12 mois : celle de janvier", () => {
    expect(choisirRevision(revs, 6)!.date).toBe("2026-07-01");
    expect(choisirRevision(revs, 12)!.date).toBe("2026-01-02");
    expect(choisirRevision([], 6)).toBeNull();
  });
  it("prochaine révision : 1er juillet ou 1er janvier", () => {
    expect(prochaineRevision(6, new Date("2026-03-10T00:00:00Z")).toISOString().slice(0, 10)).toBe("2026-07-01");
    expect(prochaineRevision(6, new Date("2026-11-19T00:00:00Z")).toISOString().slice(0, 10)).toBe("2027-01-01");
    expect(prochaineRevision(12, new Date("2026-03-10T00:00:00Z")).toISOString().slice(0, 10)).toBe("2027-01-01");
  });
  it("marge de sécurité : on vise sous la limite", () => {
    const f = [0.10, 0.13, 0.15].map((v, i) => ({ rendement: 0.05 + 0.01 * i, volatilite: v, sharpe: null, lignes: [] }));
    expect(choisirPointRisque(f, 0.15)!.point.volatilite).toBe(0.15);
    expect(choisirPointRisque(f, 0.15 * 0.87)!.point.volatilite).toBe(0.13);   // marge 0,87
  });
});
