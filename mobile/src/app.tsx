import { useEffect, useState } from "preact/hooks";
import { App as CapApp } from "@capacitor/app";
import { configured, ecouterRetourGoogle } from "./api";
import { reprogrammerAuLancement } from "./rappels";
import { lireParametres } from "./settings";
import { Home } from "./screens/Home";
import { Market } from "./screens/Market";
import { Stock } from "./screens/Stock";
import { Portfolio } from "./screens/Portfolio";
import { Risk } from "./screens/Risk";
import { Calculs } from "./screens/Calculs";
import { Analyse } from "./screens/Analyse";
import { Glossaire } from "./screens/Glossaire";
import { Guide } from "./screens/Guide";
import { PositionsEcran } from "./screens/EcransSecondaires";
import { Progression } from "./screens/Progression";
import { Settings } from "./screens/Settings";
import { MiseAJourDialogue, verifierAuLancement } from "./screens/MiseAJourDialogue";

// Routage par hash (#/marche, #/titre/AAPL...) : marche à l'identique dans
// l'APK, sur GitHub Pages et en local, sans configuration serveur.
const useHash = () => {
  const [h, setH] = useState(location.hash || "#/");
  useEffect(() => {
    const on = () => { setH(location.hash || "#/"); window.scrollTo(0, 0); };
    addEventListener("hashchange", on);
    return () => removeEventListener("hashchange", on);
  }, []);
  return h;
};

const go = (h: string) => { location.hash = h; };

const TABS = [
  { h: "#/", label: "Accueil", icon: "M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" },
  { h: "#/portefeuille", label: "Portefeuille", icon: "M12 3v9l7 4A9 9 0 1 1 12 3zM15 3.5A9 9 0 0 1 20.5 9H15z" },
  { h: "#/analyse", label: "Analyse", icon: "M3 17l5-5 4 4 8-8M15 8h5v5" },
  { h: "#/positions", label: "Positions", icon: "M4 7h16v12H4zM9 7V5h6v2M4 12h16" },
];

export function App() {
  const hash = useHash();
  // Mise à jour (APK uniquement) : vérifiée une fois par lancement, proposée dans une fenêtre
  useEffect(() => { verifierAuLancement(); reprogrammerAuLancement(lireParametres().rythmeRevision ?? 6); }, []);
  // Connexion Google dans l'APK : retour par com.thesee.app://login-callback
  useEffect(() => { ecouterRetourGoogle((m) => alert(`Connexion Google impossible : ${m}`)); }, []);

  // Bouton retour Android : remonte l'historique, quitte l'appli depuis l'accueil
  useEffect(() => {
    const sub = CapApp.addListener("backButton", () => {
      if ((location.hash || "#/") === "#/") CapApp.exitApp(); else history.back();
    }).catch(() => null);
    return () => { sub.then((s) => s?.remove()); };
  }, []);

  const [, route, arg] = hash.match(/^#\/([^/]*)\/?(.*)$/) ?? [];
  let screen;
  switch (route) {
    case "marche": screen = <Market go={go} />; break;
    case "titre": screen = <Stock symbol={decodeURIComponent(arg)} go={go} />; break;
    case "portefeuille": screen = <Portfolio />; break;
    case "positions": screen = <PositionsEcran />; break;
    case "analyse": screen = <Analyse />; break;
    case "risque": screen = <Risk tab={arg === "ia" ? "ia" : "credit"} go={go} />; break;
    case "glossaire": screen = <Glossaire />; break;
    case "guide": screen = <Guide />; break;
    case "parametres": screen = arg.startsWith("calculs") ? <Calculs section={arg.split("/")[1]} /> : <Settings />; break;
    default: screen = <Home go={go} />;
  }
  // Onglet actif : les écrans d'analyse (marché, risque, réglages…) sont rangés sous « Analyse »
  const ANALYSE = ["marche", "titre", "risque", "parametres", "analyse", "glossaire", "guide"];
  const active = ANALYSE.includes(route ?? "") ? "#/analyse" : `#/${route ?? ""}`;

  return (
    <div class="app">
      {!configured && <div class="note warn top">Build sans configuration Supabase : définir VITE_SUPABASE_URL et VITE_SUPABASE_ANON_KEY.</div>}
      <Progression />
      <MiseAJourDialogue />
      <main>{screen}</main>
      <nav class="tabbar" aria-label="Navigation principale">
        {TABS.map((t) => {
          const on = t.h === "#/" ? active === "#/" : active.startsWith(t.h);
          return (
            <a href={t.h} class={on ? "on" : ""} aria-current={on ? "page" : undefined}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d={t.icon} /></svg>
              <span>{t.label}</span>
            </a>
          );
        })}
      </nav>
    </div>
  );
}
