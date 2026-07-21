# universe.py
# ==============================================================================
# UNIVERS DE TICKERS — S&P 500 + Nasdaq 100 + ETFs sectoriels/indiciels
# Récupération dynamique depuis Wikipedia (source ouverte, toujours à jour),
# avec repli sur une liste statique si le scraping échoue (résilience réseau).
# ==============================================================================
import streamlit as st
import pandas as pd

# --- ETFs sectoriels/indiciels (statiques — univers stable, peu de changements) ---
ETFS_SECTORIELS = {
    "SPY": "SPDR S&P 500 ETF",
    "QQQ": "Invesco QQQ (Nasdaq-100)",
    "DIA": "SPDR Dow Jones Industrial Average",
    "IWM": "iShares Russell 2000",
    "XLK": "Technology Select Sector SPDR",
    "XLF": "Financial Select Sector SPDR",
    "XLV": "Health Care Select Sector SPDR",
    "XLE": "Energy Select Sector SPDR",
    "XLY": "Consumer Discretionary Select SPDR",
    "XLP": "Consumer Staples Select SPDR",
    "XLI": "Industrial Select Sector SPDR",
    "XLB": "Materials Select Sector SPDR",
    "XLU": "Utilities Select Sector SPDR",
    "XLRE": "Real Estate Select Sector SPDR",
    "XLC": "Communication Services Select SPDR",
}

# --- Repli statique (utilisé seulement si le scraping Wikipedia échoue) ---
FALLBACK_SP500 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "BRK.B", "JPM",
    "V", "LLY", "AVGO", "UNH", "XOM", "MA", "PG", "HD", "COST", "MRK",
]
FALLBACK_NASDAQ100 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA", "AVGO", "COST",
    "NFLX", "AMD", "PEP", "ADBE", "CSCO", "INTC", "QCOM", "AMGN", "TXN", "INTU",
]


@st.cache_data(ttl=86400, show_spinner="Récupération de la liste S&P 500...")
def get_sp500_tickers() -> pd.DataFrame:
    """Retourne un DataFrame [symbol, nom, secteur] depuis Wikipedia. TTL 24h."""
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
        df = tables[0][["Symbol", "Security", "GICS Sector"]].copy()
        df.columns = ["symbol", "nom", "secteur"]
        df["symbol"] = df["symbol"].str.replace(".", "-", regex=False)  # BRK.B -> BRK-B (format yfinance)
        df["indice"] = "S&P 500"
        return df
    except Exception as e:
        st.warning(f"Impossible de charger la liste S&P 500 depuis Wikipedia ({e}) — repli sur liste statique réduite.")
        return pd.DataFrame({
            "symbol": FALLBACK_SP500,
            "nom": FALLBACK_SP500,
            "secteur": "Inconnu",
            "indice": "S&P 500",
        })


@st.cache_data(ttl=86400, show_spinner="Récupération de la liste Nasdaq-100...")
def get_nasdaq100_tickers() -> pd.DataFrame:
    """Retourne un DataFrame [symbol, nom, secteur] depuis Wikipedia. TTL 24h."""
    try:
        tables = pd.read_html("https://en.wikipedia.org/wiki/Nasdaq-100")
        # La table des composants n'est pas toujours au même index selon les éditions Wikipedia
        df = None
        for t in tables:
            cols = [str(c).lower() for c in t.columns]
            if any("ticker" in c or "symbol" in c for c in cols):
                df = t
                break
        if df is None:
            raise ValueError("table des composants introuvable")

        col_symbol = next(c for c in df.columns if "ticker" in str(c).lower() or "symbol" in str(c).lower())
        col_nom = next((c for c in df.columns if "company" in str(c).lower()), df.columns[0])
        col_secteur = next((c for c in df.columns if "sector" in str(c).lower()), None)

        out = pd.DataFrame({
            "symbol": df[col_symbol].astype(str).str.replace(".", "-", regex=False),
            "nom": df[col_nom].astype(str),
            "secteur": df[col_secteur].astype(str) if col_secteur else "Inconnu",
        })
        out["indice"] = "Nasdaq-100"
        return out
    except Exception as e:
        st.warning(f"Impossible de charger la liste Nasdaq-100 depuis Wikipedia ({e}) — repli sur liste statique réduite.")
        return pd.DataFrame({
            "symbol": FALLBACK_NASDAQ100,
            "nom": FALLBACK_NASDAQ100,
            "secteur": "Inconnu",
            "indice": "Nasdaq-100",
        })


@st.cache_data(ttl=86400, show_spinner=False)
def get_etf_tickers() -> pd.DataFrame:
    return pd.DataFrame({
        "symbol": list(ETFS_SECTORIELS.keys()),
        "nom": list(ETFS_SECTORIELS.values()),
        "secteur": "ETF",
        "indice": "ETF",
    })


@st.cache_data(ttl=86400, show_spinner="Construction de l'univers de tickers...")
def get_univers_complet() -> pd.DataFrame:
    """
    Univers dédoublonné : S&P 500 + Nasdaq 100 + ETFs.
    Colonnes : symbol, nom, secteur, indice (peut être multi-indice, on garde la 1ère occurrence).
    """
    sp500 = get_sp500_tickers()
    nasdaq = get_nasdaq100_tickers()
    etfs = get_etf_tickers()

    combined = pd.concat([sp500, nasdaq, etfs], ignore_index=True)
    combined = combined.drop_duplicates(subset="symbol", keep="first").reset_index(drop=True)
    combined = combined.sort_values("symbol").reset_index(drop=True)
    return combined


def search_tickers(query: str, univers_df: pd.DataFrame, limit: int = 25) -> pd.DataFrame:
    """Recherche insensible à la casse sur symbol OU nom. Utilisé par le Screener."""
    if not query:
        return univers_df.head(limit)
    q = query.strip().upper()
    mask = univers_df["symbol"].str.upper().str.contains(q, na=False) | \
           univers_df["nom"].str.upper().str.contains(q, na=False)
    return univers_df[mask].head(limit)
