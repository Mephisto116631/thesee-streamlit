// Accès aux données — LECTURE SEULE. Clé "anon" publique, protégée par RLS
// (supabase_schema.sql) : impossible d'écrire avec. Toutes les tables sont
// pré-calculées par le cron (publish.py).
import { createClient } from "@supabase/supabase-js";

const URL = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;
export const configured = Boolean(URL && KEY);
const sb = configured ? createClient(URL!, KEY!, { auth: { persistSession: false } }) : null;

export interface Snapshot {
  symbol: string; nom: string; secteur: string; indice: string; is_etf: boolean; date: string;
  close: number; chg_1d: number | null; chg_5d: number | null; chg_20d: number | null; chg_1y: number | null;
  rsi_14: number | null; volatility: number | null; pct_vs_ma50: number | null; pct_vs_ma200: number | null;
  high_52w: number | null; low_52w: number | null;
  roe: number | null; margin: number | null; ev_ebitda: number | null; debt_eq: number | null;
  z_score: number | null; rating_sp: string | null; proba_hausse: number | null;
}
export interface SectorMedian {
  secteur: string; n: number; chg_20d: number | null; chg_1y: number | null; rsi_14: number | null;
  volatility: number | null; roe: number | null; margin: number | null; ev_ebitda: number | null; debt_eq: number | null;
}
export interface Facteur { feature: string; label: string; valeur: number | null; impact: number }
export interface Signal { symbol: string; kind: string; date: string; proba_hausse: number; facteurs: Facteur[] }
export interface ModelRun {
  kind: "actions" | "etf"; trained_at: string; accuracy: number | null; baseline: number | null;
  gain_pts: number | null; verdict: "aucun" | "bruit" | "signal";
  importance: { feature: string; label: string; importance: number }[];
  diagnostics: any;
}
export interface Overview {
  date: string; vix: number | null; vix_regime: number | null;
  hy_spread_bp: number | null; hy_pct_10y: number | null; hy_min_10y: number | null; hy_med_10y: number | null; hy_max_10y: number | null;
  ig_spread_bp: number | null; ig_pct_10y: number | null; ig_min_10y: number | null; ig_med_10y: number | null; ig_max_10y: number | null;
  pct_above_ma50: number | null; pct_above_ma200: number | null; n_hausse_1d: number; n_baisse_1d: number;
  eurusd?: number | null;
}
export interface LigneReco { symbol: string; nom: string; secteur: string | null; poids: number; rendement_1y: number; volatilite: number }
export interface PortefeuilleReco {
  date: string; methode: string; updated_at: string;
  lignes: LigneReco[];
  stats: { rendement_1y: number; volatilite: number; sharpe: number | null; perte_max: number; poids_secteur_max: number; secteur_principal: string;
    rendement_attendu?: number; volatilite_attendue?: number };
  frontiere?: { cible: number; rendement: number; volatilite: number; sharpe: number | null; lignes: { symbol: string; poids: number }[] }[];
  titres?: Record<string, { nom: string; secteur: string | null; prix: number | null; rendement_1y: number; volatilite: number }>;
  univers?: { symbols: string[]; mu_hist: number[]; beta: number[]; cov: number[][]; jours: number };
}
export interface SyncLog { started_at: string; finished_at: string | null; status: string; message: string | null }
export interface PricePoint { symbol: string; date: string; close: number }
export interface SpreadPoint { serie_id: string; date: string; valeur: number }

// ---------------------------------------------------------------------------
// Cache local : la dernière réponse de chaque requête est gardée sur le
// téléphone -> l'appli s'ouvre instantanément et reste consultable hors ligne.
// ---------------------------------------------------------------------------
const CACHE_PREFIX = "thesee:v1:";
interface Cached<T> { at: number; data: T }

function readCache<T>(key: string): Cached<T> | null {
  try {
    const s = localStorage.getItem(CACHE_PREFIX + key);
    return s ? (JSON.parse(s) as Cached<T>) : null;
  } catch { return null; }
}
function writeCache<T>(key: string, data: T) {
  try { localStorage.setItem(CACHE_PREFIX + key, JSON.stringify({ at: Date.now(), data })); } catch { /* quota */ }
}

