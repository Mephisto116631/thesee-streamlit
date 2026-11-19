import { useEffect, useRef, useState } from "preact/hooks";
import type { ComponentChildren } from "preact";
import {
  Chart, LineController, LineElement, PointElement, LinearScale, CategoryScale,
  Filler, Tooltip, BarController, BarElement, Legend,
} from "chart.js";
import { RANGES, bornesTexte, fmt, zoneIndex, zoneOf } from "./ranges";
import type { Result } from "./api";
import { ilYA } from "./format";

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip, BarController, BarElement, Legend);

// ---------------------------------------------------------------------------
// Chargement asynchrone avec cache (affiche d'abord le cache, puis le réseau)
// ---------------------------------------------------------------------------
// Bouton « rafraîchir » : un événement global relance toutes les requêtes affichées.
const EVT_REFRESH = "thesee:refresh";
export const rafraichir = () => window.dispatchEvent(new CustomEvent(EVT_REFRESH));

// Compteur global des chargements en cours (barre fine en haut de l'écran)
let chargements = 0;
const EVT_CHARGEMENT = "thesee:chargement";
function signalerChargement(delta: number) {
  chargements = Math.max(0, chargements + delta);
  window.dispatchEvent(new CustomEvent(EVT_CHARGEMENT, { detail: chargements }));
}
export function useChargementsEnCours(): number {
  const [n, setN] = useState(chargements);
  useEffect(() => {
    const on = (e: Event) => setN((e as CustomEvent).detail);
    window.addEventListener(EVT_CHARGEMENT, on);
    return () => window.removeEventListener(EVT_CHARGEMENT, on);
  }, []);
  return n;
}

export function useData<T>(loader: () => Promise<Result<T>>, deps: unknown[] = []) {
  const [res, setRes] = useState<Result<T> | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const on = () => setTick((t) => t + 1);
    window.addEventListener(EVT_REFRESH, on);
    return () => window.removeEventListener(EVT_REFRESH, on);
  }, []);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    signalerChargement(+1);
    loader().then((r) => { if (alive) { setRes(r); setLoading(false); } })
      .finally(() => signalerChargement(-1));
    return () => { alive = false; };
  }, [...deps, tick]);
  return { data: res?.data, res, loading };
}

/** Bouton d'en-tête : recharge toutes les données de l'écran depuis Supabase. */
export function RefreshButton() {
  const [tourne, setTourne] = useState(false);
  return (
    <button class={`help-btn refresh ${tourne ? "spin" : ""}`} aria-label="Rafraîchir les données"
      onClick={() => { setTourne(true); rafraichir(); setTimeout(() => setTourne(false), 900); }}>↻</button>
  );
}

/** Bouton d'en-tête : ouvre les Paramètres (hypothèses, frais, risque…). */
export function ReglagesButton() {
  return <a class="help-btn reglages" href="#/parametres" aria-label="Paramètres">⚙</a>;
}

export function Loading({ label = "Chargement…" }: { label?: string }) {
  return <div class="loading" role="status"><span class="spinner" />{label}</div>;
}

