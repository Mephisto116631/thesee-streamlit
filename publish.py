# publish.py
# ==============================================================================
# PUBLICATION DES TABLES "PRÊTES À AFFICHER" — exécuté par le cron
# ==============================================================================
# L'appli mobile (APK / PWA) ne fait AUCUN calcul lourd : elle lit des tables
# Supabase déjà calculées ici, à chaque run du cron :
#   screener_snapshot, sector_medians, signals, model_runs, market_overview
# Les fourchettes d'interprétation sont dans ranges.json (partagé avec l'appli).
# ==============================================================================
import json
import math

import numpy as np
import pandas as pd

import data_pipeline as dp
import db
import universe
import utils


# ------------------------------------------------------------------------------
# Utilitaires
# ------------------------------------------------------------------------------
def _clean(obj):
    """Convertit récursivement numpy/pandas/NaN en types JSON natifs (NaN -> None)."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if obj is None or obj is pd.NA or obj is pd.NaT:
        return None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.date().isoformat()
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return obj


def _records(df: pd.DataFrame) -> list[dict]:
    return [_clean(r) for r in df.to_dict(orient="records")]


def _rsi(close: pd.Series) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    down = delta.clip(upper=0).abs().ewm(com=13, adjust=False).mean()
    return 100 - (100 / (1 + (up / down.replace(0, np.inf))))


def verdict_modele(gain_pts: float | None) -> str:
    """Même bornes que ranges.json > gain_pts."""
    if gain_pts is None:
        return "aucun"
    if gain_pts <= 0:
        return "aucun"
    if gain_pts <= 2:
        return "bruit"
    return "signal"


# ------------------------------------------------------------------------------
# 1. Indicateurs du dernier jour par ticker
# ------------------------------------------------------------------------------
def indicateurs_derniere_seance(market_raw: pd.DataFrame) -> pd.DataFrame:
    lignes = []
    for sym, g in market_raw.groupby("symbol"):
        g = g.sort_values("date")
        c = g["close"].astype(float)
        if len(c) < 2 or pd.isna(c.iloc[-1]):
            continue
        last = c.iloc[-1]

        def chg(n):
            return last / c.iloc[-1 - n] - 1 if len(c) > n and c.iloc[-1 - n] else None

        ret = c.pct_change()
        fen_1y = c.iloc[-252:]
        ma50 = c.rolling(50).mean().iloc[-1]
        ma200 = c.rolling(200).mean().iloc[-1]
        lignes.append({
            "symbol": sym,
            "date": pd.Timestamp(g["date"].iloc[-1]).date().isoformat(),
            "close": last,
            "chg_1d": chg(1),
            "chg_5d": chg(5),
            "chg_20d": chg(20),
            "chg_1y": chg(252),
            "rsi_14": _rsi(c).iloc[-1],
            "volatility": ret.iloc[-20:].std() * np.sqrt(252),
            "pct_vs_ma50": (last - ma50) / ma50 if ma50 and not pd.isna(ma50) else None,
            "pct_vs_ma200": (last - ma200) / ma200 if ma200 and not pd.isna(ma200) else None,
            "high_52w": fen_1y.max(),
            "low_52w": fen_1y.min(),
        })
    return pd.DataFrame(lignes)


# ------------------------------------------------------------------------------
# 2. Signaux IA du jour + explication SHAP
# ------------------------------------------------------------------------------
def signaux_du_jour(model_result: dict, features_df: pd.DataFrame, kind: str, top_n: int = 5) -> pd.DataFrame:
    model = model_result.get("model")
    if model is None or features_df.empty:
        return pd.DataFrame()
    feat = model_result["features"]
    derniers = features_df.sort_values("date").groupby("symbol").tail(1).reset_index(drop=True)
    X_raw = derniers[feat].values
    X = model_result["scaler"].transform(model_result["imputer"].transform(X_raw))
    proba = model.predict_proba(X)[:, 1]

    try:
        import shap
        shap_vals = shap.TreeExplainer(model)(X).values
    except Exception as e:  # SHAP est un bonus : le signal reste publié sans
        print(f"[PUBLISH][WARN] SHAP indisponible ({e})")
        shap_vals = np.zeros_like(X)

    lignes = []
    for i, row in derniers.iterrows():
        ordre = np.argsort(-np.abs(shap_vals[i]))[:top_n]
        facteurs = [{
            "feature": feat[j],
            "label": utils.FEATURE_LABELS.get(feat[j], feat[j]),
            "valeur": X_raw[i][j],
            "impact": shap_vals[i][j],
        } for j in ordre]
        lignes.append({
            "symbol": row["symbol"],
            "kind": kind,
            "date": pd.Timestamp(row["date"]).date().isoformat(),
            "proba_hausse": proba[i],
            "facteurs": _clean(facteurs),
        })
    return pd.DataFrame(lignes)


def ligne_model_run(model_result: dict, kind: str) -> dict:
    diag = model_result.get("diagnostics") or {}
    gain = diag.get("amelioration_vs_baseline")
    importance = []
    if model_result.get("model") is not None:
        imp = model_result["model"].feature_importances_
        importance = sorted(
            [{"feature": f, "label": utils.FEATURE_LABELS.get(f, f), "importance": float(v)}
             for f, v in zip(model_result["features"], imp)],
            key=lambda d: -d["importance"],
        )
    return _clean({
        "kind": kind,
        "trained_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "accuracy": diag.get("accuracy"),
        "baseline": diag.get("baseline_accuracy"),
        "gain_pts": gain,
        "verdict": verdict_modele(gain),
        "importance": importance,
        "diagnostics": diag,
    })


# ------------------------------------------------------------------------------
# 3. Vue d'ensemble du marché
# ------------------------------------------------------------------------------
def _stats_spread(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {}
    s = df.set_index("date")["valeur"].astype(float) * 100  # % -> points de base
    s = s[s.index >= s.index.max() - pd.Timedelta(days=3652)]
    actuel = s.iloc[-1]
    return {
        "bp": actuel,
        "pct": float((s <= actuel).mean() * 100),
        "min": s.min(), "med": s.median(), "max": s.max(),
    }


def ligne_overview(macro_raw: pd.DataFrame, snapshot: pd.DataFrame, spreads: dict) -> dict:
    vix = None
    if not macro_raw.empty and "^VIX" in set(macro_raw["symbol"]):
        vix = float(macro_raw[macro_raw["symbol"] == "^VIX"].sort_values("date")["close"].iloc[-1])
    actions = snapshot[~snapshot["is_etf"]] if not snapshot.empty else snapshot
    hy = _stats_spread(spreads.get("hy"))
    ig = _stats_spread(spreads.get("ig"))
    return _clean({
        "id": 1,
        "date": snapshot["date"].max() if not snapshot.empty else None,
        "vix": vix,
        "vix_regime": dp._calc_vix_regime(vix) if vix is not None else None,
        "hy_spread_bp": hy.get("bp"), "hy_pct_10y": hy.get("pct"),
        "hy_min_10y": hy.get("min"), "hy_med_10y": hy.get("med"), "hy_max_10y": hy.get("max"),
        "ig_spread_bp": ig.get("bp"), "ig_pct_10y": ig.get("pct"),
        "ig_min_10y": ig.get("min"), "ig_med_10y": ig.get("med"), "ig_max_10y": ig.get("max"),
        "pct_above_ma50": float((actions["pct_vs_ma50"] > 0).mean() * 100) if not actions.empty else None,
        "pct_above_ma200": float((actions["pct_vs_ma200"] > 0).mean() * 100) if not actions.empty else None,
        "n_hausse_1d": int((actions["chg_1d"] > 0).sum()) if not actions.empty else 0,
        "n_baisse_1d": int((actions["chg_1d"] < 0).sum()) if not actions.empty else 0,
        "updated_at": pd.Timestamp.now(tz="UTC").isoformat(),
    })


# ------------------------------------------------------------------------------
# 4. Point d'entrée
# ------------------------------------------------------------------------------
def construire_snapshot(data: dict, univers_df: pd.DataFrame, signals_df: pd.DataFrame) -> pd.DataFrame:
    ind = indicateurs_derniere_seance(data["market_data_raw"])
    if ind.empty:
        return ind
    snap = univers_df[["symbol", "nom", "secteur", "indice"]].merge(ind, on="symbol", how="inner")
    snap["is_etf"] = snap["symbol"].isin(universe.ETFS_SECTORIELS.keys())

    fonda = data["fonda_data_clean"]
    if not fonda.empty:
        f = fonda[["symbol", "roe", "margin", "ev_ebitda", "debt_eq"]].copy()
        # Alpha Vantage renvoie 0.0 quand la donnée manque : on ne l'affiche pas comme un vrai 0
        f[["roe", "margin", "ev_ebitda", "debt_eq"]] = f[["roe", "margin", "ev_ebitda", "debt_eq"]].replace(0.0, np.nan)
        snap = snap.merge(f, on="symbol", how="left")
    z = data["zscore_df"]
    if not z.empty:
        snap = snap.merge(z[["symbol", "z_score"]], on="symbol", how="left")
    r = data["ratings_df"]
    if not r.empty:
        snap = snap.merge(r[["symbol", "rating_sp"]], on="symbol", how="left")
    if not signals_df.empty:
        snap = snap.merge(signals_df[["symbol", "proba_hausse"]], on="symbol", how="left")

    for col in ["roe", "margin", "ev_ebitda", "debt_eq", "z_score", "rating_sp", "proba_hausse"]:
        if col not in snap.columns:
            snap[col] = None
    snap["updated_at"] = pd.Timestamp.now(tz="UTC").isoformat()
    return snap


def construire_medianes(snapshot: pd.DataFrame) -> pd.DataFrame:
    actions = snapshot[~snapshot["is_etf"]]
    cols = ["chg_20d", "chg_1y", "rsi_14", "volatility", "roe", "margin", "ev_ebitda", "debt_eq"]
    med = actions.groupby("secteur")[cols].median(numeric_only=True)
    med["n"] = actions.groupby("secteur").size()
    med = med.reset_index()
    med["updated_at"] = pd.Timestamp.now(tz="UTC").isoformat()
    return med


def publier(data: dict, univers_df: pd.DataFrame, spreads: dict) -> dict:
    """Calcule et écrit toutes les tables d'affichage. Retourne un résumé (logs)."""
    symboles_etf = set(universe.ETFS_SECTORIELS.keys())
    raw = data["market_data_raw"]
    macro = data["macro_data_raw"]

    # Features AVEC la dernière séance (le signal du jour porte sur demain)
    feats_actions = dp.build_features(raw[~raw["symbol"].isin(symboles_etf)], macro,
                                      utils.dict_secteurs, data["fonda_data_clean"], garder_dernier=True)
    feats_etf = dp.build_features_etf(raw[raw["symbol"].isin(symboles_etf)], macro, garder_dernier=True)

    sig = pd.concat([
        signaux_du_jour(data["model_result"], feats_actions, "actions"),
        signaux_du_jour(data["model_result_etf"], feats_etf, "etf"),
    ], ignore_index=True)

    snap = construire_snapshot(data, univers_df, sig)
    med = construire_medianes(snap) if not snap.empty else pd.DataFrame()
    overview = ligne_overview(macro, snap, spreads)

    db.upsert_rows("screener_snapshot", _records(snap), on_conflict="symbol")
    db.delete_where_not_in("screener_snapshot", "symbol", snap["symbol"].tolist() if not snap.empty else [])
    db.upsert_rows("sector_medians", _records(med), on_conflict="secteur")
    db.upsert_rows("signals", _records(sig), on_conflict="symbol")
    db.upsert_rows("model_runs", [ligne_model_run(data["model_result"], "actions"),
                                  ligne_model_run(data["model_result_etf"], "etf")], on_conflict="kind")
    db.upsert_rows("market_overview", [overview], on_conflict="id")

    return {"snapshot": len(snap), "secteurs": len(med), "signaux": len(sig)}


if __name__ == "__main__":
    print(json.dumps(_clean({"exemple": np.float64("nan")})))
