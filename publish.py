# publish.py
# ==============================================================================
# PUBLICATION DES TABLES "PRÊTES À AFFICHER" — exécuté par le cron
# ==============================================================================
# L'appli mobile (APK / PWA) ne fait AUCUN calcul lourd : elle lit des tables
# Supabase déjà calculées ici, à chaque run du cron :
#   titres_snapshot, sector_medians, signals, model_runs, market_overview
# Les fourchettes d'interprétation sont dans ranges.json (partagé avec l'appli).
# ==============================================================================
import json
import math

import numpy as np
import pandas as pd

import data_pipeline as dp
import db
import fondamentaux_sec as fsec
import modele_horizon
import modele_risque
import portefeuille
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


def taux_eurusd() -> float | None:
    """Dernier cours EUR/USD (Yahoo). Sert à convertir le plan d'achat en euros."""
    try:
        fx = dp.yf.download("EURUSD=X", period="10d", progress=False, auto_adjust=False)
        close = fx["Close"].dropna()
        v = close.iloc[-1]
        return float(v.iloc[0] if hasattr(v, "iloc") else v)
    except Exception as e:
        print(f"[PUBLISH][WARN] EUR/USD indisponible : {e}")
        return None


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
        "eurusd": taux_eurusd(),
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


# ------------------------------------------------------------------------------
# Volatilité prévue par l'IA : publiée SEULEMENT si sa preuve tient toujours
# ------------------------------------------------------------------------------
def filtrer_vol_ia(vol_ia: pd.Series, fiabilite: dict) -> pd.Series | None:
    """Garde-fou : la prévision n'est montrée dans l'appli que si le DERNIER test du
    laboratoire est probant. Sinon None : l'appli revient d'elle-même à l'historique."""
    if not fiabilite.get("probant") or vol_ia is None or vol_ia.dropna().empty:
        return None
    return vol_ia.dropna()


def _cours(raw: pd.DataFrame) -> pd.DataFrame:
    px = raw.pivot_table(index="date", columns="symbol", values="close")
    px.index = pd.to_datetime(px.index)
    return px.sort_index()


def suivre_volatilite(vol_ia: pd.Series, raw: pd.DataFrame, date_marche, fiabilite: dict) -> dict:
    """Enregistre la prévision une fois par semaine (table suivi_volatilite), puis compare les
    prévisions vieilles de 6 mois à la volatilité réellement observée. Résultat -> model_runs."""
    cli = db.get_client()
    px = _cours(raw)
    date_marche = pd.Timestamp(date_marche)
    derniere = cli.table("suivi_volatilite").select("date").order("date", desc=True).limit(1).execute().data
    if vol_ia is not None and not vol_ia.dropna().empty and (
            not derniere or (date_marche - pd.Timestamp(derniere[0]["date"])).days >= 7):
        vol_3m = px.pct_change().iloc[-63:].std() * np.sqrt(252)
        lignes = [{"date": str(date_marche.date()), "symbol": s, "vol_prevue": float(v),
                   "vol_3m": float(vol_3m[s]) if s in vol_3m and pd.notna(vol_3m[s]) else None}
                  for s, v in vol_ia.dropna().items()]
        db.upsert_rows("suivi_volatilite", lignes, on_conflict="date,symbol")
        print(f"[PUBLISH] Suivi réel : {len(lignes)} prévisions enregistrées au {date_marche.date()}")
    # Seules les prévisions de plus de ~6 mois peuvent être jugées : inutile de lire les autres
    premiere = cli.table("suivi_volatilite").select("date").order("date").limit(1).execute().data
    limite = str((date_marche - pd.Timedelta(days=170)).date())
    suivi = pd.DataFrame(db._select_all(lambda: cli.table("suivi_volatilite").select("date,symbol,vol_prevue,vol_3m")
                                        .lte("date", limite).order("date").order("symbol")))
    bilan = modele_risque.bilan_reel(suivi, px, premiere[0]["date"] if premiere else None)
    db.upsert_rows("model_runs", [_clean({
        "kind": "risque_volatilite_reel",
        "trained_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "verdict": bilan.get("verdict", "en attente"),
        "diagnostics": {"labo": fiabilite, "reel": bilan, "vol_ia_publiee": bool(fiabilite.get("probant"))},
    })], on_conflict="kind")
    return bilan


# ------------------------------------------------------------------------------
# Valorisation : comptes officiels déposés à la SEC (une fois par semaine)
# ------------------------------------------------------------------------------
COLONNES_MEDIANES_SEC = {"per": "per", "cours_vc": "cours_vc", "roe_sec": "roe_sec",
                         "rentabilite_brute": "rentabilite_brute", "endettement": "endettement",
                         "part_encaissee": "part_encaissee"}


