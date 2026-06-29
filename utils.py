# utils.py
# ==============================================================================
# CONFIGURATION STATIQUE
# ==============================================================================

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
