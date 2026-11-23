// Rappels de révision (APK seulement) : notifications locales programmées sur le téléphone, sans serveur.
// 3 jours avant et le jour de la révision du portefeuille (1er janvier et 1er juillet, ou 1er janvier seulement), à 9 h.
// Reprogrammés à chaque ouverture de l'appli et à chaque changement de réglage.
import { Capacitor } from "@capacitor/core";
import { LocalNotifications } from "@capacitor/local-notifications";
import { prochaineRevision } from "./revision";

const KEY = "thesee:rappels:v1";
export const IDS = { veille: 7101, jour: 7102 };
export const JOURS_AVANT = 3;

export const rappelsDisponibles = () => Capacitor.isNativePlatform();
export function lireRappels(): boolean {
  try { return localStorage.getItem(KEY) === "1"; } catch { return false; }
}
function ecrireRappels(v: boolean) {
  try { localStorage.setItem(KEY, v ? "1" : "0"); } catch { /* ignore */ }
}

export interface Rappel { id: number; at: Date; title: string; body: string }

/** Rappels à venir pour le rythme choisi (jamais une date passée). Heure locale du téléphone. */
export function rappelsAVenir(rythme: 6 | 12, maintenant = new Date()): Rappel[] {
  const r = prochaineRevision(rythme, maintenant);
  const jour = new Date(r.getUTCFullYear(), r.getUTCMonth(), r.getUTCDate(), 9, 0, 0);
  const veille = new Date(jour.getTime() - JOURS_AVANT * 864e5);
  const quand = jour.toLocaleDateString("fr-FR", { day: "numeric", month: "long" });
  return [
    { id: IDS.veille, at: veille, title: "Révision du portefeuille dans 3 jours",
      body: `Le ${quand}, Thésée propose le portefeuille révisé. Rien à faire d'ici là.` },
    { id: IDS.jour, at: jour, title: "C'est le jour de la révision",
      body: "Ouvre Thésée › Positions : les ordres de la révision sont prêts à vérifier." },
  ].filter((x) => x.at > maintenant);
}

/** Active / désactive et (re)programme. Retourne l'état réel. */
export async function programmerRappels(actif: boolean, rythme: 6 | 12): Promise<"actifs" | "desactives" | "refuses" | "indisponibles"> {
  if (!rappelsDisponibles()) return "indisponibles";
  await LocalNotifications.cancel({ notifications: [{ id: IDS.veille }, { id: IDS.jour }] }).catch(() => null);
  if (!actif) { ecrireRappels(false); return "desactives"; }
  let perm = await LocalNotifications.checkPermissions();
  if (perm.display !== "granted") perm = await LocalNotifications.requestPermissions();
  if (perm.display !== "granted") { ecrireRappels(false); return "refuses"; }
  const rs = rappelsAVenir(rythme);
  if (rs.length) await LocalNotifications.schedule({ notifications: rs.map((x) => ({ ...x, schedule: { at: x.at, allowWhileIdle: true } })) });
  ecrireRappels(true);
  return "actifs";
}

/** À l'ouverture de l'appli : reprogramme si les rappels sont actifs (la date suivante a pu changer). */
export function reprogrammerAuLancement(rythme: 6 | 12) {
  if (rappelsDisponibles() && lireRappels()) programmerRappels(true, rythme).catch(() => null);
}

/** Lignes du portefeuille qui dépassent le seuil de rééquilibrage (vérifié à l'ouverture, pas de tâche de fond). */
export function lignesAuDessusDuSeuil(poids: Record<string, number>, seuil: number): string[] {
  const total = Object.values(poids).reduce((a, b) => a + b, 0);
  if (total <= 0) return [];
  return Object.entries(poids).filter(([, v]) => v / total > seuil).map(([s]) => s);
}
