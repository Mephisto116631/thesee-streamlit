import { useEffect, useState } from "preact/hooks";
import { App as CapApp } from "@capacitor/app";
import { configured } from "./api";
import { Home } from "./screens/Home";
import { Market } from "./screens/Market";
import { Stock } from "./screens/Stock";
import { Portfolio } from "./screens/Portfolio";
import { Risk } from "./screens/Risk";
import { Calculs } from "./screens/Calculs";
import { Settings } from "./screens/Settings";
import { estNatif, installer, type MiseAJour, verifierMiseAJour } from "./update";

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
  { h: "#/marche", label: "Marché", icon: "M3 17l5-5 4 4 8-8M15 8h5v5" },
  { h: "#/portefeuille", label: "Portefeuille", icon: "M12 3v9l7 4A9 9 0 1 1 12 3zM15 3.5A9 9 0 0 1 20.5 9H15z" },
  { h: "#/risque", label: "Risque & IA", icon: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" },
  { h: "#/parametres", label: "Réglages", icon: "M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1M15 4v4M9 10v4M17 16v4" },
];

export function App() {
  const hash = useHash();
  const [maj, setMaj] = useState<MiseAJour | null>(null);

  // Mise à jour automatique : vérification au démarrage et au retour dans l'appli
  // (au plus toutes les 6 h), uniquement dans l'APK.
  useEffect(() => {
    if (!estNatif()) return;
    const verifier = () => verifierMiseAJour().then((m) => m && setMaj(m)).catch(() => {});
    verifier();
    const sub = CapApp.addListener("resume", verifier).catch(() => null);
    return () => { sub.then((x) => x?.remove()); };
  }, []);

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
    case "risque": screen = <Risk tab={arg === "ia" ? "ia" : "credit"} go={go} />; break;
    case "parametres": screen = arg === "calculs" ? <Calculs /> : <Settings />; break;
    default: screen = <Home go={go} />;
  }
  const active = route === "titre" ? "#/marche" : `#/${route ?? ""}`;

  return (
    <div class="app">
      {!configured && <div class="note warn top">Build sans configuration Supabase : définir VITE_SUPABASE_URL et VITE_SUPABASE_ANON_KEY.</div>}
      {maj && (
        <div class="banniere-maj" role="status">
          <span>Nouvelle version <b>{maj.version}</b> disponible</span>
          <button onClick={() => installer(maj)}>Installer</button>
          <button class="fermer" aria-label="Plus tard" onClick={() => setMaj(null)}>✕</button>
        </div>
      )}
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
