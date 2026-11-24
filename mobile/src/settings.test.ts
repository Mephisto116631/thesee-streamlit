import { beforeEach, describe, expect, it, vi } from "vitest";

// Environnement de test sans navigateur : localStorage et événements simulés
const stock = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => stock.get(k) ?? null,
  setItem: (k: string, v: string) => { stock.set(k, v); },
  removeItem: (k: string) => { stock.delete(k); },
});
vi.stubGlobal("window", { dispatchEvent: () => true, addEventListener: () => {}, removeEventListener: () => {} });
vi.stubGlobal("CustomEvent", class { constructor(public type: string) {} });

const S = await import("./settings");

describe("taux sans risque du marché (docs/METHODE.md § 2.1)", () => {
  beforeEach(() => stock.clear());

  it("sans taux publié : valeur par défaut 4,35 %", () => {
    expect(S.lireParametres().tauxSansRisque).toBe(0.0435);
  });

  it("suit le taux publié par défaut, sans compter comme une modification", () => {
    S.definirTauxMarche(0.0372, "2026-11-21");
    const p = S.lireParametres();
    expect(p.tauxSansRisque).toBe(0.0372);
    expect(S.nbModifies(p)).toBe(0);
  });

  it("une saisie fige le taux et compte comme une modification", () => {
    S.definirTauxMarche(0.0372, "2026-11-21");
    S.ecrireParametres({ tauxSansRisque: 0.03 });
    const p = S.lireParametres();
    expect(p.tauxSansRisqueAuto).toBe(false);
    expect(p.tauxSansRisque).toBe(0.03);
    expect(S.nbModifies(p)).toBe(2);              // valeur fixe + taux différent du défaut
    S.definirTauxMarche(0.05, "2026-12-01");      // le marché bouge : la valeur fixe reste
    expect(S.lireParametres().tauxSansRisque).toBe(0.03);
  });

  it("revenir au marché, et réinitialiser, le refont suivre", () => {
    S.definirTauxMarche(0.0372, "2026-11-21");
    S.ecrireParametres({ tauxSansRisque: 0.03 });
    S.ecrireParametres({ tauxSansRisqueAuto: true });
    expect(S.lireParametres().tauxSansRisque).toBe(0.0372);
    S.ecrireParametres({ tauxSansRisque: 0.02 });
    S.ecrireParametres(null);
    expect(S.lireParametres().tauxSansRisque).toBe(0.0372);
  });

  it("ignore un taux absent ou invraisemblable", () => {
    S.definirTauxMarche(null, null);
    S.definirTauxMarche(0.5, "2026-11-21");
    expect(S.lireTauxMarche()).toBeNull();
    expect(S.avecTauxMarche(S.PARAMETRES_DEFAUT, null).tauxSansRisque).toBe(0.0435);
  });
});