export interface Result<T> { data: T; fromCache: boolean; cachedAt?: number; error?: string }

async function cached<T>(key: string, fetcher: () => Promise<T>, fallback: T): Promise<Result<T>> {
  const c = readCache<T>(key);
  if (!sb) return { data: c?.data ?? fallback, fromCache: true, cachedAt: c?.at, error: "Appli non configurée (URL/clé Supabase absentes du build)." };
  try {
    const data = await fetcher();
    writeCache(key, data);
    return { data, fromCache: false };
  } catch (e: any) {
    return { data: c?.data ?? fallback, fromCache: true, cachedAt: c?.at, error: e?.message ?? String(e) };
  }
}

/** Lit toutes les lignes (PostgREST renvoie 1000 lignes max par requête). */
async function selectAll<T>(build: (from: number, to: number) => PromiseLike<{ data: T[] | null; error: any }>): Promise<T[]> {
  const out: T[] = [];
  for (let from = 0; from < 500_000; from += 1000) { // garde-fou : jamais de boucle infinie
    const { data, error } = await build(from, from + 999);
    if (error) throw new Error(error.message);
    out.push(...(data ?? []));
    if (!data || data.length < 1000) return out;
  }
  return out;
}

export const api = {
  snapshot: () => cached<Snapshot[]>("snapshot",
    () => selectAll((a, b) => sb!.from("titres_snapshot").select("*").order("symbol").range(a, b)), []),

  medians: () => cached<SectorMedian[]>("medians",
    () => selectAll((a, b) => sb!.from("sector_medians").select("*").range(a, b)), []),

  overview: () => cached<Overview | null>("overview", async () => {
    const { data, error } = await sb!.from("market_overview").select("*").eq("id", 1).maybeSingle();
    if (error) throw new Error(error.message);
    return data as Overview | null;
  }, null),

  models: () => cached<ModelRun[]>("models", async () => {
    const { data, error } = await sb!.from("model_runs").select("*");
    if (error) throw new Error(error.message);
    return (data ?? []) as ModelRun[];
  }, []),

  lastSync: () => cached<SyncLog | null>("sync", async () => {
    const { data, error } = await sb!.from("sync_log").select("*").order("started_at", { ascending: false }).limit(1).maybeSingle();
    if (error) throw new Error(error.message);
    return data as SyncLog | null;
  }, null),

  portefeuilleReco: () => cached<PortefeuilleReco | null>("reco", async () => {
    const { data, error } = await sb!.from("portefeuille_recommande").select("*").eq("id", 1).maybeSingle();
    if (error) throw new Error(error.message);
    return data as PortefeuilleReco | null;
  }, null),

  signal: (symbol: string) => cached<Signal | null>(`signal:${symbol}`, async () => {
    const { data, error } = await sb!.from("signals").select("*").eq("symbol", symbol).maybeSingle();
    if (error) throw new Error(error.message);
    return data as Signal | null;
  }, null),

  prices: (symbols: string[]) => cached<PricePoint[]>(`prices:${[...symbols].sort().join(",")}`,
    () => selectAll((a, b) => sb!.from("price_history_1y").select("symbol,date,close")
      .in("symbol", symbols).order("symbol").order("date").range(a, b)), []),

  spreads: () => cached<SpreadPoint[]>("spreads",
    () => selectAll((a, b) => sb!.from("credit_spreads").select("serie_id,date,valeur")
      .gte("date", new Date(Date.now() - 3 * 365 * 864e5).toISOString().slice(0, 10))
      .order("serie_id").order("date").range(a, b)), []),
};

// Favoris (sur le téléphone uniquement)
const FAV_KEY = "thesee:favoris";
export function getFavoris(): string[] {
  try { return JSON.parse(localStorage.getItem(FAV_KEY) ?? "[]"); } catch { return []; }
}
export function toggleFavori(s: string): string[] {
  const f = getFavoris();
  const next = f.includes(s) ? f.filter((x) => x !== s) : [...f, s];
  try { localStorage.setItem(FAV_KEY, JSON.stringify(next)); } catch { /* ignore */ }
  return next;
}
