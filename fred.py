# fred.py
# ==============================================================================
# SPREADS DE CRÉDIT RÉELS — Federal Reserve Economic Data (FRED)
# Séries : ICE BofA High Yield (BAMLH0A0HYM2) et Investment Grade (BAMLC0A0CM)
# ==============================================================================
import requests
import pandas as pd
import streamlit as st

import db

SERIE_HY = "BAMLH0A0HYM2"  # ICE BofA US High Yield Index Option-Adjusted Spread
SERIE_IG = "BAMLC0A0CM"    # ICE BofA US Corporate Index Option-Adjusted Spread (proxy IG)

FRED_API_KEY = db._get_secret("FRED_API_KEY")
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


def _fetch_fred_serie(serie_id: str, start_date: str = "2015-01-01") -> pd.DataFrame:
    """Récupère une série FRED complète depuis start_date. Retourne [date, valeur]."""
    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY manquante dans les secrets.")

    params = {
        "series_id": serie_id,
        "api_key": FRED_API_KEY,
        "file_type": "json",
        "observation_start": start_date,
    }
    resp = requests.get(FRED_BASE_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    obs = data.get("observations", [])
    df = pd.DataFrame(obs)
    if df.empty:
        return df

    df = df[["date", "value"]].rename(columns={"value": "valeur"})
    df["valeur"] = pd.to_numeric(df["valeur"], errors="coerce")  # FRED renvoie "." pour les valeurs manquantes
    df = df.dropna(subset=["valeur"])
    df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data(ttl=86400, show_spinner=False)
def sync_credit_spread(serie_id: str) -> pd.DataFrame:
    """
    Synchronise une série FRED vers Supabase (table credit_spreads).
    TTL 24h en cache Streamlit — les spreads bougent quotidiennement max,
    pas besoin de re-fetch à chaque rerun de session.
    """
    derniere_date_db = db.last_credit_spread_date(serie_id)

    if derniere_date_db is not None:
        aujourdhui = pd.Timestamp.today().date()
        if (aujourdhui - derniere_date_db).days < 1:
            # Déjà à jour (mise à jour FRED quotidienne côté source) -> on lit juste Supabase
            return db.fetch_credit_spreads(serie_id)
        start = str(derniere_date_db)
    else:
        start = "2015-01-01"

    try:
        df_fresh = _fetch_fred_serie(serie_id, start_date=start)
    except Exception as e:
        st.warning(f"Erreur FRED sur {serie_id} : {e}")
        return db.fetch_credit_spreads(serie_id)

    if not df_fresh.empty:
        records = [
            {"serie_id": serie_id, "date": str(row["date"].date()), "valeur": row["valeur"]}
            for _, row in df_fresh.iterrows()
        ]
        db.upsert_credit_spreads(records)

    return db.fetch_credit_spreads(serie_id)


def get_spreads_hy_ig() -> dict:
    """
    Point d'entrée unique pour la page Crédit & Bilan.
    Retourne {"hy": df, "ig": df, "hy_actuel": float, "ig_actuel": float}.
    """
    if not FRED_API_KEY:
        return {"hy": pd.DataFrame(), "ig": pd.DataFrame(), "hy_actuel": None, "ig_actuel": None}

    df_hy = sync_credit_spread(SERIE_HY)
    df_ig = sync_credit_spread(SERIE_IG)

    hy_actuel = df_hy["valeur"].iloc[-1] * 100 if not df_hy.empty else None  # FRED renvoie en %, converti en pb
    ig_actuel = df_ig["valeur"].iloc[-1] * 100 if not df_ig.empty else None

    return {"hy": df_hy, "ig": df_ig, "hy_actuel": hy_actuel, "ig_actuel": ig_actuel}
