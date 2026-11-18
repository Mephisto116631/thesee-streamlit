// Fenêtre de mise à jour (comme Sisyphe) : proposition, téléchargement avec
// progression, puis installeur Android. Ouverte au lancement (une fois) ou
// depuis Paramètres via proposerMiseAJour().
import { useEffect, useState } from "preact/hooks";
import {
  enCache, estNatif, ignorerVersion, installerApk, mo, telecharger, telechargementAuto,
  VERSION, verifierMiseAJour, versionIgnoree, type MiseAJour,
} from "../update";

const EVT = "thesee:maj:proposer";

/** Ouvre la fenêtre pour cette mise à jour. `auLancement` : propose aussi « Ignorer cette version ». */
export function proposerMiseAJour(m: MiseAJour, auLancement = false) {
  window.dispatchEvent(new CustomEvent(EVT, { detail: { m, auLancement } }));
}

/** Vérification silencieuse : au démarrage, rien ne s'affiche si tout est à jour ou si GitHub est injoignable. */
export async function verifierAuLancement() {
  if (!estNatif()) return;
  let m: MiseAJour | null = null;
  try { m = await verifierMiseAJour(); } catch { return; }
  if (!m || m.build === versionIgnoree()) return;
  if (telechargementAuto() && !(await enCache(m))) {
    try { await telecharger(m); } catch { /* on proposera le téléchargement manuel */ }
  }
  proposerMiseAJour(m, true);
}

type Etat =
  | { e: "ferme" }
  | { e: "propose"; m: MiseAJour; auLancement: boolean; chemin: string | null }
  | { e: "telechargement"; m: MiseAJour; p: number; erreur?: string }
  | { e: "permission"; m: MiseAJour; chemin: string };

export function MiseAJourDialogue() {
  const [s, setS] = useState<Etat>({ e: "ferme" });
  const fermer = () => setS({ e: "ferme" });

  useEffect(() => {
    const on = async (ev: Event) => {
      const { m, auLancement } = (ev as CustomEvent).detail as { m: MiseAJour; auLancement: boolean };
      setS({ e: "propose", m, auLancement, chemin: await enCache(m) });
    };
    window.addEventListener(EVT, on);
    return () => window.removeEventListener(EVT, on);
  }, []);

  const installer = async (m: MiseAJour, chemin: string) => {
    try {
      if (await installerApk(chemin)) fermer();
      else setS({ e: "permission", m, chemin });
    } catch (err: any) { setS({ e: "telechargement", m, p: 0, erreur: err?.message ?? String(err) }); }
  };

  const lancer = async (m: MiseAJour) => {
    setS({ e: "telechargement", m, p: 0 });
    try {
      const chemin = await telecharger(m, (p) => setS((x) => (x.e === "telechargement" ? { ...x, p } : x)));
      await installer(m, chemin);
    } catch (err: any) {
      setS({ e: "telechargement", m, p: 0, erreur: err?.message ?? String(err) });
    }
  };

  if (s.e === "ferme") return null;
  // Un appui hors de la fenêtre = « Plus tard », jamais « Ignorer » (sauf pendant le téléchargement)
  const fond = () => { if (s.e !== "telechargement" || s.erreur) fermer(); };

  return (
    <div class="modal-fond" onClick={fond}>
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="maj-titre" onClick={(e) => e.stopPropagation()}>
        {s.e === "propose" && (
          <>
            <h2 id="maj-titre">Mise à jour disponible</h2>
            <p>Version <b>{s.m.version}</b>{s.m.taille ? ` (${mo(s.m.taille)})` : ""}.<br />Installée : {VERSION}.</p>
            {s.chemin && <p class="accent">Déjà téléchargée : prête à installer.</p>}
            <p class="hint">Tes données ne sont pas touchées : elles sont sur le serveur (et tes réglages restent sur le téléphone).</p>
            <div class="modal-actions">
              {s.auLancement && <button class="lien" onClick={() => { ignorerVersion(s.m.build); fermer(); }}>Ignorer cette version</button>}
              <button class="lien" onClick={fermer}>Plus tard</button>
              <button class="principal" onClick={() => (s.chemin ? installer(s.m, s.chemin) : lancer(s.m))}>
                {s.chemin ? "Installer" : "Télécharger et installer"}</button>
            </div>
          </>
        )}
        {s.e === "telechargement" && (
          <>
            <h2 id="maj-titre">Téléchargement {s.m.version}</h2>
            {s.erreur ? <div class="note warn">Échec du téléchargement : {s.erreur}</div> : (
              <>
                <div class="modal-piste"><div class={`modal-rempli${s.p > 0 ? "" : " indetermine"}`} style={{ width: s.p > 0 ? `${Math.round(s.p * 100)}%` : "30%" }} /></div>
                <p class="hint">{Math.round(s.p * 100)} %{s.m.taille ? ` de ${mo(s.m.taille)}` : ""}</p>
              </>
            )}
            {s.erreur && (
              <div class="modal-actions">
                <button class="lien" onClick={fermer}>Annuler</button>
                <button class="principal" onClick={() => lancer(s.m)}>Réessayer</button>
              </div>
            )}
          </>
        )}
        {s.e === "permission" && (
          <>
            <h2 id="maj-titre">Autorisation Android</h2>
            <p>Active « Autoriser depuis cette source » pour Thésée dans l'écran qui vient de s'ouvrir,
              puis reviens ici et appuie sur Installer.</p>
            <div class="modal-actions">
              <button class="lien" onClick={fermer}>Plus tard</button>
              <button class="principal" onClick={() => installer(s.m, s.chemin)}>Installer</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
