# utils.py
# ==============================================================================
# CONFIGURATION STATIQUE
# ==============================================================================

# --- Liste "core" — tickers suivis activement (fondamentaux Alpha Vantage inclus) ---
# L'univers élargi (S&P 500 + Nasdaq 100 + ETFs) est chargé dynamiquement
# via universe.py — cette liste reste le socle par défaut pour l'ETL fondamentaux.
actifs_sp500 = ["AAPL", "MSFT", "NVDA", "JPM", "LLY", "TSLA", "AMZN", "META", "GOOGL", "V", "MA", "UNH"]
actifs_macro = ["^VIX", "SPY"]

dict_secteurs = {
    "Technologie": ["AAPL", "MSFT", "NVDA"],
    "Finance": ["JPM", "V", "MA"],
    "Santé": ["LLY", "UNH"],
    "Consommation": ["TSLA", "AMZN"],
    "Communication": ["META", "GOOGL"],
}

dict_noms = {
    "AAPL": "Apple Inc.", "MSFT": "Microsoft Corp.", "NVDA": "NVIDIA Corp.",
    "JPM": "JPMorgan Chase", "LLY": "Eli Lilly", "TSLA": "Tesla Inc.",
    "AMZN": "Amazon.com", "META": "Meta Platforms", "GOOGL": "Alphabet Inc.",
    "V": "Visa Inc.", "MA": "Mastercard Inc.", "UNH": "UnitedHealth Group",
}

FEATURES_DEFAUT = [
    'daily_return', 'pct_vs_ma50', 'macd_diff', 'mom_5j',
    'mom_20j', 'vol_relative', 'rsi_14', 'volatility',
    'vix_regime', 'rsi_rank_sec'
]
