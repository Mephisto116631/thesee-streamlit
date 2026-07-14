# db.py
# ==============================================================================
# COUCHE DE PERSISTANCE — SUPABASE (remplace global_data.py / DuckDB)
# ==============================================================================
import os
import functools
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


def _safe_read(default_factory):
    """
    Decorateur pour les fonctions de LECTURE Supabase (fetch_*) : si Supabase
    est injoignable (timeout, panne, config manquante...), on affiche un
    avertissement et on retourne une valeur par defaut (DataFrame vide en
    general) plutot que de laisser planter toute la page Streamlit avec une
    stack trace brute.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print(f"[Supabase] Erreur lecture dans {func.__name__} : {e}")
                st.warning(
                    f"⚠️ Connexion à la base de données indisponible ({func.__name__}). "
                    "Certaines données peuvent être manquantes ou obsolètes.",
                    icon="⚠️",
                )
                return default_factory()
        return wrapper
    return decorator


def _safe_write(func):
    """
    Decorateur pour les fonctions d'ECRITURE Supabase (upsert_*) : en cas
    d'echec on ne peut pas simuler un succes, mais on evite de planter la
    page. Les donnees fraiches restent utilisables en memoire pour la session
    en cours, elles ne seront simplement pas persistees.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f"[Supabase] Erreur écriture dans {func.__name__} : {e}")
            st.warning(
                f"⚠️ Écriture en base de données impossible ({func.__name__}) : "
                "les nouvelles données ne seront pas sauvegardées pour la "
                "prochaine visite, mais restent disponibles pour cette session.",
                icon="⚠️",
            )
            return None
    return wrapper


# ------------------------------------------------------------------------------
# MARKET DATA
# ------------------------------------------------------------------------------
@_safe_write
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


@_safe_read(lambda: pd.DataFrame())
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
@_safe_read(lambda: pd.DataFrame())
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


@_safe_write
def upsert_fonda_data(records: list[dict]):
    """records: liste de dicts {symbol, roe, ev_ebitda, debt_eq, margin, last_updated}."""
    if not records:
        return
    client = get_client()
    client.table("fonda_data").upsert(records, on_conflict="symbol").execute()


# ------------------------------------------------------------------------------
# RATINGS S&P (table statique)
# ------------------------------------------------------------------------------
@_safe_read(lambda: pd.DataFrame())
def fetch_ratings() -> pd.DataFrame:
    client = get_client()
    res = client.table("ratings_sp").select("*").execute()
    return pd.DataFrame(res.data)
