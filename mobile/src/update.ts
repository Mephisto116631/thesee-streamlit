// Mise à jour intégrée de l'APK (même fonctionnement que Sisyphe) :
//  - au lancement, l'appli compare son numéro de build à la dernière Release
//    GitHub (« apk-<n> ») et propose la nouvelle version dans une fenêtre
//    (Ignorer cette version / Plus tard / Télécharger et installer) ;
//  - l'APK est téléchargé DANS l'appli (barre de progression), puis l'installeur
//    Android s'ouvre directement (plugin natif MiseAJour, mobile/native/) ;
//  - option « télécharger automatiquement » : l'APK est prêt avant même la fenêtre ;
//  - les anciens APK du cache sont supprimés à chaque vérification.
// Android impose une confirmation d'installation (pas d'installation silencieuse hors Play Store).
import { Capacitor, registerPlugin, type PluginListenerHandle } from "@capacitor/core";

export const DEPOT = "Mephisto116631/thesee-streamlit";
/** Numéro de build injecté par le workflow (github.run_number) ; "dev" en local. */
export const BUILD = (import.meta.env.VITE_APP_BUILD as string | undefined) ?? "dev";
export const VERSION = BUILD === "dev" ? "dev" : `1.${BUILD}`;
export const estNatif = () => Capacitor.isNativePlatform();

export interface MiseAJour { version: string; build: number; url: string; date: string; notes: string; taille: number }

interface PluginMiseAJour {
  enCache(o: { nom: string; taille: number }): Promise<{ chemin: string | null }>;
  telecharger(o: { url: string; nom: string; taille: number }): Promise<{ chemin: string }>;
  installer(o: { chemin: string }): Promise<{ etat: "started" | "needs_permission" }>;
  tailleCache(): Promise<{ octets: number }>;
  nettoyer(o: { garder?: string }): Promise<{ liberes: number }>;
  addListener(evt: "progression", f: (d: { p: number }) => void): Promise<PluginListenerHandle>;
}
const Natif = registerPlugin<PluginMiseAJour>("MiseAJour");

const CLE_AUTO = "thesee:maj:auto";
const CLE_IGNOREE = "thesee:maj:ignoree";
const lire = (k: string) => { try { return localStorage.getItem(k); } catch { return null; } };
const ecrire = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* ignore */ } };

export const telechargementAuto = () => lire(CLE_AUTO) === "1";
export const definirTelechargementAuto = (v: boolean) => ecrire(CLE_AUTO, v ? "1" : "0");
export const versionIgnoree = () => Number(lire(CLE_IGNOREE) ?? 0);
export const ignorerVersion = (build: number) => ecrire(CLE_IGNOREE, String(build));

export const nomFichier = (m: MiseAJour) => `thesee-${m.build}.apk`;
export const mo = (octets: number) => `${Math.max(1, Math.round(octets / 1048576))} Mo`;

/** Lit la réponse GitHub « dernière Release » ; null si pas d'APK ou pas de numéro de build. */
export function lireRelease(rel: any): MiseAJour | null {
  const build = Number(String(rel?.tag_name ?? "").replace(/^apk-/, ""));
  const asset = (rel?.assets ?? []).find((a: any) => String(a.name).endsWith(".apk"));
  if (!build || !asset) return null;
  return { version: `1.${build}`, build, url: asset.browser_download_url, date: rel.published_at,
    notes: rel.body ?? "", taille: Number(asset.size ?? 0) };
}

/** Plus récente que la version installée ? (build local « dev » : jamais) */
export const plusRecente = (m: MiseAJour, courant = BUILD) => {
  const c = Number(courant);
  return Number.isFinite(c) && m.build > c;
};

/** Dernière Release si elle est plus récente que l'appli, sinon null. Nettoie les vieux APK au passage. */
export async function verifierMiseAJour(): Promise<MiseAJour | null> {
  const r = await fetch(`https://api.github.com/repos/${DEPOT}/releases/latest`, { headers: { Accept: "application/vnd.github+json" } });
  if (!r.ok) throw new Error(`GitHub a répondu ${r.status}`);
  const m = lireRelease(await r.json());
  const dispo = m && plusRecente(m) ? m : null;
  if (estNatif()) await Natif.nettoyer({ garder: dispo ? nomFichier(dispo) : undefined }).catch(() => {});
  return dispo;
}

/** Chemin de l'APK s'il est déjà entièrement téléchargé. */
export async function enCache(m: MiseAJour): Promise<string | null> {
  if (!estNatif()) return null;
  try { return (await Natif.enCache({ nom: nomFichier(m), taille: m.taille })).chemin; } catch { return null; }
}

/** Télécharge l'APK dans le cache de l'appli ; `progres` reçoit 0..1. */
export async function telecharger(m: MiseAJour, progres?: (p: number) => void): Promise<string> {
  const h = progres ? await Natif.addListener("progression", (d) => progres(d.p)) : null;
  try { return (await Natif.telecharger({ url: m.url, nom: nomFichier(m), taille: m.taille })).chemin; }
  finally { await h?.remove(); }
}

/** Ouvre l'installeur Android. false : Android a d'abord ouvert « Installer des applis inconnues ». */
export async function installerApk(chemin: string): Promise<boolean> {
  return (await Natif.installer({ chemin })).etat === "started";
}

export async function tailleCache(): Promise<number> {
  if (!estNatif()) return 0;
  try { return (await Natif.tailleCache()).octets; } catch { return 0; }
}
export async function viderCache(): Promise<number> {
  if (!estNatif()) return 0;
  try { return (await Natif.nettoyer({})).liberes; } catch { return 0; }
}
