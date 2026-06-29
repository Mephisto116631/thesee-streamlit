# pages/2_Portefeuille.py
# ==============================================================================
# MODULE : PORTEFEUILLE (Markowitz & Monte-Carlo)
# ==============================================================================
import streamlit as st
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from theme import apply_theme
import data_pipeline as dp
import utils

st.set_page_config(page_title="Portefeuille — Thésée", page_icon="💼", layout="wide")
apply_theme()

st.title("💼 Portefeuille")

if "thesee_data" not in st.session_state:
    st.session_state["thesee_data"] = dp.get_all_data()
data = st.session_state["thesee_data"]
market_data_raw = data["market_data_raw"]

with st.sidebar:
    st.subheader("Configuration")
    actifs = st.multiselect("Sélection des actifs :", utils.actifs_sp500, default=["AAPL", "MSFT", "NVDA"])
    capital = st.number_input("Capital initial (EUR) :", min_value=100, value=10000, step=100)
    weight_mode = st.radio("Méthode d'optimisation :", ["Équipondéré", "Markowitz"])
    lancer_mc = st.button("🎲 Lancer Monte-Carlo", use_container_width=True)


def calc_weights(actifs, weight_mode, market_data_raw):
    if not actifs:
        return pd.DataFrame()

    df = market_data_raw[market_data_raw["symbol"].isin(actifs)].copy()
    df["daily_return"] = df.groupby("symbol")["close"].pct_change()
    returns_matrix = df.pivot_table(index="date", columns="symbol", values="daily_return").dropna()
    N = len(returns_matrix.columns)

    if weight_mode == "Équipondéré" or N < 2:
        w = np.ones(N) / N
    else:
        try:
            cov_matrix = returns_matrix.cov() * 252
            inv_cov = np.linalg.inv(cov_matrix.values)
            w = inv_cov.dot((returns_matrix.mean() * 252).values - 0.0435)
            w[w < 0] = 0
            w = w / np.sum(w) if np.sum(w) > 0 else np.ones(N) / N
        except Exception:
            w = np.ones(N) / N

    return pd.DataFrame({
        "Ticker": returns_matrix.columns,
        "Poids (%)": np.round(w * 100, 2),
        "Allocation (EUR)": np.round(w * capital, 2),
    }).sort_values(by="Poids (%)", ascending=False)


weights_df = calc_weights(actifs, weight_mode, market_data_raw)

st.subheader("Poids & Ordres")
if weights_df.empty:
    st.info("Sélection requise.")
else:
    st.dataframe(weights_df, use_container_width=True, hide_index=True)

st.subheader("Simulation Monte-Carlo (252j)")

if lancer_mc and not weights_df.empty:
    df = market_data_raw[market_data_raw["symbol"].isin(actifs)].copy()
    returns_matrix = (
        df.assign(ret=df.groupby("symbol")["close"].pct_change())
        .pivot_table(index="date", columns="symbol", values="ret")
        .dropna()
    )
    weights = weights_df.set_index("Ticker").loc[returns_matrix.columns]["Poids (%)"].values / 100
    port_returns = returns_matrix.dot(weights).values

    rng = np.random.default_rng(seed=42)
    simulations = rng.choice(port_returns, size=(252, 500), replace=True)
    trajectories = capital * np.cumprod(1 + simulations, axis=0)

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#1e293b")
    ax.set_facecolor("#1e293b")

    x = np.arange(252)
    ax.fill_between(x, np.percentile(trajectories, 5, axis=1), np.percentile(trajectories, 95, axis=1),
                     color="#3b82f6", alpha=0.25)
    ax.plot(x, np.percentile(trajectories, 50, axis=1), color="#f59e0b", linewidth=2)

    ax.tick_params(colors="#e2e8f0")
    ax.set_xlabel("Jours", color="#cbd5e1")
    ax.set_ylabel("Valeur", color="#cbd5e1")
    for spine in ax.spines.values():
        spine.set_color("#475569")

    st.pyplot(fig, use_container_width=True)
elif not lancer_mc:
    st.caption("Clique sur « Lancer Monte-Carlo » dans la barre latérale pour générer la simulation.")
else:
    st.info("Sélection d'actifs requise pour la simulation.")
