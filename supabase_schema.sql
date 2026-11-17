-- ==============================================================================
-- SCHEMA SUPABASE — THESEE (remplace le cache local DuckDB)
-- A executer dans : Supabase Dashboard > SQL Editor > New Query
-- ==============================================================================

-- 1. Donnees de marche (OHLCV quotidien, Yahoo Finance)
create table if not exists market_data (
    symbol      text not null,
    date        date not null,
    open        double precision,
    high        double precision,
    low         double precision,
    close       double precision,
    volume      bigint,
    primary key (symbol, date)
);

create index if not exists idx_market_data_symbol on market_data (symbol);
create index if not exists idx_market_data_date on market_data (date);

-- 2. Donnees macro (VIX, SPY...)
create table if not exists macro_data (
    symbol      text not null,
    date        date not null,
    open        double precision,
    high        double precision,
    low         double precision,
    close       double precision,
    volume      bigint,
    primary key (symbol, date)
);

-- 3. Donnees fondamentales (Alpha Vantage OVERVIEW), avec TTL via last_updated
create table if not exists fonda_data (
    symbol          text primary key,
    roe             double precision,
    ev_ebitda       double precision,
    debt_eq         double precision,
    margin          double precision,
    last_updated    date not null default current_date
);

-- 4. Ratings de credit S&P (table de reference statique)
create table if not exists ratings_sp (
    symbol      text primary key,
    rating_sp   text not null
);

-- Seed initial des ratings (modifiable manuellement / trimestriellement)
insert into ratings_sp (symbol, rating_sp) values
    ('AAPL',  'AA+'),
    ('MSFT',  'AAA'),
    ('NVDA',  'A+'),
    ('JPM',   'A-'),
    ('LLY',   'A'),
    ('TSLA',  'BB+'),
    ('AMZN',  'AA-'),
    ('META',  'AA-'),
    ('GOOGL', 'AA+'),
    ('V',     'AA-'),
    ('MA',    'A+'),
    ('UNH',   'A+')
on conflict (symbol) do nothing;

-- ==============================================================================
-- NOTES
-- ==============================================================================
-- - RLS (Row Level Security) : voir la section SÉCURITÉ en fin de fichier
--   (lecture seule pour la clé anon, écriture réservée à la clé service_role).
-- - Le TTL de 7 jours sur fonda_data est gere cote application Python
--   (comparaison a current_date - 7), pas par une contrainte SQL.
-- - market_data et macro_data utilisent une cle composite (symbol, date) pour
--   permettre un upsert natif Postgres (`on conflict (symbol, date) do update`),
--   ce qui resout le probleme rencontre avec DuckDB (pas de contrainte unique).

-- ==============================================================================
-- V2 — tables manquantes + tables "prêtes à afficher" pour l'APK
-- Script idempotent : peut être ré-exécuté sans risque.
-- ==============================================================================

-- 5. Altman Z-Score (TTL 7 jours géré en Python)
create table if not exists zscore_data (
    symbol        text primary key,
    z_score       double precision,
    last_updated  date not null default current_date
);

-- 6. Spreads de crédit FRED (HY / IG)
create table if not exists credit_spreads (
    serie_id  text not null,
    date      date not null,
    valeur    double precision,
    primary key (serie_id, date)
);

-- 7. Dernière date par ticker (sync incrémentale du cron, 1 ligne par ticker)
create or replace view market_data_last as
    select symbol, max(date) as last_date from market_data group by symbol;
create or replace view macro_data_last as
    select symbol, max(date) as last_date from macro_data group by symbol;

