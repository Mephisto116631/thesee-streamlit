# fred.py
# ==============================================================================
# SPREADS DE CRÉDIT RÉELS — Federal Reserve Economic Data (FRED)
# Séries : ICE BofA High Yield (BAMLH0A0HYM2) et Investment Grade (BAMLC0A0CM)
# ==============================================================================
import requests
import pandas as pd

import db

SERIE_HY = "BAMLH0A0HYM2"  # ICE BofA US High Yield Index Option-Adjusted Spread
SERIE_IG = "BAMLC0A0CM"    # ICE BofA US Corporate Index Option-Adjusted Spread (proxy IG)
SERIE_TAUX_3M = "DGS3MO"   # Bons du Trésor US à 3 mois, marché secondaire (% par an) : taux sans risque

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


def sync_credit_spread(serie_id: str) -> pd.DataFrame:
    """
    Synchronise une série FRED vers Supabase (table credit_spreads).
    Ne télécharge que les jours postérieurs à la dernière date en base.
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
        print(f"[FRED][WARN] Erreur FRED sur {serie_id} : {e}")
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


TAUX_MIN, TAUX_MAX = -0.01, 0.20     # bornes de plausibilité (docs/METHODE.md § 2.1)
TAUX_AGE_MAX_JOURS = 15


def choisir_taux(serie: pd.DataFrame, aujourdhui=None) -> tuple[float, str] | None:
    """Dernière valeur plausible et récente d'une série de taux FRED [date, valeur en %] -> (fraction, date ISO).
    None si la série est vide, trop ancienne ou hors bornes : l'appelant prend alors la valeur de repli."""
    if serie is None or serie.empty:
        return None
    s = serie.dropna(subset=["valeur"]).sort_values("date")
    if s.empty:
        return None
    der = s.iloc[-1]
    date_ = pd.Timestamp(der["date"])
    aujourdhui = pd.Timestamp(aujourdhui) if aujourdhui is not None else pd.Timestamp.today()
    taux = float(der["valeur"]) / 100
    if not (TAUX_MIN <= taux <= TAUX_MAX) or (aujourdhui - date_).days > TAUX_AGE_MAX_JOURS:
        return None
    return taux, str(date_.date())


def taux_sans_risque() -> tuple[float, str] | None:
    """Taux sans risque du jour (docs/METHODE.md § 2.1) : bons du Trésor US à 3 mois, FRED DGS3MO.
    (taux en fraction, date) ; None si FRED est indisponible ou la valeur non plausible."""
    debut = str((pd.Timestamp.today() - pd.Timedelta(days=40)).date())
    return choisir_taux(_fetch_fred_serie(SERIE_TAUX_3M, start_date=debut))
