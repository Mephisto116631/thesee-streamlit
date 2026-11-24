import { useEffect, useState } from "preact/hooks";
import { api, relancerCalcul } from "../api";
import { rafraichir } from "../components";
import { ilYA } from "../format";
import { libelleStatut, passageTermine } from "../sync";
import { EVT_SYNC_LANCE } from "./Progression";

/** Bouton « Relancer le calcul » : synchro + ré-entraînement des modèles côté serveur. */
export function Relance() {
  const [etat, setEtat] = useState<{ phase: "idle" | "envoi" | "attente" | "fini" | "erreur"; msg?: string; depuis?: number }>({ phase: "idle" });

  // Suit l'avancement dans le journal de synchro et rafraîchit l'appli à la fin
  useEffect(() => {
    if (etat.phase !== "attente") return;
    const t = setInterval(async () => {
      const r = await api.lastSync();
      const s = r.data;
      if (s && new Date(s.started_at).getTime() >= (etat.depuis ?? 0) - 120_000 && s.status !== "running") {
        clearInterval(t);
        const ok = passageTermine(s.status);
        setEtat({ phase: ok ? "fini" : "erreur",
          msg: ok ? `${s.status === "partiel" ? "Terminé avec avertissements" : "Terminé"} (${s.message ?? ""}).`
            : `Échec du calcul : ${s.message ?? "voir GitHub Actions"}.` });
        rafraichir();
      }
    }, 20_000);
    return () => clearInterval(t);
  }, [etat.phase]);

  const lancer = async () => {
    setEtat({ phase: "envoi" });
    const r = await relancerCalcul();
    setEtat(r.ok ? { phase: "attente", msg: r.message, depuis: Date.now() } : { phase: "erreur", msg: r.message });
    if (r.ok) window.dispatchEvent(new CustomEvent(EVT_SYNC_LANCE)); // la barre de progression prend le relais
  };

  return (
    <div class="relance">
      <button class="more" onClick={lancer} disabled={etat.phase === "envoi" || etat.phase === "attente"}>
        {etat.phase === "envoi" ? "Envoi…" : etat.phase === "attente" ? "Calcul en cours…" : "↻ Relancer le calcul et l'entraînement"}
      </button>
      {etat.msg && <p class={`hint ${etat.phase === "erreur" ? "down" : ""}`}>{etat.msg}</p>}
      {etat.phase === "idle" && <DernierCalcul />}
    </div>
  );
}

function DernierCalcul() {
  const [txt, setTxt] = useState("");
  useEffect(() => {
    api.lastSync().then((r) => {
      const s = r.data;
      if (!s) return;
      // Passage partiel : on dit ce qui a échoué (le message liste les étapes non publiées)
      const detail = s.status === "partiel" && s.message ? ` ${s.message}.` : "";
      setTxt(`Dernier calcul ${ilYA(s.finished_at ?? s.started_at)} (${libelleStatut(s.status)}).${detail}`);
    });
  }, []);
  return txt ? <p class="hint">{txt} Le serveur télécharge les cours, ré-entraîne les modèles et republie tout (3 à 8 min).</p> : null;
}
