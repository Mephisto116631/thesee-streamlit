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
    status       text not null default 'running',   -- running | success | partiel | error
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
-- qui contourne RLS.
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

-- V10 — Volatilité prévue par l'IA de risque (6 mois) pour chaque titre suivi
alter table titres_snapshot add column if not exists vol_ia double precision;

-- V11 — Suivi en conditions réelles de l'IA de volatilité : la prévision de chaque titre est
-- enregistrée une fois par semaine, puis comparée 6 mois plus tard à la volatilité observée.
create table if not exists suivi_volatilite (
    date        date not null,              -- séance de la prévision
    symbol      text not null,
    vol_prevue  double precision not null,  -- volatilité annuelle prévue par l'IA (6 mois)
    vol_3m      double precision,           -- référence naïve : volatilité des 3 derniers mois
    primary key (date, symbol)
);
alter table suivi_volatilite enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'suivi_volatilite' and policyname = 'lecture publique') then
        create policy "lecture publique" on suivi_volatilite for select to anon, authenticated using (true);
    end if;
end $$;

-- V12 — Valorisation depuis les comptes officiels déposés à la SEC (mise à jour hebdomadaire)
alter table titres_snapshot add column if not exists bpa_sec double precision;          -- bénéfice par action annuel
alter table titres_snapshot add column if not exists vc_action_sec double precision;    -- fonds propres par action
alter table titres_snapshot add column if not exists roe_sec double precision;          -- bénéfice / fonds propres
alter table titres_snapshot add column if not exists rentabilite_brute double precision; -- marge brute / actifs
alter table titres_snapshot add column if not exists endettement double precision;      -- 1 − fonds propres / actifs
alter table titres_snapshot add column if not exists part_encaissee double precision;   -- trésorerie d'exploitation / bénéfice
alter table titres_snapshot add column if not exists comptes_date date;                 -- publication des comptes utilisés
alter table titres_snapshot add column if not exists sec_maj timestamptz;
alter table sector_medians add column if not exists per double precision;
alter table sector_medians add column if not exists cours_vc double precision;
alter table sector_medians add column if not exists roe_sec double precision;
alter table sector_medians add column if not exists rentabilite_brute double precision;
alter table sector_medians add column if not exists endettement double precision;
alter table sector_medians add column if not exists part_encaissee double precision;

-- V13 — Univers du portefeuille sous forme factorielle (~500 titres du S&P 500). Nouvelle colonne :
-- les anciennes versions de l'appli lisent `univers` (vide désormais) et affichent la frontière du serveur.
alter table portefeuille_recommande add column if not exists univers_facteurs jsonb;

-- V14 — Révisions du portefeuille (1 à 2 fois par an, docs/METHODE.md § 4.9) : l'univers (titres, covariance
-- factorielle, volatilité prévue) est figé à chaque révision ; l'appli construit le portefeuille conseillé
-- à partir de la dernière révision de son rythme (6 ou 12 mois) au lieu de l'univers du jour.
create table if not exists revisions_portefeuille (
    date              date primary key,
    univers_facteurs  jsonb not null,
    titres            jsonb,
    methode           text,
    cree_le           timestamptz not null default now()
);
alter table revisions_portefeuille enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'revisions_portefeuille' and policyname = 'lecture publique') then
        create policy "lecture publique" on revisions_portefeuille for select to anon, authenticated using (true);
    end if;
end $$;

-- V15 — Suivi en conditions réelles du risque du mois à venir (docs/METHODE.md § 4.18) : chaque semaine, la prévision
-- à 22 séances de HAR-X (avec le VIX) et de HAR seul est enregistrée, puis jugée sur ce qui arrive vraiment.
create table if not exists suivi_risque_mois (
    date      date not null,              -- séance de la prévision
    symbol    text not null,
    vol_harx  double precision not null,  -- volatilité annuelle prévue à 22 séances, HAR + VIX
    vol_har   double precision not null,  -- même ajustement sans le VIX (référence)
    primary key (date, symbol)
);
alter table suivi_risque_mois enable row level security;
do $$ begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'suivi_risque_mois' and policyname = 'lecture publique') then
        create policy "lecture publique" on suivi_risque_mois for select to anon, authenticated using (true);
    end if;
end $$;

-- V16 — Calculs automatiques à l'heure. Les tâches planifiées de GitHub démarraient 7 à 9 heures en retard :
-- la base appelle la fonction Edge « calcul-programme », qui lance sync.yml (déployer cette fonction AVANT).
create extension if not exists pg_cron;
create extension if not exists pg_net;
create schema if not exists prive;                       -- non exposé par l'API
revoke all on schema prive from public, anon, authenticated;

-- Secret aléatoire partagé entre la tâche et la fonction : créé ici, jamais affiché ni copié
do $$ begin
    if not exists (select 1 from vault.secrets where name = 'jeton_calcul_programme') then
        perform vault.create_secret(encode(extensions.gen_random_bytes(32), 'hex'), 'jeton_calcul_programme',
                                    'En-tête x-jeton-calcul de la fonction calcul-programme');
    end if;
end $$;

-- Appelée par la fonction Edge (clé service_role seulement)
create or replace function public.verifier_jeton_calcul(jeton text) returns boolean
language sql stable security definer set search_path = '' as $$
    select coalesce((
        select extensions.digest(coalesce(jeton, ''), 'sha256') = extensions.digest(decrypted_secret, 'sha256')
        from vault.decrypted_secrets where name = 'jeton_calcul_programme'), false)
$$;
revoke all on function public.verifier_jeton_calcul(text) from public, anon, authenticated;
grant execute on function public.verifier_jeton_calcul(text) to service_role;

-- Passage prévu à cet instant (heure de New York, donc sans décalage été / hiver), sinon null.
-- Arrondi à la demi-heure : un léger retard de la tâche ne fait pas sauter le passage.
create or replace function prive.creneau_calcul(instant timestamptz) returns text
language sql stable set search_path = '' as $$
    select case when extract(isodow from ny) between 1 and 5 then
        case to_char(ny, 'HH24:MI') when '10:00' then 'ouverture' when '13:00' then 'mi-seance'
                                    when '16:30' then 'cloture' end end
    from (select date_bin('30 minutes', instant, timestamptz '2000-01-01 00:00:00+00')
                 at time zone 'America/New_York' as ny) t
$$;

create or replace function prive.lancer_calcul_programme() returns void
language plpgsql set search_path = '' as $$
declare creneau text := prive.creneau_calcul(now());
begin
    if creneau is null then return; end if;
    perform net.http_post(
        url := 'https://ommkiaoqnavcxvxsoiwg.supabase.co/functions/v1/calcul-programme',
        headers := jsonb_build_object('Content-Type', 'application/json', 'x-jeton-calcul',
            (select decrypted_secret from vault.decrypted_secrets where name = 'jeton_calcul_programme')),
        body := jsonb_build_object('creneau', creneau),
        timeout_milliseconds := 15000);
end $$;
revoke all on function prive.creneau_calcul(timestamptz) from public, anon, authenticated;
revoke all on function prive.lancer_calcul_programme() from public, anon, authenticated;

-- Toutes les demi-heures de 14 h à 21 h 30 UTC (couvre été et hiver) ; la fonction ne garde que les 3 passages.
-- Arrêter : select cron.unschedule('calcul-programme');
-- Suivre  : select * from net._http_response order by created desc;   (réponses gardées 6 heures)
select cron.schedule('calcul-programme', '0,30 14-21 * * 1-5', 'select prive.lancer_calcul_programme()');
