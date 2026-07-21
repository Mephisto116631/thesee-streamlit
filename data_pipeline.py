# data_pipeline.py
# ==============================================================================
# PIPELINE ETL — Yahoo Finance + Alpha Vantage -> Supabase, cache Streamlit
# ==============================================================================
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
    data = data[["symbol", "date", "open", "high", "low", "close", "volume"]]

    # Supabase: la colonne 'volume' est de type bigint -> aucune virgule tolérée.
    data["volume"] = pd.to_numeric(data["volume"], errors="coerce").fillna(0).astype("int64")
    for col in ["open", "high", "low", "close"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")

    return data


@st.cache_data(ttl=3600, show_spinner=False)
def sync_market_data(tickers: tuple[str, ...]) -> pd.DataFrame:
    """
    On tente d'abord Supabase. Si les donnees du jour sont absentes pour au
    moins un ticker, on retelecharge tout le lot Yahoo et on upsert.
    Fonctionne aussi bien pour la liste 'core' que pour un univers élargi
    (S&P 500 + Nasdaq 100 + ETFs) — c'est juste une liste de tickers en entrée.
    """
    tickers = list(tickers)
    df_db = db.fetch_market_data(tickers)

    aujourdhui = pd.Timestamp.today().normalize()
    tickers_en_db = set(df_db["symbol"].unique()) if not df_db.empty else set()
    tickers_manquants = set(tickers) - tickers_en_db

    a_jour = (
        not df_db.empty
        and not tickers_manquants
        and df_db.groupby("symbol")["date"].max().min() >= aujourdhui - pd.Timedelta(days=3)
    )

    if a_jour:
        return df_db

    # Téléchargement par lots pour rester raisonnable sur les univers larges (~600 tickers)
    batch_size = 100
    frames = []
    total_batches = (len(tickers) + batch_size - 1) // batch_size
    progress = st.progress(0, text="Téléchargement des prix (Yahoo Finance)...") if total_batches > 1 else None

    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            frames.append(_telecharger_yahoo(batch))
        except Exception as e:
            st.warning(f"Erreur Yahoo Finance sur le lot {batch[:3]}... : {e}")
        if progress:
            progress.progress(min(1.0, (i + batch_size) / len(tickers)),
                               text=f"Téléchargement des prix : {min(i + batch_size, len(tickers))}/{len(tickers)} tickers")

    if progress:
        progress.empty()

    if not frames:
        return df_db  # rien de neuf, on retombe sur ce qu'on a

    df_fresh = pd.concat(frames, ignore_index=True)
    db.upsert_market_data(df_fresh)
    df_fresh["date"] = pd.to_datetime(df_fresh["date"])
    return df_fresh


@st.cache_data(ttl=3600, show_spinner=False)
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
# 2. FONDAMENTAUX (Alpha Vantage OVERVIEW -> Supabase, TTL 7 jours)
#    Reste limité à la liste "core" suivie activement (pas l'univers élargi)
#    pour respecter le rate-limit Alpha Vantage (5 req/min plan gratuit).
# ------------------------------------------------------------------------------
def _safe_cast(data: dict, key: str) -> float:
    v = data.get(key, "0")
    return float(v) if v not in ["None", "-", "", None] else 0.0


@st.cache_data(ttl=3600, show_spinner=False)
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

    total = len(a_rafraichir)
    progress_bar = st.progress(0, text=f"Fondamentaux : 0/{total} tickers traités")

    nouveaux_records = []
    for i, t in enumerate(a_rafraichir):
        progress_bar.progress(
            i / total,
            text=f"Fondamentaux : {i}/{total} tickers traités — récupération de {t}...",
        )
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

    progress_bar.progress(1.0, text=f"Fondamentaux : {total}/{total} tickers traités")
    progress_bar.empty()
    if nouveaux_records:
        st.toast(f"{len(nouveaux_records)} ticker(s) mis à jour (fondamentaux)", icon="✓")
        db.upsert_fonda_data(nouveaux_records)

    return db.fetch_fonda_data(tickers)


# ------------------------------------------------------------------------------
# 2bis. ALTMAN Z-SCORE RÉEL (Alpha Vantage BALANCE_SHEET + INCOME_STATEMENT)
#    Formule complète (entreprises publiques, non-manufacturières exclues) :
#    Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
#    A = Fonds de roulement / Total actifs
#    B = Bénéfices non répartis / Total actifs
#    C = EBIT / Total actifs
#    D = Capitalisation boursière / Total passifs
#    E = Chiffre d'affaires / Total actifs
# ------------------------------------------------------------------------------
def _safe_get(d: dict, key: str, default: float = 0.0) -> float:
    v = d.get(key)
    if v in (None, "None", "-", ""):
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@st.cache_data(ttl=3600, show_spinner=False)
def sync_altman_zscore(tickers: tuple[str, ...], prix_actuels: dict) -> pd.DataFrame:
    """
    prix_actuels : dict {symbol: dernier_prix} pour calculer la capitalisation
                   boursière (approximation : prix x nombre d'actions du bilan).
    Résultat stocké dans Supabase (table zscore_data), TTL 7 jours comme fonda_data.
    """
    tickers = list(tickers)
    zscore_df = db.fetch_zscore_data(tickers)
    a_rafraichir = db.tickers_a_rafraichir_zscore(tickers, zscore_df, ttl_jours=7)

    if not a_rafraichir:
        return zscore_df

    if not CLE_ALPHA_VANTAGE:
        st.warning(f"Clé Alpha Vantage absente : Z-Score non calculé pour {len(a_rafraichir)} ticker(s).")
        return zscore_df

    total = len(a_rafraichir)
    progress_bar = st.progress(0, text=f"Z-Score Altman : 0/{total} tickers traités")
    nouveaux_records = []

    for i, t in enumerate(a_rafraichir):
        progress_bar.progress(i / total, text=f"Z-Score Altman : {i}/{total} — {t}...")
        try:
            url_bs = f"https://www.alphavantage.co/query?function=BALANCE_SHEET&symbol={t}&apikey={CLE_ALPHA_VANTAGE}"
            bs = requests.get(url_bs, timeout=10).json()
            time.sleep(13)

            url_is = f"https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol={t}&apikey={CLE_ALPHA_VANTAGE}"
            inc = requests.get(url_is, timeout=10).json()
            time.sleep(13)

            bs_annual = bs.get("annualReports", [{}])
            inc_annual = inc.get("annualReports", [{}])
            if not bs_annual or not inc_annual:
                continue

            bs0, inc0 = bs_annual[0], inc_annual[0]

            total_assets = _safe_get(bs0, "totalAssets")
            total_liabilities = _safe_get(bs0, "totalLiabilities")
            current_assets = _safe_get(bs0, "totalCurrentAssets")
            current_liabilities = _safe_get(bs0, "totalCurrentLiabilities")
            retained_earnings = _safe_get(bs0, "retainedEarnings")
            shares_out = _safe_get(bs0, "commonStockSharesOutstanding")

            ebit = _safe_get(inc0, "ebit")
            revenue = _safe_get(inc0, "totalRevenue")

            if total_assets <= 0:
                continue

            prix = prix_actuels.get(t, 0.0)
            market_cap = prix * shares_out

            A = (current_assets - current_liabilities) / total_assets
            B = retained_earnings / total_assets
            C = ebit / total_assets
            D = market_cap / total_liabilities if total_liabilities > 0 else 0.0
            E = revenue / total_assets

            z = 1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E

            nouveaux_records.append({
                "symbol": t,
                "z_score": round(z, 3),
                "last_updated": str(pd.Timestamp.today().date()),
            })
        except Exception as e:
            st.warning(f"Erreur Z-Score sur {t} : {e}")

    progress_bar.progress(1.0, text=f"Z-Score Altman : {total}/{total} tickers traités")
    progress_bar.empty()
    if nouveaux_records:
        st.toast(f"{len(nouveaux_records)} Z-Score(s) recalculés", icon="✓")
        db.upsert_zscore_data(nouveaux_records)

    return db.fetch_zscore_data(tickers)


# ------------------------------------------------------------------------------
# 3. FEATURE ENGINEERING — vix_regime et rsi_rank_sec désormais réels
# ------------------------------------------------------------------------------
def _calc_vix_regime(vix_close: float) -> int:
    """0 = calme (<15), 1 = normal (15-25), 2 = stress (>25)."""
    if pd.isna(vix_close):
        return 1
    if vix_close < 15:
        return 0
    if vix_close <= 25:
        return 1
    return 2


def build_features(mkt_df: pd.DataFrame, macro_df: pd.DataFrame = None, dict_secteurs: dict = None) -> pd.DataFrame:
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
        parts.append(grp)

    df = pd.concat(parts) if parts else pd.DataFrame()
    if df.empty:
        return df

    # --- vix_regime réel : jointure sur la date avec le niveau de clôture du VIX ---
    if macro_df is not None and not macro_df.empty and "^VIX" in macro_df["symbol"].unique():
        vix = macro_df[macro_df["symbol"] == "^VIX"][["date", "close"]].rename(columns={"close": "vix_close"})
        df = df.merge(vix, on="date", how="left")
        df["vix_regime"] = df["vix_close"].apply(_calc_vix_regime)
        df = df.drop(columns=["vix_close"])
    else:
        df["vix_regime"] = 1  # régime "normal" par défaut si le VIX est indisponible

    # --- rsi_rank_sec réel : rang percentile du RSI au sein du secteur, par date ---
    if dict_secteurs:
        symbol_to_secteur = {}
        for secteur, tickers_sec in dict_secteurs.items():
            for t in tickers_sec:
                symbol_to_secteur[t] = secteur
        df["secteur_tmp"] = df["symbol"].map(symbol_to_secteur).fillna("Autre")
        df["rsi_rank_sec"] = df.groupby(["date", "secteur_tmp"])["rsi_14"].rank(pct=True)
        df = df.drop(columns=["secteur_tmp"])
        df["rsi_rank_sec"] = df["rsi_rank_sec"].fillna(0.5)
    else:
        df["rsi_rank_sec"] = 0.5

    return df.dropna(subset=["target_next_return"])


# ------------------------------------------------------------------------------
# 4. MODELE XGBOOST — accuracy dynamique via split train/test temporel
# ------------------------------------------------------------------------------
@st.cache_resource(show_spinner="Entraînement du modèle IA...")
def train_ia(_df_hash: str, df: pd.DataFrame) -> dict:
    """
    _df_hash : cle de cache stable (nombre de lignes + derniere date),
               car st.cache_resource ne hash pas bien les gros DataFrame.
    Split train/test temporel (80/20, pas de shuffle) pour une accuracy
    représentative — on n'évalue jamais sur du passé utilisé à l'entraînement.
    """
    from xgboost import XGBClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import accuracy_score

    if df.empty:
        return {"model": None, "features": utils.FEATURES_DEFAUT, "accuracy": 0.0}

    feat = utils.FEATURES_DEFAUT
    df_sorted = df.sort_values("date")

    X = df_sorted[feat].values
    y = (df_sorted["target_next_return"] > 0).astype(int).values

    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    imp, scl = SimpleImputer(strategy="median"), StandardScaler()
    X_train_s = scl.fit_transform(imp.fit_transform(X_train))

    model = XGBClassifier(n_estimators=100, max_depth=3, learning_rate=0.05, random_state=42)
    model.fit(X_train_s, y_train)

    accuracy = 50.0  # valeur neutre par défaut si pas assez de données de test
    if len(X_test) > 0:
        X_test_s = scl.transform(imp.transform(X_test))
        y_pred = model.predict(X_test_s)
        accuracy = round(accuracy_score(y_test, y_pred) * 100, 1)

    # Ré-entraîne sur l'ensemble des données pour l'usage en production (audit, etc.)
    # tout en gardant l'accuracy mesurée honnêtement sur le split test ci-dessus.
    X_full_s = scl.fit_transform(imp.fit_transform(X))
    model.fit(X_full_s, y)

    return {"model": model, "imputer": imp, "scaler": scl, "features": feat, "accuracy": accuracy}


# ------------------------------------------------------------------------------
# 5. POINT D'ENTREE UNIQUE — a appeler depuis chaque page Streamlit
# ------------------------------------------------------------------------------
def get_all_data(univers_etendu: list[str] = None):
    """
    Retourne un dict avec toutes les donnees necessaires aux pages.
    univers_etendu : si fourni, les PRIX (Yahoo) sont synchronisés pour cette
                      liste élargie. Les FONDAMENTAUX restent limités à
                      utils.actifs_sp500 (rate-limit Alpha Vantage).
    """
    tickers_core = tuple(utils.actifs_sp500)
    macro = tuple(utils.actifs_macro)
    tickers_prix = tuple(univers_etendu) if univers_etendu else tickers_core

    etape = st.empty()

    etape.info("Étape 1/5 — Synchronisation des données de marché (Yahoo Finance)...")
    market_data_raw = sync_market_data(tickers_prix)

    etape.info("Étape 2/5 — Synchronisation des données macro (VIX, SPY)...")
    macro_data_raw = sync_macro_data(macro)

    etape.info("Étape 3/5 — Vérification des fondamentaux (Alpha Vantage)...")
    fonda_data_clean = sync_fonda_data(tickers_core)

    etape.info("Étape 4/5 — Calcul du Z-Score Altman...")
    market_core = market_data_raw[market_data_raw["symbol"].isin(tickers_core)] if not market_data_raw.empty else market_data_raw
    prix_actuels = {}
    if not market_core.empty:
        derniers = market_core.sort_values("date").groupby("symbol").last()
        prix_actuels = derniers["close"].to_dict()
    zscore_df = sync_altman_zscore(tickers_core, prix_actuels)

    etape.info("Étape 5/5 — Calcul des indicateurs et entraînement du modèle IA...")
    market_data_clean = build_features(market_data_raw, macro_data_raw, utils.dict_secteurs)

    cache_key = f"{len(market_data_clean)}_{market_data_clean['date'].max() if not market_data_clean.empty else 'empty'}"
    model_result = train_ia(cache_key, market_data_clean)

    etape.empty()

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
        "zscore_df": zscore_df,
        "model_result": model_result,
        "model_ia": model_result["model"],
        "importance_df": importance_df,
        "ratings_df": ratings_df,
    }