-- 8. Journal des synchronisations (affiché dans l'app : "Données au ...")
create table if not exists sync_log (
    id           bigint generated always as identity primary key,
    started_at   timestamptz not null default now(),
    finished_at  timestamptz,
    status       text not null default 'running',   -- running | success | error
    n_tickers    integer default 0,
    message      text
);

-- 9. Instantané par titre : 1 ligne par ticker, tout pré-calculé par le cron
--    (nom distinct de `screener_snapshot`, utilisée par la branche test-modele-relatif)
create table if not exists titres_snapshot (
    symbol        text primary key,
    nom           text,
    secteur       text,
    indice        text,
    is_etf        boolean default false,
    date          date,
    close         double precision,
    chg_1d        double precision,   -- variations en fraction (0.012 = +1.2 %)
    chg_5d        double precision,
    chg_20d       double precision,
    chg_1y        double precision,
    rsi_14        double precision,
    volatility    double precision,   -- annualisée, fraction
    pct_vs_ma50   double precision,
    pct_vs_ma200  double precision,
    high_52w      double precision,
    low_52w       double precision,
    roe           double precision,
    margin        double precision,
    ev_ebitda     double precision,
    debt_eq       double precision,
    z_score       double precision,
    rating_sp     text,
    proba_hausse  double precision,   -- proba IA d'un mouvement significatif à la hausse demain
    updated_at    timestamptz default now()
);

-- 10. Médianes par secteur (comparaison d'un titre à ses pairs)
create table if not exists sector_medians (
    secteur      text primary key,
    n            integer,
    chg_20d      double precision,
    chg_1y       double precision,
    rsi_14       double precision,
    volatility   double precision,
    roe          double precision,
    margin       double precision,
    ev_ebitda    double precision,
    debt_eq      double precision,
    updated_at   timestamptz default now()
);

-- 11. Résultats des modèles IA (1 ligne par modèle : actions / etf)
create table if not exists model_runs (
    kind          text primary key,     -- 'actions' | 'etf'
    trained_at    timestamptz default now(),
    accuracy      double precision,
    baseline      double precision,
    gain_pts      double precision,
    verdict       text,                 -- 'aucun' | 'bruit' | 'signal'
    importance    jsonb,                -- [{feature, label, importance}]
    diagnostics   jsonb                 -- diagnostics complets (walk-forward, calibration...)
);

-- 12. Signal IA par ticker + explication SHAP (top facteurs)
create table if not exists signals (
    symbol        text primary key,
    kind          text,                 -- 'actions' | 'etf'
    date          date,
    proba_hausse  double precision,
    facteurs      jsonb,                -- [{feature, label, valeur, impact}]
    updated_at    timestamptz default now()
);

-- 13. Vue d'ensemble du marché (1 seule ligne, id = 1)
create table if not exists market_overview (
    id               integer primary key default 1,
    date             date,
    vix              double precision,
    vix_regime       integer,
    hy_spread_bp     double precision,
    hy_pct_10y       double precision,  -- percentile du spread actuel sur 10 ans (0-100)
    hy_min_10y       double precision,
    hy_med_10y       double precision,
    hy_max_10y       double precision,
    ig_spread_bp     double precision,
    ig_pct_10y       double precision,
    ig_min_10y       double precision,
    ig_med_10y       double precision,
    ig_max_10y       double precision,
    pct_above_ma50   double precision,  -- % des titres au-dessus de leur MM50
    pct_above_ma200  double precision,
    n_hausse_1d      integer,
    n_baisse_1d      integer,
    updated_at       timestamptz default now()
);

-- 14. Historique 1 an pour les graphiques de l'APK (lecture légère)
create or replace view price_history_1y as
    select symbol, date, close, volume
    from market_data
    where date >= current_date - interval '400 days';

-- ==============================================================================
-- SÉCURITÉ — RLS : la clé "anon" (embarquée dans l'APK, publique par nature)
-- peut uniquement LIRE. Le cron écrit avec la clé service_role (secret GitHub),
-- qui contourne RLS. L'app Streamlit peut garder la clé service_role ou anon.
-- ==============================================================================
do $$
declare t text;
begin
    foreach t in array array[
        'market_data', 'macro_data', 'fonda_data', 'ratings_sp', 'zscore_data',
        'credit_spreads', 'sync_log', 'titres_snapshot', 'sector_medians',
        'model_runs', 'signals', 'market_overview'
    ] loop
        execute format('alter table %I enable row level security', t);
        execute format('drop policy if exists "lecture publique" on %I', t);
        execute format('create policy "lecture publique" on %I for select to anon, authenticated using (true)', t);
    end loop;
end $$;

-- Les vues héritent des droits du propriétaire par défaut : on force les droits de l'appelant.
alter view market_data_last set (security_invoker = true);
alter view macro_data_last set (security_invoker = true);
alter view price_history_1y set (security_invoker = true);
