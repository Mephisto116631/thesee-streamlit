-- ==============================================================================
-- MIGRATION 003 — résultats des modèles et snapshot du screener
-- L'entraînement tourne dans le CRON GitHub Actions ; l'app Streamlit ne fait
-- que LIRE ces tables (elle n'entraîne plus rien, ce qui évite le bridage CPU).
-- A exécuter dans : Supabase Dashboard > SQL Editor > New Query
-- ==============================================================================

-- Résultats d'un modèle (diagnostics, importance des features, comparaison de seuils)
-- model : 'jour' | 'relatif' | 'etf' | 'meta'
create table if not exists model_results (
    model       text primary key,
    payload     jsonb not null,
    updated_at  timestamptz not null default now()
);

-- Valeurs SHAP du dernier jour disponible, pour chaque titre et chaque modèle
create table if not exists shap_latest (
    model       text not null,
    symbol      text not null,
    date        date,
    payload     jsonb not null,
    primary key (model, symbol)
);

-- Dernière ligne d'indicateurs par titre (alimente le Screener)
create table if not exists screener_snapshot (
    symbol      text primary key,
    date        date,
    payload     jsonb not null
);

-- Dernière date et nombre de lignes par titre (lecture légère : ~500 lignes)
create or replace view market_data_status
    with (security_invoker = true) as
    select symbol, max(date) as max_date, count(*) as n
    from market_data
    group by symbol;

-- Même politique que les autres tables : RLS activé, accès via la clé secrète côté serveur
alter table model_results enable row level security;
alter table shap_latest enable row level security;
alter table screener_snapshot enable row level security;
