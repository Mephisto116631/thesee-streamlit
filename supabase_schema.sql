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
-- - Pas de RLS (Row Level Security) active : conforme a ta demande "SQL standard,
--   pas d'auth pour l'instant". Les clients Streamlit utiliseront la cle anon
--   ou service_role selon le niveau d'acces souhaite cote .env.
-- - Le TTL de 7 jours sur fonda_data est gere cote application Python
--   (comparaison a current_date - 7), pas par une contrainte SQL.
-- - market_data et macro_data utilisent une cle composite (symbol, date) pour
--   permettre un upsert natif Postgres (`on conflict (symbol, date) do update`),
--   ce qui resout le probleme rencontre avec DuckDB (pas de contrainte unique).
