# data_pipeline.py
# ==============================================================================
# PIPELINE ETL — Yahoo Finance + Alpha Vantage -> Supabase (exécuté par le cron, cron_sync.py)
# ==============================================================================
import time
import requests
import pandas as pd
import yfinance as yf

import db
import utils

CLE_ALPHA_VANTAGE = db._get_secret("ALPHA_VANTAGE_KEY")


def _info(msg: str) -> None:
    print(f"[PIPELINE] {msg}")


def _avert(msg: str) -> None:
    print(f"[PIPELINE][WARN] {msg}")


# ------------------------------------------------------------------------------
# 1. DONNEES DE MARCHE (Yahoo Finance -> Supabase)
# ------------------------------------------------------------------------------
HISTORIQUE_DEBUT = "2020-01-01"       # stocké dans Supabase (appli, indicateurs, portefeuille)
HISTORIQUE_LONG_DEBUT = "2005-01-01"  # téléchargé à chaque passage mais NON stocké : sert seulement à
                                      # évaluer les modèles « horizon » (6 mois / 1 an) sur assez d'années
_HISTORIQUE_LONG: dict[str, pd.DataFrame] = {}
MARGE_JOURS = 5          # on ré-écrit les derniers jours (corrections Yahoo, jours fériés)


def _telecharger_yahoo(tickers: list[str], start: str = HISTORIQUE_DEBUT) -> pd.DataFrame:
    data = yf.download(tickers, start=start, progress=False, auto_adjust=False, threads=True)
    if data is None or data.empty:
        return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume"])
    if isinstance(data.columns, pd.MultiIndex):
        data = data.stack(level=1, future_stack=True).rename_axis(["Date", "symbol"]).reset_index()
    else:
        data = data.reset_index()
        data["symbol"] = tickers[0]
    data.columns = [str(c).lower() for c in data.columns]
    data = data[["symbol", "date", "open", "high", "low", "close", "volume"]]
    data = data.dropna(subset=["close"])

    # Supabase: la colonne 'volume' est de type bigint -> aucune virgule tolérée.
    data["volume"] = pd.to_numeric(data["volume"], errors="coerce").fillna(0).astype("int64")
    for col in ["open", "high", "low", "close"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data["date"] = pd.to_datetime(data["date"]).dt.date
    return data


def _sync_incremental(tickers: list[str], table: str) -> pd.DataFrame:
    """Télécharge l'historique complet depuis Yahoo (rapide, en mémoire) mais
    n'ÉCRIT dans Supabase que ce qui est nouveau :
      - ticker absent de la base  -> tout l'historique
      - ticker présent            -> lignes >= dernière date en base - MARGE_JOURS
    Avant : ~800 000 lignes ré-upsertées à chaque run (~10 min). Après : quelques milliers.
    Retourne l'historique complet téléchargé (utilisé pour les features / le modèle).
    """
    try:
        dernieres = db.last_dates_by_symbol(table)
    except Exception as e:
        _avert(f"Vue {table}_last indisponible ({e}) — écriture complète.")
        dernieres = {}

    frames, n_ecrites = [], 0
    batch_size = 100
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i + batch_size]
        try:
            df = _telecharger_yahoo(batch, start=HISTORIQUE_LONG_DEBUT if table == "market_data" else HISTORIQUE_DEBUT)
        except Exception as e:
            _avert(f"Erreur Yahoo Finance sur le lot {batch[:3]}... : {e}")
            continue
        if df.empty:
            continue
        frames.append(df)

        seuil = df["symbol"].map(
            lambda s: dernieres[s] - pd.Timedelta(days=MARGE_JOURS) if s in dernieres else pd.Timestamp(HISTORIQUE_DEBUT).date()
        )
        a_ecrire = df[(df["date"] >= seuil) & (df["date"] >= pd.Timestamp(HISTORIQUE_DEBUT).date())]
        db.upsert_market_data(a_ecrire, table=table)
        n_ecrites += len(a_ecrire)
        _info(f"{table} : {min(i + batch_size, len(tickers))}/{len(tickers)} tickers — {len(a_ecrire)} lignes écrites")
        if table == "market_data":  # 5 % -> 30 % de la barre de progression
            db.progression(5 + int(25 * min(i + batch_size, len(tickers)) / len(tickers)),
                           f"Cours : {min(i + batch_size, len(tickers))}/{len(tickers)} titres")

    _info(f"{table} : {n_ecrites} lignes écrites au total")
    if not frames:
        return pd.DataFrame(columns=["symbol", "date", "open", "high", "low", "close", "volume"])
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    out = out.sort_values(["symbol", "date"]).reset_index(drop=True)
    # Le reste du calcul garde l'historique habituel ; le long historique est mis de côté pour les modèles horizon.
    _HISTORIQUE_LONG[table] = out
    return out[out["date"] >= pd.Timestamp(HISTORIQUE_DEBUT)].reset_index(drop=True)


