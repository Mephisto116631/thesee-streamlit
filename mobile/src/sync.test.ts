import { describe, expect, it } from "vitest";
import { etatDonnees, libelleStatut, passageTermine } from "./sync";

describe("statut du passage du cron", () => {
  it("« partiel » compte comme terminé, pas comme une erreur", () => {
    expect(passageTermine("success")).toBe(true);
    expect(passageTermine("partiel")).toBe(true);
    expect(passageTermine("error")).toBe(false);
    expect(passageTermine("running")).toBe(false);
  });
  it("l'accueil ne dit plus « à jour » sans réserve quand une étape a échoué", () => {
    expect(etatDonnees("success")).toBe("à jour");
    expect(etatDonnees("partiel")).toContain("avertissements");
    expect(etatDonnees("error")).toContain("erreur");
  });
  it("libellés lisibles, statut inconnu affiché tel quel", () => {
    expect(libelleStatut("partiel")).toBe("terminé avec avertissements");
    expect(libelleStatut("autre")).toBe("autre");
  });
});

import { chrono, etatRelance } from "./sync";
describe("bouton Ré-entraîner : état et minuteur", () => {
  const t0 = Date.parse("2026-11-28T10:00:00Z");
  const iso = (ms: number) => new Date(ms).toISOString();
  it("calcul en cours : temps écoulé", () => {
    expect(etatRelance({ started_at: iso(t0), status: "running" }, t0 + 135_000)).toEqual({ phase: "calcul", secondes: 135 });
  });
  it("calcul fini depuis 3 min : relance possible dans 7 min", () => {
    expect(etatRelance({ started_at: iso(t0), status: "success" }, t0 + 180_000)).toEqual({ phase: "pause", secondes: 420 });
  });
  it("libre après 10 min, ou si un « en cours » a plus de 45 min", () => {
    expect(etatRelance({ started_at: iso(t0), status: "success" }, t0 + 600_000).phase).toBe("libre");
    expect(etatRelance({ started_at: iso(t0), status: "running" }, t0 + 46 * 60_000).phase).toBe("libre");
    expect(etatRelance(null, t0).phase).toBe("libre");
  });
  it("demande envoyée, calcul pas encore démarré : temps depuis la demande", () => {
    const ancien = { started_at: iso(t0 - 3 * 3600_000), status: "success" };
    expect(etatRelance(ancien, t0 + 20_000, t0)).toEqual({ phase: "demande", secondes: 20 });
    // Le passage démarre : on bascule sur le temps de calcul
    expect(etatRelance({ started_at: iso(t0 + 30_000), status: "running" }, t0 + 50_000, t0)).toEqual({ phase: "calcul", secondes: 20 });
  });
  it("chrono", () => {
    expect(chrono(75)).toBe("1:15");
    expect(chrono(5)).toBe("0:05");
    expect(chrono(600)).toBe("10:00");
  });
});
