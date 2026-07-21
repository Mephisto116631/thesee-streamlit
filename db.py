# db.py
# ==============================================================================
# COUCHE DE PERSISTANCE — SUPABASE (remplace global_data.py / DuckDB)
# ==============================================================================
import os
import pandas as pd
from datetime import date, timedelta
from supabase import create_client, Client
import streamlit as st


def _get_secret(key: str, default: str = "") -> str:
    """Lit depuis st.secrets (local via .streamlit/secrets.toml, ou Streamlit Cloud > Settings > Secrets)."""
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)


SUPABASE_URL = _get_secret("SUPABASE_URL")
SUPABASE_KEY = _get_secret("SUPABASE_KEY")

def get_client() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_KEY manquants. "
            "Verifie ton fichier .env ou tes secrets Streamlit Cloud."
        )
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ------------------------------------------------------------------------------
# MARKET DATA
# ------------------------------------------------------------------------------
def upsert_market_data(df: pd.DataFrame, table: str = "market_data"):
    """Upsert d'un DataFrame OHLCV (colonnes: symbol, date, open, high, low, close, volume)."""
    if df.empty:
        return
    client = get_client()
    records = df.copy()
    records["date"] = records["date"].astype(str)

    # records.where(...).to_dict() ne convertit pas toujours NaN -> None de façon
    # fiable (le float nan peut persister). On passe par une vraie sérialisation
    # JSON (to_json force NaN -> null), puis on recharge en objets Python natifs.
    import json
    payload = json.loads(records.to_json(orient="records"))

    # Supabase REST limite la taille des batchs -> on chunke par 500 lignes
    chunk_size = 500
    for i in range(0, len(payload), chunk_size):
        chunk = payload[i:i + chunk_size]
        client.table(table).upsert(chunk, on_conflict="symbol,date").execute()


def fetch_market_data(tickers: list[str], table: str = "market_data") -> pd.DataFrame:
    client = get_client()
    res = client.table(table).select("*").in_("symbol", tickers).execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(["symbol", "date"])
    return df


# ------------------------------------------------------------------------------
# FONDAMENTAUX (avec TTL 7 jours, logique portee depuis sync_fonda_alphavantage)
# ------------------------------------------------------------------------------
def fetch_fonda_data(tickers: list[str]) -> pd.DataFrame:
    client = get_client()
    res = client.table("fonda_data").select("*").in_("symbol", tickers).execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        df["last_updated"] = pd.to_datetime(df["last_updated"]).dt.date
    return df


def tickers_a_rafraichir(tickers: list[str], fonda_df: pd.DataFrame, ttl_jours: int = 7) -> list[str]:
    """Retourne la liste des tickers absents ou perimes (> ttl_jours)."""
    limite = date.today() - timedelta(days=ttl_jours)
    a_jour = set()
    if not fonda_df.empty:
        a_jour = set(fonda_df[fonda_df["last_updated"] >= limite]["symbol"])
    return [t for t in tickers if t not in a_jour]


def upsert_fonda_data(records: list[dict]):
    """records: liste de dicts {symbol, roe, ev_ebitda, debt_eq, margin, last_updated}."""
    if not records:
        return
    client = get_client()
    client.table("fonda_data").upsert(records, on_conflict="symbol").execute()


# ------------------------------------------------------------------------------
# RATINGS S&P (table statique)
# ------------------------------------------------------------------------------
def fetch_ratings() -> pd.DataFrame:
    client = get_client()
    res = client.table("ratings_sp").select("*").execute()
    return pd.DataFrame(res.data)


# ------------------------------------------------------------------------------
# ALTMAN Z-SCORE (avec TTL 7 jours, même logique que fonda_data)
# ------------------------------------------------------------------------------
def fetch_zscore_data(tickers: list[str]) -> pd.DataFrame:
    client = get_client()
    res = client.table("zscore_data").select("*").in_("symbol", tickers).execute()
    df = pd.DataFrame(res.data)
    if not df.empty:
        df["last_updated"] = pd.to_datetime(df["last_updated"]).dt.date
    return df


def tickers_a_rafraichir_zscore(tickers: list[str], zscore_df: pd.DataFrame, ttl_jours: int = 7) -> list[str]:
    limite = date.today() - timedelta(days=ttl_jours)
    a_jour = set()
    if not zscore_df.empty:
        a_jour = set(zscore_df[zscore_df["last_updated"] >= limite]["symbol"])
    return [t for t in tickers if t not in a_jour]


def upsert_zscore_data(records: list[dict]):
    """records: liste de dicts {symbol, z_score, last_updated}."""
    if not records:
        return
    client = get_client()
    client.table("zscore_data").upsert(records, on_conflict="symbol").execute()


# ------------------------------------------------------------------------------
# SPREADS DE CREDIT FRED (historique HY/IG, persisté)
# ------------------------------------------------------------------------------
def fetch_credit_spreads(serie_id: str, limit: int = 260) -> pd.DataFrame:
    """serie_id : 'BAMLH0A0HYM2' (HY) ou 'BAMLC0A0CM' (IG)."""
    client = get_client()
    res = (
        client.table("credit_spreads")
        .select("*")
        .eq("serie_id", serie_id)
        .order("date", desc=True)
        .limit(limit)
        .execute()
    )
    df = pd.DataFrame(res.data)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date")
    return df


def upsert_credit_spreads(records: list[dict]):
    """records: liste de dicts {serie_id, date, valeur}."""
    if not records:
        return
    client = get_client()
    chunk_size = 500
    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        client.table("credit_spreads").upsert(chunk, on_conflict="serie_id,date").execute()


def last_credit_spread_date(serie_id: str):
    client = get_client()
    res = (
        client.table("credit_spreads")
        .select("date")
        .eq("serie_id", serie_id)
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    if res.data:
        return pd.to_datetime(res.data[0]["date"]).date()
    return None