def historique_long(table: str = "market_data") -> pd.DataFrame | None:
    """Historique depuis HISTORIQUE_LONG_DEBUT téléchargé pendant ce passage du cron (None sinon)."""
    return _HISTORIQUE_LONG.get(table)


# ------------------------------------------------------------------------------
# 2. FONDAMENTAUX + Z-SCORE (Alpha Vantage BALANCE_SHEET + INCOME_STATEMENT -> Supabase, TTL 7 jours)
#    Reste limité à la liste "core" suivie activement (pas l'univers élargi)
#    pour respecter le rate-limit Alpha Vantage (5 req/min plan gratuit).
# ------------------------------------------------------------------------------
def _av_message(data) -> str:
    """Résume une réponse Alpha Vantage sans données (quota, clé, symbole inconnu)."""
    if not isinstance(data, dict):
        return f"réponse inattendue ({type(data).__name__})"
    for k in ("Note", "Information", "Error Message"):
        if k in data:
            return f"{k} : {str(data[k])[:200]}"
    return f"clés reçues : {sorted(data.keys())[:8] or 'aucune (réponse vide)'}"


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


def ratios_depuis_bilans(bs0: dict, inc0: dict, prix: float) -> dict | None:
    """Z-Score Altman + fondamentaux calculés depuis le dernier exercice annuel.

    L'endpoint OVERVIEW d'Alpha Vantage (ROE, marge, EV/EBITDA
    « TTM ») est désormais réservé aux offres payantes. BALANCE_SHEET et INCOME_STATEMENT
    restent gratuits : on recalcule les mêmes ratios à partir du dernier
    exercice annuel (et non des 12 derniers mois glissants).
    Retourne None si le bilan est inexploitable.
    """
    total_assets = _safe_get(bs0, "totalAssets")
    if total_assets <= 0:
        return None
    total_liabilities = _safe_get(bs0, "totalLiabilities")
    equity = _safe_get(bs0, "totalShareholderEquity")
    shares_out = _safe_get(bs0, "commonStockSharesOutstanding")
    cash = _safe_get(bs0, "cashAndCashEquivalentsAtCarryingValue")
    dette = _safe_get(bs0, "shortLongTermDebtTotal") or (
        _safe_get(bs0, "longTermDebt") + _safe_get(bs0, "shortTermDebt"))

    revenue = _safe_get(inc0, "totalRevenue")
    ebit = _safe_get(inc0, "ebit")
    ebitda = _safe_get(inc0, "ebitda")
    net_income = _safe_get(inc0, "netIncome")
    operating_income = _safe_get(inc0, "operatingIncome")

    market_cap = (prix or 0.0) * shares_out

    A = (_safe_get(bs0, "totalCurrentAssets") - _safe_get(bs0, "totalCurrentLiabilities")) / total_assets
    B = _safe_get(bs0, "retainedEarnings") / total_assets
    C = ebit / total_assets
    D = market_cap / total_liabilities if total_liabilities > 0 else 0.0
    E = revenue / total_assets
    z = 1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E

    def ratio(num, den):
        return round(num / den, 4) if den and den > 0 else None

    return {
        "z_score": round(z, 3),
        "roe": ratio(net_income, equity),                        # fraction (0.25 = 25 %)
        "margin": ratio(operating_income, revenue),              # fraction
        "debt_eq": ratio(dette, equity),                         # multiple
        "ev_ebitda": ratio(market_cap + dette - cash, ebitda) if market_cap > 0 else None,
    }


