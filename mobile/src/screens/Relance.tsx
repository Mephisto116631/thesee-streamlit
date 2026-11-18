import { useEffect, useState } from "preact/hooks";
import { api, relancerCalcul } from "../api";
import { rafraichir } from "../components";
import { ilYA } from "../format";

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
        setEtat({ phase: s.status === "success" ? "fini" : "erreur", msg: s.status === "success" ? `Terminé (${s.message ?? ""}).` : `Échec du calcul : ${s.message ?? "voir GitHub Actions"}.` });
        rafraichir();
      }
    }, 20_000);
    return () => clearInterval(t);
  }, [etat.phase]);

  const lancer = async () => {
    setEtat({ phase: "envoi" });
    const r = await relancerCalcul();
    setEtat(r.ok ? { phase: "attente", msg: r.message, depuis: Date.now() } : { phase: "erreur", msg: r.message });
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
  useEffect(() => { api.lastSync().then((r) => r.data && setTxt(`Dernier calcul ${ilYA(r.data.finished_at ?? r.data.started_at)} (${r.data.status}).`)); }, []);
  return txt ? <p class="hint">{txt} Le serveur télécharge les cours, ré-entraîne les modèles et republie tout (3 à 8 min).</p> : null;
}
