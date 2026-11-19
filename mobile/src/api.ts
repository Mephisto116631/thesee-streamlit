// Accès aux données — LECTURE SEULE. Clé "anon" publique, protégée par RLS
// (supabase_schema.sql) : impossible d'écrire avec. Toutes les tables sont
// pré-calculées par le cron (publish.py).
import { createClient } from "@supabase/supabase-js";
import type { LaboVol } from "./fiabilite";

const URL = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const KEY = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;
export const configured = Boolean(URL && KEY);
// Session conservée sur le téléphone : nécessaire pour « Mes positions » (connexion).
// Les autres données restent publiques en lecture seule (RLS).
const sb = configured ? createClient(URL!, KEY!, {
  auth: { persistSession: true, autoRefreshToken: true, storageKey: "thesee-auth" },
}) : null;

export interface Snapshot {
  symbol: string; nom: string; secteur: string; indice: string; is_etf: boolean; date: string;
  close: number; chg_1d: number | null; chg_5d: number | null; chg_20d: number | null; chg_1y: number | null;
  rsi_14: number | null; volatility: number | null; pct_vs_ma50: number | null; pct_vs_ma200: number | null;
  high_52w: number | null; low_52w: number | null;
  roe: number | null; margin: number | null; ev_ebitda: number | null; debt_eq: number | null;
  z_score: number | null; rating_sp: string | null; proba_hausse: number | null;
  vol_ia?: number | null;   // volatilité prévue par l'IA de risque (6 mois), publiée seulement si probante
  // Comptes officiels déposés à la SEC (mis à jour chaque semaine)
  bpa_sec?: number | null; vc_action_sec?: number | null; roe_sec?: number | null; rentabilite_brute?: number | null;
  endettement?: number | null; part_encaissee?: number | null; comptes_date?: string | null;
}
export interface SectorMedian {
  secteur: string; n: number; chg_20d: number | null; chg_1y: number | null; rsi_14: number | null;
  volatility: number | null; roe: number | null; margin: number | null; ev_ebitda: number | null; debt_eq: number | null;
  per?: number | null; cours_vc?: number | null; roe_sec?: number | null; rentabilite_brute?: number | null;
  endettement?: number | null; part_encaissee?: number | null;
}
export interface Facteur { feature: string; label: string; valeur: number | null; impact: number }
export interface Signal { symbol: string; kind: string; date: string; proba_hausse: number; facteurs: Facteur[] }
export interface Experience {
  id: number; lot: string; nom: string; horizon: string; description: string | null;
  ic: number | null; t_stat: number | null; seuil_t_global: number | null; n_essais: number | null;
  verdict: string; regimes: { hausse?: { ic: number | null }; baisse?: { ic: number | null } } | null;
  ic_base: number | null; cree_le: string;
}
export interface ModelRun {
  kind: string; // "actions" | "etf" | "horizon_court" | "horizon_6m" | "horizon_1a"
  trained_at: string; accuracy: number | null; baseline: number | null;
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
  titres?: Record<string, { nom: string; secteur: string | null; prix: number | null; rendement_1y: number; volatilite: number; vol_ia?: number }>;
  univers?: { symbols: string[]; mu_hist: number[]; beta: number[]; cov: number[][]; jours: number } | null;   // ancien format (≤ PR #24)
  univers_facteurs?: { symbols: string[]; mu_hist: number[]; beta: number[]; facteurs: number[][]; idio: number[]; jours: number } | null;
}
export interface ScoreHorizon { symbol: string; horizon: "court" | "6m" | "1a"; score: number; date: string }
export interface SyncLog { started_at: string; finished_at: string | null; status: string; message: string | null;
  progression?: number | null; etape?: string | null }
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

  experiences: () => cached<Experience[]>("experiences", async () => {
    const { data, error } = await sb!.from("experiences")
      .select("id,lot,nom,horizon,description,ic,t_stat,seuil_t_global,n_essais,verdict,regimes:diagnostics->regimes,ic_base:diagnostics->ic_base,cree_le")
      .order("id", { ascending: false }).limit(60);
    if (error) throw new Error(error.message);
    return (data ?? []) as Experience[];
  }, []),

  /** Examen approfondi de l'IA de volatilité : dernier résultat de chaque essai « examen_* ». */
  examen: () => cached<{ nom: string; verdict: string; diagnostics: any; cree_le: string }[]>("examen", async () => {
    const { data, error } = await sb!.from("experiences").select("nom,verdict,diagnostics,cree_le")
      .like("nom", "examen_%").order("id", { ascending: false }).limit(40);
    if (error) throw new Error(error.message);
    const vus = new Set<string>();
    return (data ?? []).filter((r: any) => (vus.has(r.nom) ? false : (vus.add(r.nom), true)));
  }, []),

  /** Dernier backtest du portefeuille Hold (volatilité historique / 3 mois / IA). */
  backtestVol: () => cached<any | null>("backtest-vol", async () => {
    const { data, error } = await sb!.from("experiences").select("diagnostics,cree_le")
      .eq("nom", "backtest_volatilite_sharpe_max").order("id", { ascending: false }).limit(1).maybeSingle();
    if (error) throw new Error(error.message);
    return data ?? null;
  }, null),

  /** Dernier test de l'IA de volatilité à 6 mois + bilan en conditions réelles. */
  fiabiliteVol: () => cached<{ labo: LaboVol | null; run: ModelRun | null }>("fiabilite-vol", async () => {
    const [l, r] = await Promise.all([
      sb!.from("experiences").select("verdict,t_stat,seuil_t_global,cree_le,ic:diagnostics->ic_moyen,ic_base:diagnostics->ic_base,"
        + "gain:diagnostics->gain,part:diagnostics->part_dates_gagnantes")
        .eq("nom", "risque_volatilite").eq("horizon", "6m").order("id", { ascending: false }).limit(1).maybeSingle(),
      sb!.from("model_runs").select("*").eq("kind", "risque_volatilite_reel").maybeSingle(),
    ]);
    if (l.error) throw new Error(l.error.message);
    return { labo: (l.data ?? null) as LaboVol | null, run: (r.data ?? null) as ModelRun | null };
  }, { labo: null, run: null }),

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

  scores: (horizon: "court" | "6m" | "1a") => cached<ScoreHorizon[]>(`scores:${horizon}`,
    () => selectAll((a, b) => sb!.from("scores_horizon").select("*").eq("horizon", horizon).order("symbol").range(a, b)), []),

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

