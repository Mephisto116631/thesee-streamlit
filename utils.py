# utils.py
# ==============================================================================
# CONFIGURATION STATIQUE
# ==============================================================================

# --- Liste "core" : seuls titres dont les bilans Alpha Vantage sont rafraîchis (quota gratuit) ---
# L'univers élargi (S&P 500 + Nasdaq 100 + ETFs) est chargé dynamiquement via universe.py.
actifs_sp500 = ["AAPL", "MSFT", "NVDA", "JPM", "LLY", "TSLA", "AMZN", "META", "GOOGL", "V", "MA", "UNH"]
actifs_macro = ["^VIX", "SPY"]