def sync_bilans(tickers: list[str], prix_actuels: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Rafraîchit fondamentaux (fonda_data) ET Z-Score (zscore_data) en une seule
    passe : 2 requêtes Alpha Vantage par titre (BALANCE_SHEET + INCOME_STATEMENT).
    TTL 7 jours : un titre est rafraîchi si l'une des deux tables est périmée.
    Plan gratuit : 25 requêtes/jour -> 12 titres max par jour.
    prix_actuels : {symbol: dernier_prix} pour la capitalisation (prix x actions).
    Retourne (fonda_df, zscore_df).
    """
    tickers = list(tickers)
    fonda_df = db.fetch_fonda_data(tickers)
    zscore_df = db.fetch_zscore_data(tickers)
    perimes = set(db.tickers_a_rafraichir(tickers, fonda_df, ttl_jours=7)) | \
        set(db.tickers_a_rafraichir_zscore(tickers, zscore_df, ttl_jours=7))
    a_rafraichir = [t for t in tickers if t in perimes]

    if not a_rafraichir:
        return fonda_df, zscore_df

    if not CLE_ALPHA_VANTAGE:
        _avert(f"Clé Alpha Vantage absente : {len(a_rafraichir)} titre(s) non rafraîchi(s).")
        return fonda_df, zscore_df

    total = len(a_rafraichir)
    fonda_records, z_records = [], []
    aujourdhui = str(pd.Timestamp.today().date())

    for i, t in enumerate(a_rafraichir):
        _info(f"Bilans : {i}/{total} — {t}...")
        try:
            url_bs = f"https://www.alphavantage.co/query?function=BALANCE_SHEET&symbol={t}&apikey={CLE_ALPHA_VANTAGE}"
            bs = requests.get(url_bs, timeout=10).json()
            time.sleep(13)  # Rate limit Alpha Vantage (plan gratuit : 5 req/min)

            url_is = f"https://www.alphavantage.co/query?function=INCOME_STATEMENT&symbol={t}&apikey={CLE_ALPHA_VANTAGE}"
            inc = requests.get(url_is, timeout=10).json()
            time.sleep(13)

            if not bs.get("annualReports") or not inc.get("annualReports"):
                _avert(f"Alpha Vantage bilan/compte de résultat sans données pour {t} — "
                           f"{_av_message(bs if not bs.get('annualReports') else inc)}")
                continue

            r = ratios_depuis_bilans(bs["annualReports"][0], inc["annualReports"][0], prix_actuels.get(t, 0.0))
            if r is None:
                continue
            z_records.append({"symbol": t, "z_score": r["z_score"], "last_updated": aujourdhui})
            fonda_records.append({"symbol": t, "roe": r["roe"], "margin": r["margin"],
                                  "debt_eq": r["debt_eq"], "ev_ebitda": r["ev_ebitda"],
                                  "last_updated": aujourdhui})
        except Exception as e:
            _avert(f"Erreur Alpha Vantage sur {t} : {e}")

    if z_records:
        _info(f"{len(z_records)} bilan(s) mis à jour (fondamentaux + Z-Score)")
        db.upsert_zscore_data(z_records)
        db.upsert_fonda_data(fonda_records)

    return db.fetch_fonda_data(tickers), db.fetch_zscore_data(tickers)


# ------------------------------------------------------------------------------
# 3. RÉGIME DE MARCHÉ (VIX) — affiché dans l'appli (market_overview)
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


# ------------------------------------------------------------------------------
# 4. POINT D'ENTRÉE UNIQUE — appelé par cron_sync.py
# ------------------------------------------------------------------------------
def get_all_data(univers_etendu: list[str] | None = None) -> dict:
    """Télécharge et enregistre les données du passage du cron :
      - cours (Yahoo) de l'univers élargi, écriture incrémentale dans Supabase ;
      - macro (VIX, SPY) ;
      - bilans Alpha Vantage (fondamentaux + Z-Score) de la liste « core » seulement (quota gratuit) ;
      - notes de crédit S&P (table statique).
    """
    tickers_core = list(utils.actifs_sp500)
    tickers_prix = list(univers_etendu) if univers_etendu else tickers_core

    _info("Étape 1/3 — Données de marché (Yahoo Finance)...")
    market_data_raw = _sync_incremental(tickers_prix, "market_data")
    _info("Étape 2/3 — Données macro (VIX, SPY)...")
    macro_data_raw = _sync_incremental(list(utils.actifs_macro), "macro_data")

    db.progression(32, "Bilans (Alpha Vantage)")
    _info("Étape 3/3 — Bilans : fondamentaux et Z-Score Altman (Alpha Vantage)...")
    prix_actuels = {}
    if not market_data_raw.empty:
        core = market_data_raw[market_data_raw["symbol"].isin(tickers_core)]
        if not core.empty:
            prix_actuels = core.sort_values("date").groupby("symbol").last()["close"].to_dict()
    fonda_data_clean, zscore_df = sync_bilans(tickers_core, prix_actuels)

    return {
        "market_data_raw": market_data_raw,
        "macro_data_raw": macro_data_raw,
        "fonda_data_clean": fonda_data_clean,
        "zscore_df": zscore_df,
        "ratings_df": db.fetch_ratings(),
    }
