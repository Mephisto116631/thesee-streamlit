// Mise à jour automatique de l'APK : l'appli compare son numéro de build à la
// dernière Release GitHub (« apk-<n> ») et propose d'installer la nouvelle version.
// Android impose une confirmation d'installation (pas d'installation silencieuse
// hors Play Store) ; tout le reste est automatique.
import { Capacitor } from "@capacitor/core";
import { Browser } from "@capacitor/browser";

export const DEPOT = "Mephisto116631/thesee-streamlit";
/** Numéro de build injecté par le workflow (github.run_number) ; "dev" en local. */
export const BUILD = (import.meta.env.VITE_APP_BUILD as string | undefined) ?? "dev";
export const VERSION = BUILD === "dev" ? "dev" : `1.${BUILD}`;
export const estNatif = () => Capacitor.isNativePlatform();

export interface MiseAJour { version: string; build: number; url: string; date: string; notes: string }

const CLE_DERNIERE = "thesee:maj:derniere-verif";
const INTERVALLE_MS = 6 * 3600 * 1000;

/** Interroge GitHub. Retourne la mise à jour si elle est plus récente que la version installée. */
export async function verifierMiseAJour(forcer = false): Promise<MiseAJour | null> {
  if (!forcer) {
    try {
      const der = Number(localStorage.getItem(CLE_DERNIERE) ?? 0);
      if (Date.now() - der < INTERVALLE_MS) return null;
    } catch { /* ignore */ }
  }
  const r = await fetch(`https://api.github.com/repos/${DEPOT}/releases/latest`, { headers: { Accept: "application/vnd.github+json" } });
  if (!r.ok) throw new Error(`GitHub ${r.status}`);
  const rel = await r.json();
  try { localStorage.setItem(CLE_DERNIERE, String(Date.now())); } catch { /* ignore */ }
  const build = Number(String(rel.tag_name ?? "").replace(/^apk-/, ""));
  const asset = (rel.assets ?? []).find((a: any) => String(a.name).endsWith(".apk"));
  if (!build || !asset) return null;
  const courant = Number(BUILD);
  if (Number.isFinite(courant) && build <= courant) return null;
  return { version: `1.${build}`, build, url: asset.browser_download_url, date: rel.published_at, notes: rel.body ?? "" };
}

/** Ouvre le téléchargement de l'APK dans le navigateur du téléphone (qui lance l'installation). */
export async function installer(m: MiseAJour) {
  if (estNatif()) await Browser.open({ url: m.url });
  else window.open(m.url, "_blank");
}
