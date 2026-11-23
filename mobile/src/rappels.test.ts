import { describe, expect, it, vi } from "vitest";
vi.mock("@capacitor/core", () => ({ Capacitor: { isNativePlatform: () => false } }));
vi.mock("@capacitor/local-notifications", () => ({ LocalNotifications: {} }));
import { lignesAuDessusDuSeuil, programmerRappels, rappelsAVenir } from "./rappels";

describe("rappels de révision", () => {
  it("6 mois : 1er juillet à 9 h et 3 jours avant", () => {
    const r = rappelsAVenir(6, new Date(2027, 2, 10));
    expect(r.map((x) => [x.at.getMonth(), x.at.getDate(), x.at.getHours()])).toEqual([[5, 28, 9], [6, 1, 9]]);
  });
  it("12 mois : 1er janvier suivant", () => {
    const r = rappelsAVenir(12, new Date(2027, 2, 10));
    expect(r[1].at.getFullYear()).toBe(2028);
    expect([r[1].at.getMonth(), r[1].at.getDate()]).toEqual([0, 1]);
    expect([r[0].at.getMonth(), r[0].at.getDate()]).toEqual([11, 29]);
  });
  it("jamais de date passée : la veille déjà passée n'est pas programmée", () => {
    const r = rappelsAVenir(6, new Date(2027, 5, 30, 12));
    expect(r.length).toBe(1);
    expect(r[0].at.getDate()).toBe(1);
  });
  it("hors APK : indisponible, rien n'est programmé", async () => {
    expect(await programmerRappels(true, 6)).toBe("indisponibles");
  });
  it("seuil de rééquilibrage", () => {
    expect(lignesAuDessusDuSeuil({ A: 30, B: 50, C: 20 }, 0.25)).toEqual(["A", "B"]);
    expect(lignesAuDessusDuSeuil({}, 0.25)).toEqual([]);
  });
});
