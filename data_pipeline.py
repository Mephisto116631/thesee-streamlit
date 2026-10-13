# data_pipeline.py
# ==============================================================================
# PIPELINE ETL — Yahoo Finance + Alpha Vantage -> Supabase, cache Streamlit
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
import universe

CLE_ALPHA_VANTAGE = db._get_secret("ALPHA_VANTAGE_KEY")


def _refresh_alpha_autorise() -> bool:
    """
    Alpha Vantage (plan gratuit) impose ~13 s par appel : rafraîchir 12 tickers
    prend plusieurs minutes. Ce rafraîchissement est donc réservé au CRON
    GitHub Actions (variable THESEE_CRON=1). L'app Streamlit, elle, lit
    toujours ce qui est déjà dans Supabase, même légèrement périmé (> TTL),
    au lieu de bloquer l'utilisateur pendant le chargement de la page.
    """
    return os.environ.get("THESEE_CRON") == "1"


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

    if not a_rafraichir or not _refresh_alpha_autorise():
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
        st.toast(f"{len(nouveaux_records)} ticker(s) mis à jour (fondamentaux)", icon="✅")
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

    if not a_rafraichir or not _refresh_alpha_autorise():
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
        st.toast(f"{len(nouveaux_records)} Z-Score(s) recalculés", icon="✅")
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