export function OfflineNote({ res }: { res?: Result<unknown> | null }) {
  if (!res?.error) return null;
  return (
    <div class="note warn">
      {res.cachedAt ? `Hors ligne — données en cache (${ilYA(new Date(res.cachedAt).toISOString())}).` : "Données indisponibles."}
      <small>{res.error}</small>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pastille de zone : "Suracheté", "Sain", ...
// ---------------------------------------------------------------------------
export function ZoneBadge({ k, v, short = false }: { k: string; v: number | null | undefined; short?: boolean }) {
  const z = zoneOf(k, v);
  if (!z) return <span class="badge none">n.d.</span>;
  return <span class={`badge ${z.ton}`} title={z.aide}>{short ? fmt(k, v) : z.nom}</span>;
}

export function Dot({ k, v }: { k: string; v: number | null | undefined }) {
  const z = zoneOf(k, v);
  return <span class={`dot ${z ? z.ton : "none"}`} title={z ? `${RANGES[k].label} : ${z.nom}` : "n.d."} />;
}

/** Puce colorée lisible : libellé court + valeur, couleur = zone de la fourchette. */
export function Chip({ k, v, label, value }: { k: string; v: number | null | undefined; label: string; value?: string }) {
  const z = zoneOf(k, v);
  return (
    <span class={`mchip ${z ? z.ton : "none"}`} title={z ? `${RANGES[k].label} : ${z.nom} — ${z.aide}` : `${RANGES[k].label} : n.d.`}>
      {label} <b>{value ?? fmt(k, v, 0)}</b>
    </span>
  );
}

/** Ton (couleur) d'une valeur selon sa fourchette, pour colorer un bloc. */
export function toneOf(k: string, v: number | null | undefined): string {
  return zoneOf(k, v)?.ton ?? "";
}

// ---------------------------------------------------------------------------
// Jauge de fourchette : 3 zones colorées, curseur = valeur, losange = médiane
// ---------------------------------------------------------------------------
export function RangeBar({ k, v, median, medianLabel = "médiane secteur" }:
  { k: string; v: number | null | undefined; median?: number | null; medianLabel?: string }) {
  const r = RANGES[k];
  const [b1, b2] = r.bornes;
  const span = b2 - b1 || 1;
  const lo = b1 - span, hi = b2 + span; // l'échelle couvre une zone de chaque côté
  const pos = (x: number) => Math.max(0, Math.min(100, ((x - lo) / (hi - lo)) * 100));
  const zi = zoneIndex(k, v);
  const z = zoneOf(k, v);
  const txt = bornesTexte(k);
  return (
    <div class="rangebar">
      <div class="rb-head">
        <span class="rb-label">{r.label}</span>
        <span class="rb-value">{fmt(k, v)} {z && <span class={`badge ${z.ton}`}>{z.nom}</span>}</span>
      </div>
      <div class="rb-track" aria-hidden="true">
        {r.zones.map((zone, i) => <div class={`rb-zone ${zone.ton} ${zi === i ? "active" : ""}`} />)}
        {median !== null && median !== undefined && <div class="rb-median" style={{ left: `${pos(median)}%` }} title={`${medianLabel} : ${fmt(k, median)}`} />}
        {v !== null && v !== undefined && !Number.isNaN(v) && <div class="rb-cursor" style={{ left: `${pos(v)}%` }} />}
      </div>
      <div class="rb-scale">{txt.map((t, i) => <span>{r.zones[i].nom}<br /><small>{t}</small></span>)}</div>
      {median !== null && median !== undefined && <div class="rb-foot">◆ {medianLabel} : {fmt(k, median)}</div>}
      {z && <p class="rb-aide">{z.aide}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fiche "Comment lire" : liste des indicateurs de l'écran avec leurs fourchettes
// ---------------------------------------------------------------------------
export function HelpButton({ keys, intro }: { keys: string[]; intro?: ComponentChildren }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button class="help-btn" onClick={() => setOpen(true)} aria-label="Comment lire cet écran">?</button>
      {open && (
        <div class="sheet-backdrop" onClick={() => setOpen(false)}>
          <div class="sheet" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Comment lire">
            <div class="sheet-head"><h2>Comment lire</h2><button class="close" onClick={() => setOpen(false)} aria-label="Fermer">✕</button></div>
            {intro && <div class="sheet-intro">{intro}</div>}
            {keys.map((k) => {
              const r = RANGES[k];
              const t = bornesTexte(k);
              return (
                <div class="help-item">
                  <h3>{r.label}</h3>
                  <p>{r.definition}</p>
                  <ul class="help-zones">
                    {r.zones.map((z, i) => <li><span class={`badge ${z.ton}`}>{z.nom}</span> <b>{t[i]}</b> — {z.aide}</li>)}
                  </ul>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  );
}

const CLE_REPLIS = "thesee:replis:v1";
const lireReplis = (): Record<string, boolean> => { try { return JSON.parse(localStorage.getItem(CLE_REPLIS) ?? "{}"); } catch { return {}; } };

/** Carte. `repliable` : l'en-tête ouvre/ferme le contenu (état mémorisé par titre) ; `ouvert` = état initial. */
export function Card({ title, right, children, class: cls = "", repliable = false, ouvert = true, id }:
  { title?: ComponentChildren; right?: ComponentChildren; children: ComponentChildren; class?: string;
    repliable?: boolean; ouvert?: boolean; id?: string }) {
  const cle = id ?? (typeof title === "string" ? title : "");
  const [estOuvert, setOuvert] = useState<boolean>(() => (repliable && cle in lireReplis() ? lireReplis()[cle] : ouvert));
  const basculer = () => {
    const n = !estOuvert;
    setOuvert(n);
    try { localStorage.setItem(CLE_REPLIS, JSON.stringify({ ...lireReplis(), [cle]: n })); } catch { /* ignore */ }
  };
  if (!repliable) {
    return (
      <section class={`card ${cls}`} id={id}>
        {(title || right) && <div class="card-head"><h2>{title}</h2>{right}</div>}
        {children}
      </section>
    );
  }
  return (
    <section class={`card repliable ${estOuvert ? "ouvert" : ""} ${cls}`} id={id}>
      <div class="card-head">
        <button class="card-toggle" aria-expanded={estOuvert} onClick={basculer}>
          <span class="chevron" aria-hidden="true">›</span><h2>{title}</h2>
        </button>
        {right}
      </div>
      {estOuvert && <div class="card-body">{children}</div>}
    </section>
  );
}

/** Lien discret vers la section de vérification correspondante (Fiche de calculs, modèles…). */
export function Verifier({ href, label = "Vérifier ce calcul" }: { href: string; label?: string }) {
  return <a class="verifier" href={href}>{label} ›</a>;
}

/** Info-bulle : un « i » qui déplie une explication courte. */
export function Info({ children }: { children: ComponentChildren }) {
  const [o, setO] = useState(false);
  return (
    <span class="info">
      <button class="info-btn" aria-label="Explication" aria-expanded={o} onClick={(e) => { e.stopPropagation(); setO(!o); }}>i</button>
      {o && <span class="info-txt" role="note">{children}</span>}
    </span>
  );
}

const fr1 = (x: number) => x.toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** Barre « hasard ↔ probant » : position du t par rapport au seuil exigé. */
/** Force de la preuve en % du seuil : 100 % = juste assez pour exclure le hasard (t = seuil). */
export function forcePreuve(t: number | null | undefined, seuil: number | null | undefined): number | null {
  return t == null || seuil == null || seuil <= 0 ? null : t / seuil;
}
export const textePreuve = (t: number | null | undefined, seuil: number | null | undefined) => {
  const f = forcePreuve(t, seuil);
  return f == null ? "—" : `${Math.round(Math.max(0, f) * 100)} %`;
};

const fr1 = (x: number) => x.toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/** Barre « hasard ↔ probant » : force de la preuve en % du seuil, t et seuil en petit. */
export function BarreSeuil({ t, seuil }: { t: number | null | undefined; seuil: number | null | undefined }) {
  const f = forcePreuve(t, seuil);
  if (f == null) return null;
  const r = Math.max(0, Math.min(1.5, f));
  return (
    <div class="barre-seuil" title={`t = ${t!.toFixed(1)} pour un seuil de ${seuil!.toFixed(1)}`}>
      <span class="force"><b class={f >= 1 ? "up" : ""}>{textePreuve(t, seuil)}</b><small> du seuil</small></span>
      <div class="piste"><div class={`rempli ${r >= 1 ? "ok" : ""}`} style={{ width: `${(r / 1.5) * 100}%` }} /><span class="repere" /></div>
      <small>{f >= 1 ? "probant" : f >= 0.66 ? "proche du seuil" : "hasard possible"}
        <span class="t-petit"> · t {fr1(t!)} / {fr1(seuil!)}</span></small>
    </div>
  );
}

export function Stat({ label, value, sub, cls = "", tone = "" }:
  { label: ComponentChildren; value: ComponentChildren; sub?: ComponentChildren; cls?: string; tone?: string }) {
  return (
    <div class={`stat ${tone ? `tone-${tone}` : ""}`}>
      <div class="stat-label">{label}</div>
      <div class={`stat-value ${cls}`}>{value}</div>
      {sub && <div class="stat-sub">{sub}</div>}
    </div>
  );
}

/** Section repliable. `paresseux` : le contenu n'est créé (et ses données chargées) qu'à la première ouverture. */
export function Details({ summary, children, paresseux = false }: { summary: string; children: ComponentChildren; paresseux?: boolean }) {
  const [ouvert, setOuvert] = useState(false);
  return (
    <details class="details" onToggle={(e) => { if ((e.currentTarget as HTMLDetailsElement).open) setOuvert(true); }}>
      <summary>{summary}</summary>
      <div class="details-body">{!paresseux || ouvert ? children : null}</div>
    </details>
  );
}

// ---------------------------------------------------------------------------
// Graphique (Chart.js) — couleurs lues dans les variables CSS du thème
// ---------------------------------------------------------------------------
export function cssVar(name: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function ChartBox({ config, height = 220, label }: { config: () => any; height?: number; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const cfg = config();
    const muted = cssVar("--muted"), grid = cssVar("--grid");
    cfg.options = {
      responsive: true, maintainAspectRatio: false, animation: false, locale: "fr-FR",
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: muted, boxWidth: 12 } }, tooltip: { enabled: true } },
      ...cfg.options,
      scales: {
        x: { ticks: { color: muted, maxTicksLimit: 5, maxRotation: 0 }, grid: { display: false } },
        y: { ticks: { color: muted, maxTicksLimit: 5 }, grid: { color: grid } },
        ...(cfg.options?.scales ?? {}),
      },
    };
    const chart = new Chart(ref.current, cfg);
    return () => chart.destroy();
  }, [config]);
  return <div class="chart" style={{ height }}><canvas ref={ref} role="img" aria-label={label} /></div>;
}
