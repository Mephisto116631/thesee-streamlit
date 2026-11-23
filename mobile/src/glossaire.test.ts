import { readdirSync, readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { chercher, entrees, existe, GLOSSAIRE } from "./glossaire";

describe("glossaire", () => {
  it("chaque clé d'un bouton d'aide existe (plus de bouton d'aide vide)", () => {
    const dir = new URL("./screens/", import.meta.url);
    const cles: string[] = [];
    for (const f of readdirSync(dir)) {
      const src = readFileSync(new URL(f, dir), "utf8");
      for (const m of src.matchAll(/keys=\{([^}]*)\}/g))
        for (const l of m[1].matchAll(/\[([^\]]*)\]/g)) for (const k of l[1].matchAll(/"([a-z0-9_]+)"/g)) cles.push(k[1]);
    }
    expect(cles.length).toBeGreaterThan(10);
    expect(cles.filter((k) => !existe(k))).toEqual([]);
  });
  it("chaque fiche est complète", () => {
    for (const [k, f] of Object.entries(GLOSSAIRE)) {
      expect([k, f.titre && f.def && f.lecture && f.limites && f.categorie]).toEqual([k, expect.any(String)]);
    }
  });
  it("recherche sans accents, liste triée", () => {
    expect(chercher("beta").some((e) => e.cle === "beta")).toBe(true);
    expect(chercher("révision").some((e) => e.cle === "revision")).toBe(true);
    expect(entrees().some((e) => e.cle === "gain_pts")).toBe(false);          // indicateur retiré
    const t = entrees().map((e) => e.titre);
    expect([...t].sort((a, b) => a.localeCompare(b, "fr"))).toEqual(t);
  });
});
