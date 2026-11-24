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
