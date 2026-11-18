import { describe, expect, it } from "vitest";
import { lireRelease, mo, nomFichier, plusRecente } from "./update";

const rel = {
  tag_name: "apk-21", published_at: "2026-11-18T12:00:00Z", body: "APK",
  assets: [{ name: "thesee.apk", browser_download_url: "https://exemple/thesee.apk", size: 9_437_184 }],
};

describe("mise à jour", () => {
  it("lit la Release GitHub (build, URL, taille)", () => {
    const m = lireRelease(rel)!;
    expect(m.build).toBe(21);
    expect(m.version).toBe("1.21");
    expect(m.taille).toBe(9_437_184);
    expect(nomFichier(m)).toBe("thesee-21.apk");
    expect(mo(m.taille)).toBe("9 Mo");
  });
  it("ignore une Release sans APK ou sans numéro", () => {
    expect(lireRelease({ ...rel, assets: [] })).toBeNull();
    expect(lireRelease({ ...rel, tag_name: "v1" })).toBeNull();
  });
  it("ne propose qu'une version plus récente, jamais en build de développement", () => {
    const m = lireRelease(rel)!;
    expect(plusRecente(m, "20")).toBe(true);
    expect(plusRecente(m, "21")).toBe(false);
    expect(plusRecente(m, "dev")).toBe(false);
  });
});
