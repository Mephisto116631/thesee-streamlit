# scripts/update_market_data.py
import os
import yfinance as yf
import pandas as pd
import sys

# On ajoute le dossier parent au path pour pouvoir importer db.py et utils.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
import utils

def download_and_upsert():
    tickers = utils.actifs_sp500
    print(f"Téléchargement des données pour {len(tickers)} tickers...")
    
    # 1. Téléchargement via Yahoo Finance
    data = yf.download(tickers, start="2020-01-01", progress=False)
    data = data.stack(level=1, future_stack=True).rename_axis(["Date", "symbol"]).reset_index()
    data.columns = [c.lower() for c in data.columns]
    data = data.rename(columns={"date": "date"})
    data = data[["symbol", "date", "open", "high", "low", "close", "volume"]]
    
    # Formatage strict pour Supabase
    data["volume"] = pd.to_numeric(data["volume"], errors="coerce").fillna(0).astype("int64")
    for col in ["open", "high", "low", "close"]:
        data[col] = pd.to_numeric(data[col], errors="coerce")
        
    # 2. Upsert dans Supabase
    print("Envoi vers Supabase...")
    db.upsert_market_data(data)
    print("Mise à jour terminée avec succès.")

if __name__ == "__main__":
    download_and_upsert()
  