/** Demande un nouveau calcul (synchro + ré-entraînement des modèles) via la fonction Supabase. */
export async function relancerCalcul(): Promise<{ ok: boolean; message: string }> {
  if (!sb) return { ok: false, message: "Appli non configurée." };
  const { data, error } = await sb.functions.invoke("relancer-calcul", { method: "POST" });
  if (error) {
    // Les réponses 4xx/5xx de la fonction contiennent un message lisible
    try {
      const corps = await (error as any).context?.json?.();
      if (corps?.message) return { ok: false, message: corps.message };
    } catch { /* ignore */ }
    return { ok: false, message: error.message };
  }
  return data as { ok: boolean; message: string };
}

// ---------------------------------------------------------------------------
// Compte et positions (table « positions », visibles uniquement par leur propriétaire)
// ---------------------------------------------------------------------------
export interface Position {
  id: string; symbol: string; quantite: number; prix_achat_eur: number | null;
  frais_eur: number; date_achat: string; note: string | null;
}

export async function utilisateurCourant(): Promise<{ email: string } | null> {
  if (!sb) return null;
  const { data } = await sb.auth.getSession();
  return data.session?.user?.email ? { email: data.session.user.email } : null;
}

export function surChangementSession(cb: () => void): () => void {
  if (!sb) return () => {};
  const { data } = sb.auth.onAuthStateChange(() => cb());
  return () => data.subscription.unsubscribe();
}

export async function connexion(email: string, motDePasse: string, creer: boolean): Promise<string | null> {
  if (!sb) return "Appli non configurée.";
  const r = creer
    ? await sb.auth.signUp({ email, password: motDePasse })
    : await sb.auth.signInWithPassword({ email, password: motDePasse });
  if (r.error) return r.error.message;
  if (creer && !r.data.session) return "Compte créé : confirme ton adresse avec le lien reçu par e-mail, puis connecte-toi.";
  return null;
}

export async function deconnexion() { await sb?.auth.signOut(); }

export async function lirePositions(): Promise<Position[]> {
  const { data, error } = await sb!.from("positions").select("*").order("date_achat", { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as Position[];
}

export async function ajouterPositions(lignes: Omit<Position, "id">[]): Promise<string | null> {
  const { error } = await sb!.from("positions").insert(lignes);
  return error ? error.message : null;
}

export async function modifierPosition(id: string, champs: Partial<Omit<Position, "id">>): Promise<string | null> {
  const { error } = await sb!.from("positions").update(champs).eq("id", id);
  return error ? error.message : null;
}

export async function supprimerPosition(id: string): Promise<string | null> {
  const { error } = await sb!.from("positions").delete().eq("id", id);
  return error ? error.message : null;
}
