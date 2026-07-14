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
CLE_FRED = db._get_secret("FRED_API_KEY")


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
    data = data[["symbol", "date", "open", "high", "low", "close", "volume"]]

    # Supabase: la colonne 'volume' est de type bigint -> aucune virgule tolérée.
    # yfinance renvoie parfois du float64 (ex: 59151200.0), ce qui fait planter
    # l'upsert PostgREST (erreur 22P02). On force un cast explicite en int.
    data["volume"] = pd.to_numeric(data["volume"], errors="coerce").fillna(0).astype("int64")
    for col in ["open", "high", "low", "close"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    return data


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

    try:
        df_fresh = _telecharger_yahoo(tickers)
    except Exception as e:
        # Yahoo ET potentiellement Supabase indisponibles en meme temps :
        # on ne laisse jamais planter la page. Si Supabase avait au moins
        # des donnees perimees (df_db non vide), on les utilise en dernier
        # recours plutot que de ne rien afficher du tout.
        print(f"[Yahoo Finance] Erreur de telechargement : {e}")
        if not df_db.empty:
            st.warning(
                "⚠️ Impossible de récupérer les cours à jour (Yahoo Finance "
                "indisponible) : affichage de données de marché potentiellement "
                "obsolètes.",
                icon="⚠️",
            )
            return df_db
        st.error(
            "❌ Aucune donnée de marché disponible : Yahoo Finance et la base "
            "de données sont tous deux indisponibles pour le moment. "
            "Réessaie dans quelques minutes.",
            icon="❌",
        )
        return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume"])

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

    try:
        df_fresh = _telecharger_yahoo(tickers)
    except Exception as e:
        # Meme logique de fallback que sync_market_data : donnees macro moins
        # critiques (utilisees pour vix_regime, qui a deja son propre defaut
        # neutre), donc un simple retour degrade suffit ici sans st.error.
        print(f"[Yahoo Finance] Erreur de telechargement (macro) : {e}")
        if not df_db.empty:
            return df_db
        return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume"])

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
            # On n'affiche jamais l'exception brute a l'utilisateur : certaines
            # erreurs reseau (ex: ConnectionError) incluent l'URL complete de la
            # requete, qui contient la cle API en clair (apikey=...).
            print(f"[Alpha Vantage] Erreur sur {t} : {e}")
            st.warning(f"Erreur Alpha Vantage sur {t} : échec de la requête (voir logs serveur).")

    if nouveaux_records:
        db.upsert_fonda_data(nouveaux_records)

    return db.fetch_fonda_data(tickers)


# ------------------------------------------------------------------------------
# 3. FEATURE ENGINEERING (porte depuis global_data.py)
# ------------------------------------------------------------------------------
def _calc_vix_regime(macro_df: pd.DataFrame) -> pd.DataFrame:
    """
    Regime de marche base sur le niveau du VIX (^VIX), en 3 paliers :
      0 = calme      (VIX < 20)
      1 = stress modere (20 <= VIX < 30)
      2 = stress eleve  (VIX >= 30)
    Seuils usuels de lecture du VIX (20 = moyenne long terme, 30 = zone de crise).
    Retourne un DataFrame [date, vix_regime] pret a etre merge sur la date.
    """
    if macro_df.empty or "^VIX" not in set(macro_df["symbol"]):
        return pd.DataFrame(columns=["date", "vix_regime"])

    vix = macro_df[macro_df["symbol"] == "^VIX"][["date", "close"]].copy()
    # np.select : le premier "default" gere aussi le cas NaN (aucune condition
    # n'est vraie quand close est NaN) -> sans le np.nan explicite ci-dessous,
    # un VIX manquant serait classe a tort en "stress eleve" (2). On force
    # NaN -> NaN, gere ensuite par l'appelant (build_features) avec le meme
    # fallback "calme" (0) que pour une date sans VIX du tout.
    vix["vix_regime"] = np.select(
        [vix["close"] < 20, vix["close"] < 30],
        [0, 1],
        default=np.where(vix["close"].isna(), np.nan, 2),
    )
    return vix[["date", "vix_regime"]]


def build_features(mkt_df: pd.DataFrame, macro_df: pd.DataFrame = None) -> pd.DataFrame:
    if mkt_df.empty:
        return pd.DataFrame()

    if macro_df is None:
        macro_df = pd.DataFrame()
    vix_regime_df = _calc_vix_regime(macro_df)

    parts = []
    for s, grp in mkt_df.groupby("symbol"):
        grp = grp.sort_values("date").copy()
        grp["daily_return"] = grp["close"].pct_change()
        grp["ma_50"] = grp["close"].rolling(50).mean()
        grp["pct_vs_ma50"] = (grp["close"] - grp["ma_50"]) / grp["ma_50"]

        up = grp["close"].diff().clip(lower=0).ewm(com=13, adjust=False).mean()
        down = grp["close"].diff().clip(upper=0).abs().ewm(com=13, adjust=False).mean()
        # Cas up == down == 0 (prix plat) : pas de mouvement -> RSI neutre (50),
        # pas 100 (ce que donnerait 0/inf sans ce garde-fou).
        rs = up / down.replace(0, np.inf)
        grp["rsi_14"] = np.where((up == 0) & (down == 0), 50.0, 100 - (100 / (1 + rs)))

        grp["mom_5j"] = grp["close"].pct_change(5)
        grp["mom_20j"] = grp["close"].pct_change(20)
        grp["volatility"] = grp["daily_return"].rolling(20).std() * np.sqrt(252)
        grp["vol_relative"] = grp["volume"] / grp["volume"].rolling(20).mean()
        grp["macd_diff"] = grp["close"].ewm(span=12).mean() - grp["close"].ewm(span=26).mean()
        grp["target_next_return"] = grp["daily_return"].shift(-1)
        parts.append(grp.dropna(subset=["target_next_return"]))

    result = pd.concat(parts) if parts else pd.DataFrame()
    if result.empty:
        return result

    # vix_regime : jointure sur la date (regime de marche global, identique
    # pour tous les titres a une date donnee). Si le VIX est indisponible pour
    # une date (jour ferie different, donnee manquante), on retombe sur le
    # regime "calme" (0) par defaut plutot que de propager un NaN.
    if not vix_regime_df.empty:
        result = result.merge(vix_regime_df, on="date", how="left")
        result["vix_regime"] = result["vix_regime"].fillna(0).astype(int)
    else:
        result["vix_regime"] = 0

    # rsi_rank_sec : rang percentile du RSI du titre par rapport aux autres
    # titres de son secteur, a la meme date (0 = RSI le plus bas du secteur ce
    # jour-la, 1 = le plus haut). Necessite de connaitre le secteur de chaque
    # symbole -> mapping importe depuis utils.dict_secteurs.
    symbol_to_secteur = {
        sym: secteur for secteur, symbols in utils.dict_secteurs.items() for sym in symbols
    }
    result["secteur"] = result["symbol"].map(symbol_to_secteur)
    result["rsi_rank_sec"] = (
        result.groupby(["date", "secteur"])["rsi_14"].rank(pct=True)
        if result["secteur"].notna().any()
        else 0.5
    )
    # Secteur inconnu (titre absent de dict_secteurs) ou groupe a un seul titre
    # (rank(pct=True) renvoie 1.0 par defaut) -> valeur neutre 0.5.
    result["rsi_rank_sec"] = result["rsi_rank_sec"].fillna(0.5)
    result = result.drop(columns=["secteur"])

    return result


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
    from sklearn.metrics import accuracy_score

    if df.empty:
        return {
            "model": None, "imputer": None, "scaler": None,
            "features": utils.FEATURES_DEFAUT, "accuracy": None,
        }

    feat = utils.FEATURES_DEFAUT

    # Split temporel (pas aleatoire) : le train doit precener le test
    # chronologiquement, sinon on risque une fuite d'information (le modele
    # "voit" indirectement le futur via l'ordre des donnees).
    df_sorted = df.sort_values("date")
    X_sorted = df_sorted[feat].values
    y_sorted = (df_sorted["target_next_return"] > 0).astype(int).values

    if len(df_sorted) < 20:
        # Trop peu de donnees pour un split fiable : on entraine sur tout,
        # mais l'accuracy n'est alors PAS mesurable de façon honnete.
        # accuracy=None (et non 0.0) pour eviter d'afficher un faux "0% de
        # precision" qui laisserait croire que le modele est mauvais alors
        # qu'il n'a simplement pas ete evalue.
        imp, scl = SimpleImputer(strategy="median"), StandardScaler()
        X_s = scl.fit_transform(imp.fit_transform(X_sorted))
        model = XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.05, random_state=42)
        model.fit(X_s, y_sorted)
        return {"model": model, "imputer": imp, "scaler": scl, "features": feat, "accuracy": None}

    split_idx = int(len(X_sorted) * 0.8)
    X_train, X_test = X_sorted[:split_idx], X_sorted[split_idx:]
    y_train, y_test = y_sorted[:split_idx], y_sorted[split_idx:]

    imp, scl = SimpleImputer(strategy="median"), StandardScaler()
    X_train_s = scl.fit_transform(imp.fit_transform(X_train))
    X_test_s = scl.transform(imp.transform(X_test))

    model = XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.05, random_state=42)
    model.fit(X_train_s, y_train)
    accuracy = accuracy_score(y_test, model.predict(X_test_s)) * 100

    # Reentraine sur l'integralite des donnees (train+test) pour le modele final
    # utilise en production (SHAP, predictions), mais l'accuracy affichee reste
    # celle mesuree sur le test set jamais vu par ce modele-la.
    imp_full, scl_full = SimpleImputer(strategy="median"), StandardScaler()
    X_full_s = scl_full.fit_transform(imp_full.fit_transform(X_sorted))
    model_full = XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.05, random_state=42)
    model_full.fit(X_full_s, y_sorted)

    return {
        "model": model_full,
        "imputer": imp_full,
        "scaler": scl_full,
        "features": feat,
        "accuracy": accuracy,
    }


