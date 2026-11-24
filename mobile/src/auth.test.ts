import { describe, expect, it } from "vitest";
import { adresseRetourWeb, analyserRetour, RETOUR_GOOGLE } from "./auth";

describe("connexion Google : lien de retour", () => {
  it("lit le code renvoyé à l'APK", () => {
    expect(analyserRetour(`${RETOUR_GOOGLE}?code=abc-123`)).toEqual({ code: "abc-123" });
    expect(analyserRetour(`${RETOUR_GOOGLE}/?code=xyz`)).toEqual({ code: "xyz" });
  });
  it("remonte l'erreur (refus, fournisseur non activé…)", () => {
    expect(analyserRetour(`${RETOUR_GOOGLE}?error=access_denied&error_description=Refus%C3%A9`)).toEqual({ erreur: "Refusé" });
    expect(analyserRetour(`${RETOUR_GOOGLE}#error=server_error`)).toEqual({ erreur: "server_error" });
    expect(analyserRetour(RETOUR_GOOGLE)).toEqual({ erreur: "Retour de Google sans code de connexion." });
  });
  it("ignore les autres liens", () => {
    expect(analyserRetour("https://exemple.fr/?code=1")).toBeNull();
  });
  it("PWA : revient sur la page, sans le routage par #", () => {
    expect(adresseRetourWeb({ origin: "https://x.github.io", pathname: "/thesee-streamlit/" })).toBe("https://x.github.io/thesee-streamlit/");
  });
});
