import { useEffect, useState } from "preact/hooks";
import { api, relancerCalcul } from "../api";
import { rafraichir } from "../components";
import { ilYA } from "../format";
import { chrono, etatRelance, libelleStatut, passageTermine } from "../sync";
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

/**
 * Bouton d'en-tête « Ré-entraîner les modèles », à côté de ↻ (qui ne fait que recharger les données).
 * Minuteur dans le bouton : temps écoulé pendant le calcul, puis temps avant de pouvoir relancer (10 min).
 */
export function EntrainerButton() {
  const [dernier, setDernier] = useState<{ started_at: string; status: string } | null>(null);
  const [demandeA, setDemandeA] = useState<number | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [maintenant, setMaintenant] = useState(Date.now());

  const etat = etatRelance(dernier, maintenant, demandeA);
  const actif = etat.phase !== "libre";

  // Journal de synchro : toutes les 15 s quand quelque chose se passe, sinon toutes les 2 min
  useEffect(() => {
    let vivant = true;
    const lire = () => api.lastSync().then((r) => { if (vivant) setDernier(r.data ?? null); });
    lire();
    const t = setInterval(lire, actif ? 15_000 : 120_000);
    const surLance = () => { setDemandeA(Date.now()); lire(); };
    window.addEventListener(EVT_SYNC_LANCE, surLance);
    return () => { vivant = false; clearInterval(t); window.removeEventListener(EVT_SYNC_LANCE, surLance); };
  }, [actif]);

  // Minuteur : une seconde à la fois, seulement quand il y a quelque chose à afficher
  useEffect(() => {
    if (!actif) return;
    const t = setInterval(() => setMaintenant(Date.now()), 1000);
    return () => clearInterval(t);
  }, [actif]);

  // Fin du calcul : l'appli se recharge (la barre de progression le fait aussi ; sans effet si déjà fait)
  const [avant, setAvant] = useState(etat.phase);
  useEffect(() => {
    if (avant === "calcul" && etat.phase !== "calcul") { setDemandeA(null); rafraichir(); }
    setAvant(etat.phase);
  }, [etat.phase]);

  const lancer = async () => {
    setMaintenant(Date.now());
    if (etat.phase !== "libre" || envoi) return;
    if (!confirm("Ré-entraîner les modèles maintenant ?\nLe serveur retélécharge les cours et recalcule tout (3 à 8 min).")) return;
    setEnvoi(true);
    const r = await relancerCalcul();
    setEnvoi(false);
    if (!r.ok) { alert(r.message); return; }
    window.dispatchEvent(new CustomEvent(EVT_SYNC_LANCE));   // barre de progression et minuteur
  };

  const titre = envoi ? "Envoi de la demande…"
    : etat.phase === "calcul" ? `Ré-entraînement en cours depuis ${chrono(etat.secondes)}`
    : etat.phase === "demande" ? `Demande envoyée il y a ${chrono(etat.secondes)}, démarrage sur GitHub…`
    : etat.phase === "pause" ? `Dernier calcul tout récent : nouvelle relance possible dans ${chrono(etat.secondes)}`
    : "Ré-entraîner les modèles (3 à 8 min)";
  return (
    <button class={`help-btn entrainer ${etat.phase}`} onClick={lancer} aria-label={titre} title={titre}
      aria-disabled={etat.phase !== "libre" || envoi}>
      {envoi ? "…" : etat.phase === "libre" ? (
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
          <rect x="5" y="5" width="14" height="14" rx="2" /><rect x="9.5" y="9.5" width="5" height="5" rx="1" />
          <path d="M9 2v3M15 2v3M9 19v3M15 19v3M19 9h3M19 15h3M2 9h3M2 15h3" />
        </svg>
      ) : chrono(etat.secondes)}
    </button>
  );
}
