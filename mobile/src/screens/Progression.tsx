import { useEffect, useState } from "preact/hooks";
import { api, type SyncLog } from "../api";
import { rafraichir, useChargementsEnCours } from "../components";

export const EVT_SYNC_LANCE = "thesee:sync-lance";

function minutes(ms: number) {
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? `${s} s` : `${Math.round(s / 60)} min`;
}

/**
 * Barres fines en haut de l'écran :
 *  - chargement des données (animée, sans durée) ;
 *  - calcul du serveur en cours : étape, pourcentage et temps restant estimé.
 */
export function Progression() {
  const chargements = useChargementsEnCours();
  const [sync, setSync] = useState<SyncLog | null>(null);
  const [attente, setAttente] = useState(false); // relance demandée, calcul pas encore démarré
  const [, tic] = useState(0);

  useEffect(() => {
    let vivant = true;
    let minuteur: ReturnType<typeof setTimeout>;
    const verifier = async () => {
      const r = await api.lastSync();
      if (!vivant) return;
      const s = r.data ?? null;
      setSync((avant) => {
        if (avant?.status === "running" && s && s.status !== "running") rafraichir(); // calcul terminé : on recharge
        return s;
      });
      if (s?.status === "running") setAttente(false);
      // Toutes les 10 s pendant un calcul, sinon toutes les 2 min
      minuteur = setTimeout(verifier, s?.status === "running" || attente ? 10_000 : 120_000);
    };
    verifier();
    const surLance = () => { setAttente(true); clearTimeout(minuteur); minuteur = setTimeout(verifier, 15_000); };
    window.addEventListener(EVT_SYNC_LANCE, surLance);
    const horloge = setInterval(() => tic((x) => x + 1), 1000);
    return () => { vivant = false; clearTimeout(minuteur); clearInterval(horloge); window.removeEventListener(EVT_SYNC_LANCE, surLance); };
  }, [attente]);

  const enCours = sync?.status === "running" && Date.now() - new Date(sync.started_at).getTime() < 45 * 60_000;
  const pct = enCours ? Math.max(2, sync?.progression ?? 0) : 0;
  const ecoule = enCours ? Date.now() - new Date(sync!.started_at).getTime() : 0;
  // Temps restant : extrapolé depuis l'avancement (une fois au-delà de 10 %), sinon ~3 min au total
  const restant = enCours ? (pct >= 10 ? (ecoule / pct) * (100 - pct) : 180_000 - ecoule) : 0;

  return (
    <>
      {chargements > 0 && !enCours && <div class="barre-chargement" role="progressbar" aria-label="Chargement des données" />}
      {(enCours || attente) && (
        <div class="barre-serveur" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Calcul du serveur">
          <div class="barre-serveur-piste"><div class="barre-serveur-rempli" style={{ width: `${enCours ? pct : 2}%` }} /></div>
          <span class="barre-serveur-texte">
            {enCours ? <>Calcul serveur · {sync?.etape ?? "en cours"} · {pct} % · ~{minutes(restant)}</> : "Calcul demandé, démarrage sur GitHub…"}
          </span>
        </div>
      )}
    </>
  );
}