def medianes_valorisation(valo: pd.DataFrame, snap: pd.DataFrame) -> pd.DataFrame:
    """Médiane par secteur des ratios SEC (PER et cours / valeur comptable au cours du jour)."""
    v = valo.merge(snap[~snap["is_etf"]][["symbol", "secteur", "close"]], on="symbol")
    v["per"] = (v["close"] / v["bpa_sec"]).where(v["bpa_sec"] > 0)
    v["cours_vc"] = (v["close"] / v["vc_action_sec"]).where(v["vc_action_sec"] > 0)
    med = v.groupby("secteur")[list(COLONNES_MEDIANES_SEC)].median(numeric_only=True).reset_index()
    return med


def publier_valorisation_sec(snap: pd.DataFrame, force: bool = False) -> int:
    """Télécharge les comptes SEC (≈ 5 min) si la dernière mise à jour date de plus de 6 jours."""
    import os
    if not os.environ.get("SEC_USER_AGENT", "").strip():
        print("[PUBLISH][WARN] SEC_USER_AGENT absent : valorisation SEC non mise à jour.")
        return 0
    cli = db.get_client()
    force = force or os.environ.get("SEC_FORCER") == "1"   # lancement manuel « forcer les comptes SEC »
    if not force:
        d = cli.table("titres_snapshot").select("sec_maj").not_.is_("sec_maj", "null") \
            .order("sec_maj", desc=True).limit(1).execute().data
        if d and pd.Timestamp.now(tz="UTC") - pd.Timestamp(d[0]["sec_maj"]) < pd.Timedelta(days=6):
            return 0
    actions = snap[~snap["is_etf"]]["symbol"].tolist()
    faits = fsec.telecharger(actions)
    splits = fsec.divisions_recentes(actions, str((pd.Timestamp.now() - pd.Timedelta(days=730)).date()))
    valo = fsec.valorisation_actuelle(faits, snap.set_index("symbol")["close"], splits)
    if valo.empty:
        return 0
    # Diagnostic : comptes lus mais aucun bénéfice exploitable -> on montre ce que la SEC a fourni
    sans = valo[valo["bpa_sec"].isna() & valo["roe_sec"].isna()]["symbol"].tolist()
    if sans:
        print(f"[PUBLISH][SEC] Sans bénéfice exploitable : {', '.join(sans)}")
        rn = faits[(faits["variable"].isin(["resultat_net", "bpa", "actions"])) & faits["symbol"].isin(sans[:15])]
        for s, g in rn.sort_values("filed").groupby("symbol"):
            print(f"[PUBLISH][SEC]   {s} : " + " ; ".join(
                f"{r.variable} fin {pd.Timestamp(r.end).date()} publié {pd.Timestamp(r.filed).date()} = {r.val:.4g}"
                for r in g.groupby("variable").tail(2).itertuples()))
    maj = pd.Timestamp.now(tz="UTC").isoformat()
    lignes = valo.assign(comptes_date=valo["comptes_date"].dt.strftime("%Y-%m-%d"), sec_maj=maj)
    db.upsert_rows("titres_snapshot", _records(lignes), on_conflict="symbol")
    db.upsert_rows("sector_medians", _records(medianes_valorisation(valo, snap)), on_conflict="secteur")
    print(f"[PUBLISH] Valorisation SEC : {valo['bpa_sec'].notna().sum()} PER, "
          f"{valo['roe_sec'].notna().sum()} ROE sur {len(valo)} entreprises")
    return len(valo)


