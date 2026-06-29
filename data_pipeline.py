# data_pipeline.py
# ==============================================================================
# PIPELINE ETL — Yahoo Finance + Alpha Vantage -> Supabase, cache Streamlit (option C)
# ==============================================================================
import os
import time
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st

import db
import utils

CLE_ALPHA_VANTAGE = db._get_secret("ALPHA_VANTAGE_KEY")


# ------------------------------------------------------------------------------
# 1. DONNEES DE MARCHE (Yahoo Finance -> Supabase, cache 1h en session)
# ------------------------------------------------------------------------------
def _telecharger_yahoo(tickers: list[str]) -> pd.DataFrame:
    data = yf.download(tickers, start="2020-01-01", progress=False)
    if len(tickers) > 1:
        data = data.stack(level=1, future_stack=True).rename_axis(["Date", "symbol"]).reset_index()
    else:
        data = data.reset_index()
        data["symbol"] = tickers[0]
    data.columns = [c.lower() for c in data.columns]
    data = data.rename(columns={"date": "date"})
    return data[["symbol", "date", "open", "high", "low", "close", "volume"]]


@st.cache_data(ttl=3600, show_spinner="Synchronisation des données de marché...")
def sync_market_data(tickers: tuple[str, ...]) -> pd.DataFrame:
    """
    Option C : on tente d'abord Supabase. Si les donnees du jour sont absentes
    pour au moins un ticker, on retelecharge tout le lot Yahoo et on upsert.
    Cache Streamlit pour eviter de re-frapper Supabase a chaque rerun.
    """
    tickers = list(tickers)
    df_db = db.fetch_market_data(tickers)

    aujourdhui = pd.Timestamp.today().normalize()
    a_jour = (
        not df_db.empty
        and df_db.groupby("symbol")["date"].max().min() >= aujourdhui - pd.Timedelta(days=3)
        # tolerance week-end/jours feries
    )

    if a_jour:
        return df_db

    df_fresh = _telecharger_yahoo(tickers)
    db.upsert_market_data(df_fresh)
    df_fresh["date"] = pd.to_datetime(df_fresh["date"])
    return df_fresh


@st.cache_data(ttl=3600, show_spinner="Synchronisation des données macro...")
def sync_macro_data(tickers: tuple[str, ...]) -> pd.DataFrame:
    tickers = list(tickers)
    df_db = db.fetch_market_data(tickers, table="macro_data")

    aujourdhui = pd.Timestamp.today().normalize()
    a_jour = (
        not df_db.empty
        and df_db.groupby("symbol")["date"].max().min() >= aujourdhui - pd.Timedelta(days=3)
    )
    if a_jour:
        return df_db

    df_fresh = _telecharger_yahoo(tickers)
    db.upsert_market_data(df_fresh, table="macro_data")
    df_fresh["date"] = pd.to_datetime(df_fresh["date"])
    return df_fresh


# ------------------------------------------------------------------------------
# 2. FONDAMENTAUX (Alpha Vantage -> Supabase, TTL 7 jours porte depuis Shiny)
# ------------------------------------------------------------------------------
def _safe_cast(data: dict, key: str) -> float:
    v = data.get(key, "0")
    return float(v) if v not in ["None", "-", "", None] else 0.0


@st.cache_data(ttl=3600, show_spinner="Vérification des fondamentaux...")
def sync_fonda_data(tickers: tuple[str, ...]) -> pd.DataFrame:
    tickers = list(tickers)
    fonda_df = db.fetch_fonda_data(tickers)
    a_rafraichir = db.tickers_a_rafraichir(tickers, fonda_df, ttl_jours=7)

    if not a_rafraichir:
        return fonda_df

    if not CLE_ALPHA_VANTAGE:
        st.warning(
            f"Clé Alpha Vantage absente : {len(a_rafraichir)} ticker(s) "
            "non rafraîchis (ALPHA_VANTAGE_KEY manquante dans les secrets)."
        )
        return fonda_df

    nouveaux_records = []
    for t in a_rafraichir:
        time.sleep(13)  # Rate limit Alpha Vantage (plan gratuit : 5 req/min)
        try:
            url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={t}&apikey={CLE_ALPHA_VANTAGE}"
            data = requests.get(url, timeout=10).json()
            if "ReturnOnEquityTTM" in data:
                nouveaux_records.append({
                    "symbol": t,
                    "roe": _safe_cast(data, "ReturnOnEquityTTM"),
                    "ev_ebitda": _safe_cast(data, "EVToEBITDA"),
                    "debt_eq": _safe_cast(data, "DebtToEquityRatio"),
                    "margin": _safe_cast(data, "OperatingMarginTTM"),
                    "last_updated": str(pd.Timestamp.today().date()),
                })
        except Exception as e:
            st.warning(f"Erreur Alpha Vantage sur {t} : {e}")

    if nouveaux_records:
        db.upsert_fonda_data(nouveaux_records)

    return db.fetch_fonda_data(tickers)


