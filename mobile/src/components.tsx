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
export function useData<T>(loader: () => Promise<Result<T>>, deps: unknown[] = []) {
  const [res, setRes] = useState<Result<T> | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    loader().then((r) => { if (alive) { setRes(r); setLoading(false); } });
    return () => { alive = false; };
  }, deps);
  return { data: res?.data, res, loading };
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

export function Card({ title, right, children, class: cls = "" }:
  { title?: ComponentChildren; right?: ComponentChildren; children: ComponentChildren; class?: string }) {
  return (
    <section class={`card ${cls}`}>
      {(title || right) && <div class="card-head"><h2>{title}</h2>{right}</div>}
      {children}
    </section>
  );
}

export function Stat({ label, value, sub, cls = "" }: { label: string; value: ComponentChildren; sub?: ComponentChildren; cls?: string }) {
  return (
    <div class="stat">
      <div class="stat-label">{label}</div>
      <div class={`stat-value ${cls}`}>{value}</div>
      {sub && <div class="stat-sub">{sub}</div>}
    </div>
  );
}

export function Details({ summary, children }: { summary: string; children: ComponentChildren }) {
  return <details class="details"><summary>{summary}</summary><div class="details-body">{children}</div></details>;
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
