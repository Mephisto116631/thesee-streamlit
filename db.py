# db.py
# ==============================================================================
# COUCHE DE PERSISTANCE — SUPABASE (remplace global_data.py / DuckDB)
# ==============================================================================
import os
import pandas as pd
from datetime import date, timedelta
from supabase import create_client, Client


def _get_secret(key: str, default: str = "") -> str:
    """Lit un secret dans les variables d'environnement (secrets GitHub Actions, ou export local)."""
    return os.environ.get(key, default)


SUPABASE_URL = _get_secret("SUPABASE_URL")
SUPABASE_KEY = _get_secret("SUPABASE_KEY")

_CLIENT = None


def get_client() -> Client:
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_KEY manquants. "
            "Définis-les dans l'environnement (secrets GitHub Actions, ou export local)."
        )
    _CLIENT = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _CLIENT


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


PAGE_SIZE = 1000      # plafond PostgREST par défaut (max-rows) : au-delà, Supabase tronque en silence
TICKER_BATCH = 50     # limite la longueur de l'URL du filtre `in.(...)`


def _select_all(query_builder_factory) -> list[dict]:
    """Lit TOUTES les lignes d'une requête en paginant par blocs de PAGE_SIZE.

    Sans pagination, Supabase renvoie au plus 1000 lignes : sur ~500 tickers x
    1500 jours, on ne lisait qu'une infime partie de market_data, ce qui faisait
    croire au pipeline qu'il manquait des tickers -> re-téléchargement complet.
    """
    rows, start = [], 0
    while True:
        res = query_builder_factory().range(start, start + PAGE_SIZE - 1).execute()
        batch = res.data or []
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        start += PAGE_SIZE


def fetch_market_data(tickers: list[str], table: str = "market_data", since=None) -> pd.DataFrame:
    """Lit l'OHLCV des tickers (paginé). `since` (date/str) limite l'historique lu."""
    client = get_client()
    rows = []
    for i in range(0, len(tickers), TICKER_BATCH):
        lot = tickers[i:i + TICKER_BATCH]

        def q(lot=lot):
            b = client.table(table).select("*").in_("symbol", lot)
            if since is not None:
                b = b.gte("date", str(since))
            return b.order("symbol").order("date")

        rows.extend(_select_all(q))
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values(["symbol", "date"])
    return df


def last_dates_by_symbol(table: str = "market_data") -> dict:
    """{symbol: dernière date en base}, via la vue SQL `<table>_last` (1 ligne par ticker)."""
    client = get_client()
    rows = _select_all(lambda: client.table(f"{table}_last").select("symbol,last_date").order("symbol"))
    return {r["symbol"]: pd.to_datetime(r["last_date"]).date() for r in rows if r.get("last_date")}


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


# ------------------------------------------------------------------------------
# TABLES "PRÊTES À AFFICHER" (écrites par le cron, lues par l'APK)
# ------------------------------------------------------------------------------
def upsert_rows(table: str, records: list[dict], on_conflict: str, chunk_size: int = 500):
    """Upsert générique, par paquets. `records` doit déjà être JSON-sérialisable."""
    if not records:
        return
    client = get_client()
    for i in range(0, len(records), chunk_size):
        client.table(table).upsert(records[i:i + chunk_size], on_conflict=on_conflict).execute()


def delete_in(table: str, column: str, valeurs: list[str]):
    """Supprime les lignes dont `column` est dans `valeurs` (par paquets, URL courte).
    Le choix des lignes à retirer, et ses garde-fous, se font chez l'appelant (publish.titres_a_retirer)."""
    if not valeurs:
        return
    client = get_client()
    for i in range(0, len(valeurs), TICKER_BATCH):
        client.table(table).delete().in_(column, valeurs[i:i + TICKER_BATCH]).execute()


_LOG_ID: int | None = None  # passage en cours (pour progression())


def progression(pct: int, etape: str):
    """Note l'avancement du passage en cours (barre de progression de l'appli). Ne bloque jamais."""
    if _LOG_ID is None:
        return
    try:
        get_client().table("sync_log").update({"progression": int(max(0, min(100, pct))), "etape": etape[:120]}) \
            .eq("id", _LOG_ID).execute()
    except Exception as e:
        print(f"[DB][WARN] progression non enregistrée : {e}")


def sync_log_start() -> int | None:
    global _LOG_ID
    try:
        res = get_client().table("sync_log").insert({"status": "running", "progression": 0, "etape": "Démarrage"}).execute()
        _LOG_ID = res.data[0]["id"] if res.data else None
        return _LOG_ID
    except Exception as e:  # la table peut ne pas encore exister : ne bloque pas la sync
        print(f"[DB][WARN] sync_log indisponible : {e}")
        return None


STATUTS_TERMINES = ("success", "partiel")   # « partiel » : publié, mais une étape non bloquante a échoué


def sync_log_end(log_id: int | None, status: str, message: str = "", n_tickers: int = 0):
    if log_id is None:
        return
    termine = status in STATUTS_TERMINES
    try:
        get_client().table("sync_log").update({
            "status": status,
            "progression": 100 if termine else None,
            "etape": ("Terminé" if status == "success" else "Terminé avec avertissements") if termine else "Erreur",
            "message": message[:2000],
            "n_tickers": n_tickers,
            "finished_at": pd.Timestamp.now(tz="UTC").isoformat(),
        }).eq("id", log_id).execute()
    except Exception as e:
        print(f"[DB][WARN] sync_log non mis à jour : {e}")