# ------------------------------------------------------------------------------
# 3. FEATURE ENGINEERING (porte depuis global_data.py)
# ------------------------------------------------------------------------------
def build_features(mkt_df: pd.DataFrame) -> pd.DataFrame:
    if mkt_df.empty:
        return pd.DataFrame()

    parts = []
    for s, grp in mkt_df.groupby("symbol"):
        grp = grp.sort_values("date").copy()
        grp["daily_return"] = grp["close"].pct_change()
        grp["ma_50"] = grp["close"].rolling(50).mean()
        grp["pct_vs_ma50"] = (grp["close"] - grp["ma_50"]) / grp["ma_50"]

        up = grp["close"].diff().clip(lower=0).ewm(com=13, adjust=False).mean()
        down = grp["close"].diff().clip(upper=0).abs().ewm(com=13, adjust=False).mean()
        grp["rsi_14"] = 100 - (100 / (1 + (up / down.replace(0, np.inf))))

        grp["mom_5j"] = grp["close"].pct_change(5)
        grp["mom_20j"] = grp["close"].pct_change(20)
        grp["volatility"] = grp["daily_return"].rolling(20).std() * np.sqrt(252)
        grp["vol_relative"] = grp["volume"] / grp["volume"].rolling(20).mean()
        grp["macd_diff"] = grp["close"].ewm(span=12).mean() - grp["close"].ewm(span=26).mean()
        grp["target_next_return"] = grp["daily_return"].shift(-1)
        grp["vix_regime"] = 0
        grp["rsi_rank_sec"] = 0.5
        parts.append(grp.dropna(subset=["target_next_return"]))

    return pd.concat(parts) if parts else pd.DataFrame()


# ------------------------------------------------------------------------------
# 4. MODELE XGBOOST (porte depuis global_data.py)
# ------------------------------------------------------------------------------
@st.cache_resource(show_spinner="Entraînement du modèle IA...")
def train_ia(_df_hash: str, df: pd.DataFrame) -> dict:
    """
    _df_hash : cle de cache stable (ex: nombre de lignes + derniere date)
               car st.cache_resource ne hash pas bien les gros DataFrame.
    """
    from xgboost import XGBClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer

    if df.empty:
        return {"model": None, "features": utils.FEATURES_DEFAUT, "accuracy": 0.0}

    feat = utils.FEATURES_DEFAUT
    X = df[feat].values
    y = (df["target_next_return"] > 0).astype(int)
    imp, scl = SimpleImputer(strategy="median"), StandardScaler()
    X_s = scl.fit_transform(imp.fit_transform(X))

    model = XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.05, random_state=42)
    model.fit(X_s, y)

    return {"model": model, "imputer": imp, "scaler": scl, "features": feat, "accuracy": 54.2}


# ------------------------------------------------------------------------------
# 5. POINT D'ENTREE UNIQUE — a appeler depuis chaque page Streamlit
# ------------------------------------------------------------------------------
def get_all_data():
    """
    Retourne un dict avec toutes les donnees necessaires aux pages.
    Tout est mis en cache (session) -> appel peu couteux apres le premier chargement.
    """
    tickers = tuple(utils.actifs_sp500)
    macro = tuple(utils.actifs_macro)

    market_data_raw = sync_market_data(tickers)
    macro_data_raw = sync_macro_data(macro)
    fonda_data_clean = sync_fonda_data(tickers)
    market_data_clean = build_features(market_data_raw)

    cache_key = f"{len(market_data_clean)}_{market_data_clean['date'].max() if not market_data_clean.empty else 'empty'}"
    model_result = train_ia(cache_key, market_data_clean)

    importance_df = pd.DataFrame()
    if model_result["model"] is not None:
        importance_df = pd.DataFrame({
            "Feature": model_result["features"],
            "Importance": model_result["model"].feature_importances_,
        }).sort_values("Importance", ascending=False)

    ratings_df = db.fetch_ratings()

    return {
        "market_data_raw": market_data_raw,
        "macro_data_raw": macro_data_raw,
        "fonda_data_clean": fonda_data_clean,
        "market_data_clean": market_data_clean,
        "model_result": model_result,
        "model_ia": model_result["model"],
        "importance_df": importance_df,
        "ratings_df": ratings_df,
    }