def build_features(mkt_df: pd.DataFrame, macro_df: pd.DataFrame = None, dict_secteurs: dict = None,
                    fonda_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    fonda_df : fondamentaux Alpha Vantage (roe, margin, ev_ebitda, debt_eq) par
               symbol. ATTENTION — ce sont des instantanés de la valeur ACTUELLE
               (rafraîchis tous les 7 jours), pas un historique quotidien. Les
               injecter comme features constantes sur toute la période
               historique d'un titre est une approximation : ces ratios changent
               lentement (trimestriel), donc l'erreur introduite reste limitée,
               mais ce n'est PAS la vraie valeur qu'aurait eue le ratio à une
               date passée. À garder en tête si l'edge du modèle semble venir
               principalement de ces colonnes (risque de surestimation légère).
    """
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
        grp["mom_60j"] = grp["close"].pct_change(60)
        # Momentum 12 mois hors dernier mois (évite l'effet retournement court terme)
        grp["mom_12_1"] = grp["close"].shift(21) / grp["close"].shift(252) - 1
        grp["volatility"] = grp["daily_return"].rolling(20).std() * np.sqrt(252)
        grp["vol_relative"] = grp["volume"] / grp["volume"].rolling(20).mean()
        grp["macd_diff"] = grp["close"].ewm(span=12).mean() - grp["close"].ewm(span=26).mean()
        grp["target_next_return"] = grp["daily_return"].shift(-1)
        grp["target_fwd_5j"] = grp["close"].shift(-5) / grp["close"] - 1
        parts.append(grp)

    df = pd.concat(parts) if parts else pd.DataFrame()
    if df.empty:
        return df

    # --- Features en rang cross-sectionnel + cible relative (modèle "relatif") ---
    # Rang percentile par date sur tout l'univers : retire l'effet de marché.
    # target_rel_5j = rendement 5j - médiane du jour (NaN sur les 5 derniers jours).
    for f in utils.CS_BASE:
        df[f + "_cs"] = df.groupby("date")[f].rank(pct=True)
    df["target_rel_5j"] = df["target_fwd_5j"] - df.groupby("date")["target_fwd_5j"].transform("median")

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

    # --- Fondamentaux comme features constantes par titre (voir docstring) ---
    if fonda_df is not None and not fonda_df.empty:
        f = fonda_df[["symbol", "roe", "margin", "ev_ebitda", "debt_eq"]].copy()
        df = df.merge(f, on="symbol", how="left")
        # Médiane globale en repli pour les titres sans fondamentaux disponibles
        for col in ["roe", "margin", "ev_ebitda", "debt_eq"]:
            df[col] = df[col].fillna(df[col].median())
    else:
        df["roe"] = 0.0
        df["margin"] = 0.0
        df["ev_ebitda"] = 0.0
        df["debt_eq"] = 0.0

    return df.dropna(subset=["target_next_return"])


def build_features_etf(mkt_df: pd.DataFrame, macro_df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Features spécifiques aux ETFs — modèle séparé de celui des actions.
    Pas de fondamentaux (roe/margin/ev_ebitda/debt_eq n'ont pas de sens pour
    un ETF, qui n'a pas de bilan d'entreprise propre). En échange :

    - dollar_volume : proxy d'activité/intérêt (prix × volume échangé). Ce
      n'est PAS un vrai flux de création/rachat de parts (ces données ne sont
      disponibles que via des fournisseurs payants comme ETF.com ou Massive/
      ETF Global) — c'est une approximation basée sur ce que yfinance fournit
      déjà gratuitement.
    - tracking_vs_ref : performance du rendement quotidien de l'ETF moins
      celle de son indice de référence (voir universe.ETF_INDICE_REFERENCE),
      ex. XLK vs SPY. Mesure si le secteur surperforme ou sous-performe le
      marché large ce jour-là — un signal de rotation sectorielle.
    """
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
        grp["dollar_volume"] = grp["close"] * grp["volume"]
        grp["dollar_volume_relatif"] = grp["dollar_volume"] / grp["dollar_volume"].rolling(20).mean()
        grp["target_next_return"] = grp["daily_return"].shift(-1)
        parts.append(grp)

    df = pd.concat(parts) if parts else pd.DataFrame()
    if df.empty:
        return df

    # --- vix_regime réel : même logique que pour les actions ---
    if macro_df is not None and not macro_df.empty and "^VIX" in macro_df["symbol"].unique():
        vix = macro_df[macro_df["symbol"] == "^VIX"][["date", "close"]].rename(columns={"close": "vix_close"})
        df = df.merge(vix, on="date", how="left")
        df["vix_regime"] = df["vix_close"].apply(_calc_vix_regime)
        df = df.drop(columns=["vix_close"])
    else:
        df["vix_regime"] = 1

    # --- tracking_vs_ref : rendement quotidien de l'ETF moins celui de son indice ---
    rendements_par_symbol = df.set_index(["date", "symbol"])["daily_return"].to_dict()
    tracking_values = []
    for _, row in df.iterrows():
        ref_symbol = universe.ETF_INDICE_REFERENCE.get(row["symbol"])
        if ref_symbol:
            rendement_ref = rendements_par_symbol.get((row["date"], ref_symbol))
            tracking_values.append(row["daily_return"] - rendement_ref if rendement_ref is not None else np.nan)
        else:
            tracking_values.append(np.nan)
    df["tracking_vs_ref"] = tracking_values
    df["tracking_vs_ref"] = df["tracking_vs_ref"].fillna(0.0)

    return df.dropna(subset=["target_next_return"])


# ------------------------------------------------------------------------------
# 4. MODELE XGBOOST — split temporel correct + métriques de diagnostic complètes
# ------------------------------------------------------------------------------
def _split_temporel_par_date(df: pd.DataFrame, train_ratio: float = 0.8, embargo: int = 0):
    """
    Split train/test par DATE DE COUPURE UNIQUE (pas par tri+index).
    Avec plusieurs tickers partageant les mêmes dates, un simple
    sort_values("date").iloc[:split_idx] mélange les tickers de façon
    incohérente selon leur ordre secondaire — la coupure doit se faire sur
    une date calendaire commune à tout l'univers, pour que train = strictement
    "avant" et test = strictement "après", quel que soit le ticker.
    """
    dates_uniques = np.sort(df["date"].unique())
    split_idx = int(len(dates_uniques) * train_ratio)
    date_coupure = dates_uniques[split_idx]

    # embargo : retire les `embargo` dernières dates du train. Une cible à 5 jours
    # chevauche la période de test ; sans embargo, les derniers jours du train
    # "voient" des prix du test (fuite d'information).
    date_fin_train = dates_uniques[max(split_idx - embargo, 0)]
    train = df[df["date"] < date_fin_train]
    test = df[df["date"] >= date_coupure]
    return train, test


def _cible_cfg(cible: str):
    """(colonne cible, embargo en jours). 'relatif_5j' = battre la médiane du jour sur 5 jours."""
    if cible == "relatif_5j":
        return "target_rel_5j", 5
    return "target_next_return", 0


def _ic_par_date(test_df: pd.DataFrame, y_proba: np.ndarray, col_cible: str):
    """IC moyen (corrélation de rang par date), t-stat et nombre de jours."""
    t = pd.DataFrame({"date": test_df["date"].values,
                      "p": np.asarray(y_proba, dtype=float),
                      "r": test_df[col_cible].values})
    t["rp"] = t.groupby("date")["p"].rank()
    t["rr"] = t.groupby("date")["r"].rank()
    ics = t.groupby("date").apply(
        lambda g: g["rp"].corr(g["rr"]) if len(g) >= 30 else np.nan
    ).dropna()
    if len(ics) < 10:
        return None, None, int(len(ics))
    ic = float(ics.mean())
    tstat = ic / (float(ics.std()) / np.sqrt(len(ics))) if ics.std() > 0 else None
    return round(ic, 4), (round(float(tstat), 2) if tstat is not None else None), int(len(ics))


@st.cache_resource(show_spinner="Entraînement du modèle IA...")
def train_ia(_df_hash: str, df: pd.DataFrame, seuil_neutre: float = 0.003,
             features: list[str] = None, cible: str = "jour") -> dict:
    """
    _df_hash : cle de cache stable (nombre de lignes + derniere date),
               car st.cache_resource ne hash pas bien les gros DataFrame.

    features : liste des colonnes à utiliser comme features. Par défaut
               utils.FEATURES_DEFAUT (modèle actions). Pour le modèle ETF,
               passer utils.FEATURES_ETF — cette fonction est partagée entre
               les deux, seule la liste de colonnes change.

    seuil_neutre : les mouvements de |rendement| < seuil_neutre (0.3% par défaut)
                   sont EXCLUS de l'entraînement et du test. Prédire "hausse" vs
                   "baisse" sur un mouvement de +0.01% est presque du bruit pur ;
                   en ignorant la zone neutre, la tâche devient "le titre a-t-il
                   fait un mouvement significatif à la hausse ou à la baisse ?",
                   nettement plus apprenable. C'est un choix de modélisation
                   explicite, pas un artifice pour gonfler l'accuracy : moins
                   d'exemples, mais des labels moins bruités.

    Split train/test par date de coupure unique (voir _split_temporel_par_date) :
    le modèle n'est jamais évalué sur une période qu'il a pu voir, même
    indirectement via un autre ticker de la même date.

    class_weight équilibré : le marché monte plus souvent qu'il ne baisse sur
    longue période (biais haussier structurel), donc sans pondération le
    modèle peut apprendre à prédire "hausse" par défaut et sembler bon sans
    rien avoir appris. On mesure aussi ce déséquilibre explicitement.
    """
    from xgboost import XGBClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import (
        accuracy_score, precision_score, recall_score, f1_score,
        confusion_matrix, roc_auc_score, log_loss, brier_score_loss,
    )

    feat = features if features is not None else utils.FEATURES_DEFAUT
    col_cible, embargo = _cible_cfg(cible)

    if df.empty or col_cible not in df.columns:
        return {"model": None, "features": feat, "accuracy": 0.0, "diagnostics": None}

    # Filtrage de la zone neutre — appliqué ICI (pas dans build_features) pour
    # que target_next_return brut reste disponible ailleurs si besoin.
    df = df.dropna(subset=[col_cible])
    df_signif = df[df[col_cible].abs() >= seuil_neutre].copy()
    n_exclus = len(df) - len(df_signif)

    if df_signif.empty:
        return {"model": None, "features": feat, "accuracy": 0.0, "diagnostics": None}

    train_df, test_df = _split_temporel_par_date(df_signif, train_ratio=0.8, embargo=embargo)

    if train_df.empty or test_df.empty:
        return {"model": None, "features": feat, "accuracy": 0.0, "diagnostics": None}

    X_train = train_df[feat].values
    y_train = (train_df[col_cible] > 0).astype(int).values
    X_test = test_df[feat].values
    y_test = (test_df[col_cible] > 0).astype(int).values

    # Répartition des classes — révèle un éventuel biais structurel du marché
    taux_hausse_train = y_train.mean()
    taux_hausse_test = y_test.mean()

    # Poids de classe équilibré (scale_pos_weight XGBoost = ratio négatifs/positifs)
    n_pos = y_train.sum()
    n_neg = len(y_train) - n_pos
    scale_pos_weight = (n_neg / n_pos) if n_pos > 0 else 1.0

    imp, scl = SimpleImputer(strategy="median"), StandardScaler()
    X_train_s = scl.fit_transform(imp.fit_transform(X_train))
    X_test_s = scl.transform(imp.transform(X_test))

    model = XGBClassifier(
        n_estimators=200,
        max_depth=4,
        learning_rate=0.03,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        scale_pos_weight=scale_pos_weight,
        random_state=42,
        eval_metric="logloss",
    )
    model.fit(X_train_s, y_train)

    y_pred = model.predict(X_test_s)
    y_proba = model.predict_proba(X_test_s)[:, 1]

    accuracy = round(accuracy_score(y_test, y_pred) * 100, 1)

    # Baseline naïve : toujours prédire la classe majoritaire du train.
    # Si notre modèle ne bat pas cette baseline, il n'apprend rien d'utile.
    classe_majoritaire = int(round(taux_hausse_train))
    baseline_pred = np.full_like(y_test, classe_majoritaire)
    baseline_accuracy = round(accuracy_score(y_test, baseline_pred) * 100, 1)

    # --- Log loss & Brier score : pénalisent les prédictions confiantes et fausses.
    # Une baseline qui prédit toujours p=taux_hausse_train sert de référence :
    # si notre modèle a un log loss PIRE que cette baseline constante, ses
    # probabilités sont moins fiables qu'un simple taux de base, même si son
    # accuracy semble correcte (l'accuracy ignore la confiance de la prédiction).
    logloss_modele = round(log_loss(y_test, y_proba), 4)
    proba_constante = np.full_like(y_test, taux_hausse_train, dtype=float)
    logloss_baseline = round(log_loss(y_test, proba_constante), 4)
    brier = round(brier_score_loss(y_test, y_proba), 4)

    # --- Calibration : regroupe les prédictions par tranche de probabilité,
    # compare la proba moyenne prédite au taux de hausse réellement observé
    # dans chaque tranche. Un modèle bien calibré a proba_predite ≈ taux_reel.
    calibration_bins = []
    bin_edges = np.linspace(0, 1, 6)  # 5 tranches : [0-20%], [20-40%], ...
    for i in range(len(bin_edges) - 1):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask = (y_proba >= lo) & (y_proba < hi) if i < len(bin_edges) - 2 else (y_proba >= lo) & (y_proba <= hi)
        if mask.sum() > 0:
            calibration_bins.append({
                "tranche": f"{int(lo*100)}-{int(hi*100)}%",
                "proba_moyenne_predite": round(float(y_proba[mask].mean()) * 100, 1),
                "taux_reel_observe": round(float(y_test[mask].mean()) * 100, 1),
                "n_observations": int(mask.sum()),
            })

    # --- Performance par régime de marché (vix_regime) : un modèle peut très
    # bien marcher en période calme et échouer en période de stress (ou
    # l'inverse) — ça se noie complètement dans une accuracy globale unique.
    perf_par_regime = []
    if "vix_regime" in test_df.columns:
        noms_regime = {0: "Calme (VIX<15)", 1: "Normal (15-25)", 2: "Stress (VIX>25)"}
        for regime_val in sorted(test_df["vix_regime"].dropna().unique()):
            mask = (test_df["vix_regime"] == regime_val).values
            if mask.sum() >= 10:  # assez d'observations pour une métrique significative
                perf_par_regime.append({
                    "regime": noms_regime.get(int(regime_val), f"Régime {regime_val}"),
                    "accuracy": round(accuracy_score(y_test[mask], y_pred[mask]) * 100, 1),
                    "n_observations": int(mask.sum()),
                })

    # --- Performance par ticker : révèle si le modèle marche mieux sur
    # certains titres que d'autres — utile pour savoir si un modèle par-ticker
    # serait plus pertinent qu'un modèle global mélangeant tous les titres.
    perf_par_ticker = []
    if "symbol" in test_df.columns:
        for sym in sorted(test_df["symbol"].unique()):
            mask = (test_df["symbol"] == sym).values
            if mask.sum() >= 10:
                perf_par_ticker.append({
                    "ticker": sym,
                    "accuracy": round(accuracy_score(y_test[mask], y_pred[mask]) * 100, 1),
                    "n_observations": int(mask.sum()),
                })
        perf_par_ticker.sort(key=lambda x: x["accuracy"], reverse=True)

    # --- Walk-forward validation : plusieurs fenêtres temporelles indépendantes
    # pour juger si l'accuracy est stable dans le temps ou si le chiffre unique
    # du split principal ci-dessus est un coup de chance sur cette période précise.
    wf = walk_forward_validation(df, feat, seuil_neutre=seuil_neutre, n_fenetres=5, cible=cible)

    # --- IC (Information Coefficient) : corrélation de rang, PAR DATE, entre la
    # probabilité prédite et le rendement réalisé, puis moyenne sur les dates.
    # C'est la mesure standard du pouvoir prédictif cross-sectionnel : 0.02-0.05
    # est déjà un signal exploitable ; l'accuracy seule masque ce genre d'effet.
    ic_moyen, ic_t, ic_n = _ic_par_date(test_df, y_proba, col_cible)

    diagnostics = {
        "cible": cible,
        "ic_moyen": ic_moyen,
        "ic_t": ic_t,
        "ic_n_jours": ic_n,
        "accuracy": accuracy,
        "baseline_accuracy": baseline_accuracy,
        "amelioration_vs_baseline": round(accuracy - baseline_accuracy, 1),
        "precision": round(precision_score(y_test, y_pred, zero_division=0) * 100, 1),
        "recall": round(recall_score(y_test, y_pred, zero_division=0) * 100, 1),
        "f1": round(f1_score(y_test, y_pred, zero_division=0) * 100, 1),
        "roc_auc": round(roc_auc_score(y_test, y_proba) * 100, 1) if len(np.unique(y_test)) > 1 else None,
        "confusion_matrix": confusion_matrix(y_test, y_pred).tolist(),
        "taux_hausse_train": round(taux_hausse_train * 100, 1),
        "taux_hausse_test": round(taux_hausse_test * 100, 1),
        "n_train": len(y_train),
        "n_test": len(y_test),
        "n_exclus_zone_neutre": n_exclus,
        "seuil_neutre": seuil_neutre,
        "logloss_modele": logloss_modele,
        "logloss_baseline": logloss_baseline,
        "brier_score": brier,
        "calibration_bins": calibration_bins,
        "perf_par_regime": perf_par_regime,
        "perf_par_ticker": perf_par_ticker,
        "walk_forward": wf,
    }

    # Ré-entraîne sur l'ensemble des données SIGNIFICATIVES (train + test, hors
    # zone neutre) pour l'usage en production (audit SHAP, etc.), tout en
    # gardant les métriques mesurées honnêtement sur le split test ci-dessus.
    X_full = df_signif[feat].values
    y_full = (df_signif[col_cible] > 0).astype(int).values
    X_full_s = scl.fit_transform(imp.fit_transform(X_full))
    model.fit(X_full_s, y_full)

    return {
        "model": model, "imputer": imp, "scaler": scl, "features": feat,
        "accuracy": accuracy, "diagnostics": diagnostics,
    }


def walk_forward_validation(df: pd.DataFrame, feat: list[str], seuil_neutre: float = 0.003,
                             n_fenetres: int = 5, train_ratio: float = 0.8, cible: str = "jour") -> dict:
    """
    Un seul split 80/20 donne UN chiffre d'accuracy, qui peut être un coup de
    chance (ou de malchance) selon la période testée. La walk-forward
    validation répète le même protocole sur plusieurs fenêtres temporelles
    glissantes non chevauchantes, pour obtenir une distribution (moyenne +
    écart-type) plutôt qu'un point unique — bien plus honnête pour juger si
    le modèle a un vrai edge stable dans le temps ou si le 51-55% observé
    fluctue au hasard d'une période à l'autre.

    Découpage : le dataset est divisé en n_fenetres tranches temporelles
    égales. Dans chaque tranche, on ré-applique le même split 80/20
    train/test qu'ailleurs, on entraîne un modèle indépendant, et on mesure
    son accuracy sur le test de cette tranche uniquement.
    """
    from xgboost import XGBClassifier
    from sklearn.preprocessing import StandardScaler
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import accuracy_score

    col_cible, embargo = _cible_cfg(cible)
    df = df.dropna(subset=[col_cible])
    df_signif = df[df[col_cible].abs() >= seuil_neutre].copy()
    if df_signif.empty:
        return {"fenetres": [], "accuracy_moyenne": None, "accuracy_ecart_type": None}

    dates_uniques = np.sort(df_signif["date"].unique())
    if len(dates_uniques) < n_fenetres * 20:  # pas assez de données pour découper proprement
        return {"fenetres": [], "accuracy_moyenne": None, "accuracy_ecart_type": None}

    limites = np.array_split(dates_uniques, n_fenetres)
    resultats = []

    for i, dates_fenetre in enumerate(limites):
        df_fenetre = df_signif[df_signif["date"].isin(dates_fenetre)]
        train_f, test_f = _split_temporel_par_date(df_fenetre, train_ratio=train_ratio, embargo=embargo)

        if train_f.empty or test_f.empty or len(train_f) < 30 or len(test_f) < 10:
            continue

        X_train = train_f[feat].values
        y_train = (train_f[col_cible] > 0).astype(int).values
        X_test = test_f[feat].values
        y_test = (test_f[col_cible] > 0).astype(int).values

        if len(np.unique(y_train)) < 2:  # une seule classe présente, impossible d'entraîner
            continue

        n_pos = y_train.sum()
        n_neg = len(y_train) - n_pos
        spw = (n_neg / n_pos) if n_pos > 0 else 1.0

        imp_f, scl_f = SimpleImputer(strategy="median"), StandardScaler()
        X_train_s = scl_f.fit_transform(imp_f.fit_transform(X_train))
        X_test_s = scl_f.transform(imp_f.transform(X_test))

        model_f = XGBClassifier(
            n_estimators=200, max_depth=4, learning_rate=0.03,
            subsample=0.8, colsample_bytree=0.8, min_child_weight=5,
            scale_pos_weight=spw, random_state=42, eval_metric="logloss",
        )
        model_f.fit(X_train_s, y_train)
        acc = round(accuracy_score(y_test, model_f.predict(X_test_s)) * 100, 1)

        resultats.append({
            "fenetre": i + 1,
            "date_debut": str(pd.Timestamp(dates_fenetre.min()).date()),
            "date_fin": str(pd.Timestamp(dates_fenetre.max()).date()),
            "accuracy": acc,
            "n_test": len(y_test),
        })

    if not resultats:
        return {"fenetres": [], "accuracy_moyenne": None, "accuracy_ecart_type": None}

    accs = [r["accuracy"] for r in resultats]
    return {
        "fenetres": resultats,
        "accuracy_moyenne": round(float(np.mean(accs)), 1),
        "accuracy_ecart_type": round(float(np.std(accs)), 1),
    }


def comparer_seuils_neutres(df: pd.DataFrame, feat: list[str], seuils: list[float] = None) -> pd.DataFrame:
    """Compare plusieurs seuils de zone neutre sur les mêmes données."""
    if seuils is None:
        seuils = [0.001, 0.003, 0.005, 0.01, 0.015, 0.02]

    resultats = []
    for s in seuils:
        cache_key = f"comparaison_seuil_{s}_{len(df)}"
        r = train_ia(cache_key, df, seuil_neutre=s, features=feat)
        d = r.get("diagnostics")
        if d:
            resultats.append({
                "seuil_pct": round(s * 100, 2),
                "accuracy": d["accuracy"],
                "baseline_accuracy": d["baseline_accuracy"],
                "delta_vs_baseline": d["amelioration_vs_baseline"],
                "roc_auc": d["roc_auc"],
                "n_train": d["n_train"],
                "n_test": d["n_test"],
                "n_exclus": d["n_exclus_zone_neutre"],
            })

    if not resultats:
        return pd.DataFrame()

    return pd.DataFrame(resultats).sort_values("delta_vs_baseline", ascending=False).reset_index(drop=True)


# ------------------------------------------------------------------------------
# 4 bis. MODELES A LA DEMANDE — entraînés seulement quand une page en a besoin
# (évite d'entraîner 3 modèles à chaque chargement ; train_ia est mis en cache)
# ------------------------------------------------------------------------------
def entrainer_modele_relatif(data: dict) -> dict:
    """Modèle relatif : bat la médiane de l'univers sur 5 jours (features en rang cross-sectionnel)."""
    df = data["market_data_clean"]
    cle = f"{len(df)}_{df['date'].max() if not df.empty else 'empty'}_rel"
    return train_ia(cle, df, seuil_neutre=0.0, features=utils.FEATURES_RELATIF, cible="relatif_5j")


def entrainer_modele_etf(data: dict) -> tuple[dict, pd.DataFrame]:
    """Modèle ETF + tableau d'importance des features."""
    df = data["market_etf_clean"]
    cle = f"{len(df)}_{df['date'].max() if not df.empty else 'empty'}_etf"
    res = train_ia(cle, df, features=utils.FEATURES_ETF)
    importance = pd.DataFrame()
    if res["model"] is not None:
        importance = pd.DataFrame({
            "Feature": res["features"],
            "Importance": res["model"].feature_importances_,
        }).sort_values("Importance", ascending=False)
    return res, importance


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

    etape.info("Étape 5/5 — Calcul des indicateurs et entraînement des modèles IA...")

    # Séparation actions / ETFs — les fondamentaux (roe, margin...) n'ont pas de
    # sens pour un ETF, et ses dynamiques de prix diffèrent d'une action isolée
    # (déjà diversifié). Deux modèles distincts plutôt que de tout mélanger.
    symboles_etf = set(universe.ETFS_SECTORIELS.keys())
    market_actions = market_data_raw[~market_data_raw["symbol"].isin(symboles_etf)] if not market_data_raw.empty else market_data_raw
    market_etf = market_data_raw[market_data_raw["symbol"].isin(symboles_etf)] if not market_data_raw.empty else market_data_raw

    market_data_clean = build_features(market_actions, macro_data_raw, utils.dict_secteurs, fonda_data_clean)
    cache_key = f"{len(market_data_clean)}_{market_data_clean['date'].max() if not market_data_clean.empty else 'empty'}"
    model_result = train_ia(cache_key, market_data_clean, features=utils.FEATURES_DEFAUT)

    market_etf_clean = build_features_etf(market_etf, macro_data_raw)

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
        "market_etf_clean": market_etf_clean,
        "zscore_df": zscore_df,
        "model_result": model_result,
        "model_ia": model_result["model"],
        "importance_df": importance_df,
        "ratings_df": ratings_df,
    }
