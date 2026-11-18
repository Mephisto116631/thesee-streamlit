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

-- ==============================================================================
-- V3 — Portefeuille recommandé (1 ligne, id = 1), calculé par le cron
-- ==============================================================================
create table if not exists portefeuille_recommande (
    id          integer primary key default 1,
    date        date,
    lignes      jsonb,      -- [{symbol, nom, secteur, poids, rendement_1y, volatilite}]
    stats       jsonb,      -- {rendement_1y, volatilite, sharpe, perte_max, ...}
    methode     text,
    updated_at  timestamptz default now()
);
alter table portefeuille_recommande enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'portefeuille_recommande' and policyname = 'lecture publique') then
        create policy "lecture publique" on portefeuille_recommande for select to anon, authenticated using (true);
    end if;
end $$;

-- ==============================================================================
-- V4 — Objectif de rentabilité (frontière efficiente) et taux EUR/USD
-- ==============================================================================
alter table portefeuille_recommande add column if not exists frontiere jsonb;  -- [{cible, rendement, volatilite, sharpe, lignes}]
alter table portefeuille_recommande add column if not exists titres jsonb;     -- {symbol: {nom, secteur, prix, rendement_1y, volatilite}}
alter table market_overview add column if not exists eurusd double precision; -- 1 EUR = x USD

-- V5 — ingrédients de la frontière (l'appli la recalcule avec les hypothèses de l'utilisateur)
alter table portefeuille_recommande add column if not exists univers jsonb;  -- {symbols, mu_hist, beta, cov, jours}

-- V6 — Modèles « horizon » : score de classement relatif par titre et par horizon
create table if not exists scores_horizon (
    symbol      text not null,
    horizon     text not null,          -- 'court' (1 mois) | '6m' | '1a'
    score       double precision,       -- rang 0..1 (1 = meilleure performance relative attendue)
    date        date,
    primary key (symbol, horizon)
);
alter table scores_horizon enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'scores_horizon' and policyname = 'lecture publique') then
        create policy "lecture publique" on scores_horizon for select to anon, authenticated using (true);
    end if;
end $$;

-- V7 — Progression du passage en cours (barre de progression de l'appli)
alter table sync_log add column if not exists progression integer default 0;
alter table sync_log add column if not exists etape text;

-- V8 — Positions de l'utilisateur (connexion e-mail + mot de passe). Chacun ne voit que les siennes.
create table if not exists positions (
    id              uuid primary key default gen_random_uuid(),
    user_id         uuid not null default auth.uid() references auth.users (id) on delete cascade,
    symbol          text not null,
    quantite        double precision not null check (quantite > 0),
    prix_achat_eur  double precision check (prix_achat_eur >= 0),
    frais_eur       double precision not null default 0 check (frais_eur >= 0),
    date_achat      date not null default current_date,
    note            text,
    created_at      timestamptz not null default now()
);
create index if not exists idx_positions_user on positions (user_id);
alter table positions enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where schemaname='public' and tablename='positions' and policyname='positions du proprietaire') then
        create policy "positions du proprietaire" on positions for all to authenticated
            using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
    end if;
end $$;

-- V9 — Laboratoire : essais de variantes du modèle (experiences.py), lecture publique
create table if not exists experiences (
    id              bigint generated always as identity primary key,
    lot             text not null,          -- date et heure du lancement
    nom             text not null,          -- 'reference' | 'alpha' | 'alpha_secteur' | ...
    horizon         text not null,          -- '6m' | '1a'
    description     text,
    ic              double precision,
    t_stat          double precision,
    seuil_t_global  double precision,       -- seuil corrigé du nombre total d'essais
    n_essais        integer,
    verdict         text,                   -- 'probant' | 'non probant'
    diagnostics     jsonb,
    cree_le         timestamptz not null default now()
);
alter table experiences enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'experiences' and policyname = 'lecture publique') then
        create policy "lecture publique" on experiences for select to anon, authenticated using (true);
    end if;
end $$;
