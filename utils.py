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
    'vix_regime', 'rsi_rank_sec',
    'roe', 'margin', 'ev_ebitda', 'debt_eq',  # fondamentaux Alpha Vantage
]

# Features du modèle ETF (séparé du modèle actions) — pas de fondamentaux,
# ajout du tracking vs indice de référence et du proxy dollar-volume.
FEATURES_ETF = [
    'daily_return', 'pct_vs_ma50', 'macd_diff', 'mom_5j',
    'mom_20j', 'vol_relative', 'rsi_14', 'volatility',
    'vix_regime', 'tracking_vs_ref', 'dollar_volume_relatif',
]

# --- Modèle "relatif" : cible = battre la médiane de l'univers sur 5 jours ---
# Features exprimées en RANG cross-sectionnel par date (suffixe _cs) : elles
# retirent l'effet de marché commun et se comparent d'un régime à l'autre.
# mom_12_1 = momentum 12 mois hors dernier mois (effet le plus stable mesuré
# sur l'historique), vol_relative = volume relatif (IC le plus significatif),
# daily_return / mom_5j = retournement court terme (IC négatif).
CS_BASE = ['daily_return', 'mom_5j', 'mom_20j', 'mom_60j', 'mom_12_1',
           'pct_vs_ma50', 'volatility', 'vol_relative', 'rsi_14']
FEATURES_RELATIF = [f + '_cs' for f in CS_BASE] + ['vix_regime']