def publier(data: dict, univers_df: pd.DataFrame, spreads: dict) -> dict:
    """Calcule et écrit toutes les tables d'affichage. Retourne un résumé (logs)."""
    symboles_etf = set(universe.ETFS_SECTORIELS.keys())
    raw = data["market_data_raw"]
    macro = data["macro_data_raw"]

    modele_1j = data["model_result"].get("model") is not None
    sig = pd.DataFrame()
    if modele_1j:
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

    db.upsert_rows("titres_snapshot", _records(snap), on_conflict="symbol")
    db.delete_where_not_in("titres_snapshot", "symbol", snap["symbol"].tolist() if not snap.empty else [])
    db.upsert_rows("sector_medians", _records(med), on_conflict="secteur")
    if modele_1j:
        db.upsert_rows("signals", _records(sig), on_conflict="symbol")
        db.upsert_rows("model_runs", [ligne_model_run(data["model_result"], "actions"),
                                      ligne_model_run(data["model_result_etf"], "etf")], on_conflict="kind")
    db.upsert_rows("market_overview", [overview], on_conflict="id")

    # Valorisation (PER, ROE…) depuis les comptes officiels SEC : une fois par semaine
    try:
        db.progression(62, "Comptes officiels (SEC)")
        publier_valorisation_sec(snap)
    except Exception as e:
        print(f"[PUBLISH][WARN] Valorisation SEC non mise à jour : {e}")

    # Modèles « horizon » (1 mois, 6 mois, 1 an) : classement relatif des titres
    # Sur l'historique long (depuis 2005, non stocké) : bien plus de périodes de test indépendantes.
    raw_long = dp.historique_long()
    raw_horizon = raw_long if raw_long is not None and not raw_long.empty else raw
    composition = modele_horizon.charger_composition()   # membres réels de l'indice à chaque date
    n_scores = 0
    for k, nom in enumerate(modele_horizon.HORIZONS):
        db.progression(65 + 10 * k, f"Modèle IA {dict(court='1 mois', **{'6m': '6 mois', '1a': '1 an'})[nom]}")
        try:
            ligne, scores = modele_horizon.entrainer_horizon(
                raw_horizon, snap["symbol"].tolist(), nom, composition, dict(zip(snap["symbol"], snap["secteur"])))
            if ligne:
                db.upsert_rows("model_runs", [_clean(ligne)], on_conflict="kind")
                db.upsert_rows("scores_horizon", _records(scores), on_conflict="symbol,horizon")
                n_scores += len(scores)
                d = ligne["diagnostics"]
                print(f"[PUBLISH] Modèle {nom} : IC {d.get('ic_moyen', 0):.3f} (t={d.get('t_stat', 0):.1f}, "
                      f"momentum seul {d.get('ic_momentum') or 0:.3f}) -> {ligne['verdict']}")
        except Exception as e:
            print(f"[PUBLISH][WARN] Modèle horizon {nom} non calculé : {e}")

    # Volatilité prévue par l'IA de risque (6 mois) : calculée et SUIVIE à chaque passage,
    # mais montrée dans l'appli seulement si le dernier test du laboratoire est probant.
    vol_publiee = None
    try:
        db.progression(93, "Volatilité prévue par l'IA")
        lab = db.get_client().table("experiences").select("nom,horizon,verdict,t_stat,seuil_t_global,diagnostics,cree_le") \
            .eq("nom", modele_risque.NOM_LABO).eq("horizon", "6m").order("cree_le", desc=True).limit(1).execute().data
        fiab = modele_risque.verdict_labo(lab)
        vol_ia = modele_risque.predire_volatilite(raw_horizon, snap["symbol"].tolist(), composition)
        vol_publiee = filtrer_vol_ia(vol_ia, fiab)
        if vol_publiee is None:
            # Preuve tombée : on efface les anciennes valeurs, l'appli revient à l'historique
            db.get_client().table("titres_snapshot").update({"vol_ia": None}).not_.is_("vol_ia", "null").execute()
            print(f"[PUBLISH] Volatilité IA NON publiée : dernier test « {fiab.get('verdict')} »")
        else:
            db.upsert_rows("titres_snapshot", [{"symbol": s, "vol_ia": float(v)} for s, v in vol_publiee.items()],
                           on_conflict="symbol")
            print(f"[PUBLISH] Volatilité IA : {len(vol_publiee)} titres (test t {fiab.get('t_stat', 0):.1f} "
                  f"> seuil {fiab.get('seuil', 0):.1f})")
        bilan = suivre_volatilite(vol_ia, raw, snap["date"].max(), fiab)
        print(f"[PUBLISH] Bilan réel : {bilan.get('verdict', 'en attente')} "
              f"({bilan.get('n_dates', 0)} dates jugées, premier bilan {bilan.get('premier_bilan')})")
    except Exception as e:
        print(f"[PUBLISH][WARN] Volatilité IA non calculée : {e}")

    # Portefeuille recommandé : bonus, ne doit jamais faire échouer la publication
    n_lignes = 0
    try:
        db.progression(97, "Portefeuille recommandé")
        reco = portefeuille.portefeuille_recommande(raw, snap)
        if reco:
            if vol_publiee is not None:
                syms = reco.get("univers", {}).get("symbols", [])
                if syms:
                    reco["univers"]["vol_ia"] = [float(vol_publiee[s]) if s in vol_publiee else None for s in syms]
                for s, t in (reco.get("titres") or {}).items():
                    if s in vol_publiee:
                        t["vol_ia"] = float(vol_publiee[s])
            db.upsert_rows("portefeuille_recommande", [_clean({
                "id": 1, "date": snap["date"].max(), **reco,
                "updated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            })], on_conflict="id")
            n_lignes = len(reco["lignes"])
    except Exception as e:
        print(f"[PUBLISH][WARN] Portefeuille recommandé non calculé : {e}")

    return {"snapshot": len(snap), "secteurs": len(med), "signaux": len(sig), "portefeuille": n_lignes, "scores_horizon": n_scores}


if __name__ == "__main__":
    print(json.dumps(_clean({"exemple": np.float64("nan")})))