# ------------------------------------------------------------------------------
# 4bis. SPREADS DE CREDIT (FRED — remplace la simulation dans 4_Credit_Bilan.py)
# ------------------------------------------------------------------------------
# Series FRED (ICE BofA) :
#   BAMLH0A0HYM2 : ICE BofA US High Yield Index Option-Adjusted Spread
#   BAMLC0A0CM   : ICE BofA US Corporate (Investment Grade) Index OAS
FRED_SERIES = {"HY": "BAMLH0A0HYM2", "IG": "BAMLC0A0CM"}


@st.cache_data(ttl=3600 * 12, show_spinner="Récupération des spreads de crédit (FRED)...")
def sync_fred_spreads(lookback_days: int = 730) -> pd.DataFrame:
    """
    Retourne un DataFrame avec colonnes : date, HY, IG (spreads en points de base).
    DataFrame vide si la cle FRED est absente ou en cas d'erreur -> l'appelant
    doit gerer ce cas (fallback / avertissement), jamais de donnees inventees ici.
    """
    if not CLE_FRED:
        return pd.DataFrame(columns=["date", "HY", "IG"])

    start = (pd.Timestamp.today() - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    series_frames = {}

    for label, series_id in FRED_SERIES.items():
        try:
            url = (
                "https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={series_id}&api_key={CLE_FRED}&file_type=json"
                f"&observation_start={start}"
            )
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            obs = resp.json().get("observations", [])
            df = pd.DataFrame(obs)[["date", "value"]]
            df["date"] = pd.to_datetime(df["date"])
            # FRED encode les valeurs manquantes par "." (jours feries etc.)
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            # Spread en points de base : FRED donne le OAS en % -> x100
            df["value"] = df["value"] * 100
            series_frames[label] = df.set_index("date")["value"]
        except Exception as e:
            # Meme logique que pour Alpha Vantage : jamais d'exception brute
            # affichee cote utilisateur (l'URL contient la cle FRED en clair).
            print(f"[FRED] Erreur sur la serie {series_id} ({label}) : {e}")
            return pd.DataFrame(columns=["date", "HY", "IG"])

    merged = pd.concat(series_frames, axis=1).dropna(how="all").reset_index()
    merged = merged.rename(columns={"index": "date"})
    return merged.sort_values("date")


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
    market_data_clean = build_features(market_data_raw, macro_data_raw)

    cache_key = f"{len(market_data_clean)}_{market_data_clean['date'].max() if not market_data_clean.empty else 'empty'}"
    model_result = train_ia(cache_key, market_data_clean)

    importance_df = pd.DataFrame()
    if model_result["model"] is not None:
        importance_df = pd.DataFrame({
            "Feature": model_result["features"],
            "Importance": model_result["model"].feature_importances_,
        }).sort_values("Importance", ascending=False)

    ratings_df = db.fetch_ratings()
    fred_spreads = sync_fred_spreads()

    return {
        "market_data_raw": market_data_raw,
        "macro_data_raw": macro_data_raw,
        "fonda_data_clean": fonda_data_clean,
        "market_data_clean": market_data_clean,
        "model_result": model_result,
        "model_ia": model_result["model"],
        "importance_df": importance_df,
        "ratings_df": ratings_df,
        "fred_spreads": fred_spreads,
    }
