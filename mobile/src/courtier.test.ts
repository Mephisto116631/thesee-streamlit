import { describe, expect, it } from "vitest";
import { limiteDevise, texteOrdre } from "./courtier";

const o = { symbol: "AMZN", montantEur: 40, montantUsd: 43.2, prix: 170, quantite: 0.2541, limite: 170.51, investiEur: 40 };

describe("ordres Trade Republic", () => {
  it("convertit le prix limite en euros", () => {
    expect(limiteDevise(o, "EUR", 1.1)).toBeCloseTo(155.01, 2);
    expect(limiteDevise(o, "USD", 1.1)).toBe(170.51);
  });
  it("texte prêt à recopier", () => {
    expect(texteOrdre(o, "Amazon", "EUR", 1.1, true)).toBe("Acheter 0,2541 AMZN (Amazon) — limite 155,01 € — ≈ 40,00 €");
  });
});
