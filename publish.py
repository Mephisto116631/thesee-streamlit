# publish.py
# ==============================================================================
# PUBLICATION DES TABLES "PRÊTES À AFFICHER" — exécuté par le cron
# ==============================================================================
# L'appli mobile (APK / PWA) ne fait AUCUN calcul lourd : elle lit des tables
# Supabase déjà calculées ici, à chaque run du cron :
#   titres_snapshot, sector_medians, model_runs, scores_horizon, market_overview, portefeuille_recommande…
# Les fourchettes d'interprétation sont dans ranges.json (partagé avec l'appli).
# ==============================================================================
import json
import math

import numpy as np
import pandas as pd

import data_pipeline as dp
import db
import fondamentaux_sec as fsec
import fred
import modele_horizon
import modele_risque
import portefeuille
import universe


# ------------------------------------------------------------------------------
# Utilitaires
# ------------------------------------------------------------------------------
# Étapes « bonus » qui ont échoué pendant ce passage : la publication continue, mais le passage est
# marqué « partiel » dans sync_log (au lieu de « success ») pour qu'une panne ne passe pas inaperçue.
AVERTISSEMENTS: list[str] = []


def avertir(msg: str) -> None:
    """Note un échec non bloquant : affiché dans le journal du cron ET remonté dans sync_log."""
    print(f"[PUBLISH][WARN] {msg}")
    AVERTISSEMENTS.append(str(msg)[:300])


def dernier_essai(nom: str, colonnes: str, horizon: str | None = None) -> list[dict]:
    """Dernier essai enregistré du laboratoire (table `experiences`) pour `nom` : [] s'il n'y en a pas.
    Tri par identifiant (ordre d'insertion), le même pour toutes les lectures du laboratoire."""
    q = db.get_client().table("experiences").select(colonnes).eq("nom", nom)
    if horizon is not None:
        q = q.eq("horizon", horizon)
    return q.order("id", desc=True).limit(1).execute().data or []


# Au-delà de cette part de titres à retirer d'un coup, on suppose une panne (Yahoo, liste de l'indice
# tombée sur sa liste de secours…) plutôt qu'une vraie sortie de l'indice : on ne supprime rien.
PART_MAX_SUPPRESSION = 0.05


def titres_a_retirer(existants: list[str], a_garder: list[str], part_max: float = PART_MAX_SUPPRESSION) -> list[str]:
    """Titres présents en base mais absents de `a_garder`. Lève ValueError si la suppression
    toucherait plus de `part_max` des titres existants (au moins 10 titres) : signe d'une panne."""
    existants = sorted(set(existants))
    retirer = sorted(set(existants) - set(a_garder))
    if not a_garder:
        raise ValueError("liste des titres à garder vide")
    if len(retirer) > max(10, part_max * len(existants)):
        raise ValueError(f"{len(retirer)} titres sur {len(existants)} à retirer d'un coup")
    return retirer


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
# 2. Vue d'ensemble du marché
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
        avertir(f"EUR/USD indisponible : {e}")
        return None


def vix_long(debut: str = "1998-01-01") -> pd.Series:
    """Clôtures du VIX depuis `debut` (Yahoo), index de dates sans fuseau : entrée du risque du mois à venir."""
    v = dp.yf.download("^VIX", start=debut, progress=False, auto_adjust=False)["Close"]
    v = (v.iloc[:, 0] if isinstance(v, pd.DataFrame) else v).dropna()
    v.index = pd.to_datetime(v.index).tz_localize(None)
    return v


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
# 3. Instantané par titre et point d'entrée
# ------------------------------------------------------------------------------
def construire_snapshot(data: dict, univers_df: pd.DataFrame) -> pd.DataFrame:
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
    # proba_hausse : ancien modèle « hausse demain », retiré (non probant) ; la colonne est vidée
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


def suivre_risque_mois(vol_harx: pd.Series, vol_har: pd.Series, raw: pd.DataFrame, date_marche) -> dict:
    """§ 4.18 : enregistre une fois par semaine les prévisions à 22 séances (HAR-X et HAR seul) dans `suivi_risque_mois`,
    puis juge celles dont les 22 séances suivantes sont connues. Résultat -> model_runs (kind risque_mois_reel)."""
    cli = db.get_client()
    date_marche = pd.Timestamp(date_marche)
    derniere = cli.table("suivi_risque_mois").select("date").order("date", desc=True).limit(1).execute().data
    if not derniere or (date_marche - pd.Timestamp(derniere[0]["date"])).days >= 7:
        lignes = [{"date": str(date_marche.date()), "symbol": s, "vol_harx": float(x), "vol_har": float(vol_har[s])}
                  for s, x in vol_harx.dropna().items() if s in vol_har.index and pd.notna(vol_har[s])]
        if lignes:
            db.upsert_rows("suivi_risque_mois", lignes, on_conflict="date,symbol")
            print(f"[PUBLISH] Suivi réel du mois : {len(lignes)} prévisions enregistrées au {date_marche.date()}")
    premiere = cli.table("suivi_risque_mois").select("date").order("date").limit(1).execute().data
    limite = str((date_marche - pd.Timedelta(days=32)).date())          # 22 séances ≈ 31 jours
    suivi = pd.DataFrame(db._select_all(lambda: cli.table("suivi_risque_mois").select("date,symbol,vol_harx,vol_har")
                                        .lte("date", limite).order("date").order("symbol")))
    bilan = modele_risque.bilan_reel_mois(suivi, _cours(raw), premiere[0]["date"] if premiere else None)
    db.upsert_rows("model_runs", [_clean({
        "kind": "risque_mois_reel", "trained_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "verdict": bilan.get("verdict", "en attente"), "diagnostics": bilan,
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
        avertir("SEC_USER_AGENT absent : valorisation SEC non mise à jour.")
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


def semestre(d) -> tuple[int, int]:
    d = pd.Timestamp(d)
    return d.year, (d.month - 1) // 6


def enregistrer_revision(reco: dict, date_marche) -> bool:
    """Fige l'univers du portefeuille une fois par semestre (janvier, juillet) : l'appli ne change le
    portefeuille conseillé qu'à ces révisions (docs/METHODE.md § 4.9). Retourne True si une révision est écrite."""
    u = reco.get("univers_facteurs")
    if not u:
        return False
    cli = db.get_client()
    der = cli.table("revisions_portefeuille").select("date").order("date", desc=True).limit(1).execute().data
    if der and semestre(der[0]["date"]) == semestre(date_marche):
        return False
    db.upsert_rows("revisions_portefeuille", [_clean({
        "date": pd.Timestamp(date_marche).date().isoformat(), "univers_facteurs": u,
        "titres": reco.get("titres"), "methode": reco.get("methode")})], on_conflict="date")
    print(f"[PUBLISH] Révision du portefeuille enregistrée au {pd.Timestamp(date_marche).date()}")
    return True


LIBELLES_HORIZON = {"court": "1 mois", "6m": "6 mois", "1a": "1 an"}


def publier(data: dict, univers_df: pd.DataFrame, spreads: dict) -> dict:
    """Calcule et écrit toutes les tables d'affichage, étape par étape. Seules les tables de base
    (instantané, médianes, vue d'ensemble) sont indispensables ; une étape suivante qui échoue est notée
    dans `avertissements` (passage « partiel ») sans arrêter les autres. Retourne un résumé (logs)."""
    AVERTISSEMENTS.clear()
    raw = data["market_data_raw"]
    snap = construire_snapshot(data, univers_df)
    med = construire_medianes(snap) if not snap.empty else pd.DataFrame()
    publier_tables_de_base(snap, med, ligne_overview(data["macro_data_raw"], snap, spreads))

    # Valorisation (PER, ROE…) depuis les comptes officiels SEC : une fois par semaine
    try:
        db.progression(62, "Comptes officiels (SEC)")
        publier_valorisation_sec(snap)
    except Exception as e:
        avertir(f"Valorisation SEC non mise à jour : {e}")

    # Historique long (depuis 2005, non stocké) : bien plus de périodes de test indépendantes
    raw_long = dp.historique_long()
    raw_horizon = raw_long if raw_long is not None and not raw_long.empty else raw
    composition = modele_horizon.charger_composition()   # membres réels de l'indice à chaque date

    n_scores = publier_modeles_horizon(raw_horizon, snap, composition)
    vol_publiee = publier_volatilite(raw, raw_horizon, snap, composition)
    n_lignes = publier_portefeuille(raw, raw_horizon, snap, composition, vol_publiee)
    return {"snapshot": len(snap), "secteurs": len(med), "portefeuille": n_lignes,
            "scores_horizon": n_scores, "avertissements": list(AVERTISSEMENTS)}


def publier_tables_de_base(snap: pd.DataFrame, med: pd.DataFrame, overview: dict) -> None:
    """Instantané par titre, médianes par secteur, vue d'ensemble du marché."""
    db.upsert_rows("titres_snapshot", _records(snap), on_conflict="symbol")
    # Ne retire que les titres sortis de l'indice, jamais une grosse part d'un coup (panne probable)
    try:
        existants = [r["symbol"] for r in db._select_all(
            lambda: db.get_client().table("titres_snapshot").select("symbol").order("symbol"))]
        retirer = titres_a_retirer(existants, snap["symbol"].tolist() if not snap.empty else [])
        db.delete_in("titres_snapshot", "symbol", retirer)
        if retirer:
            print(f"[PUBLISH] {len(retirer)} titres retirés (sortis de l'univers) : {', '.join(retirer[:20])}")
    except ValueError as e:
        avertir(f"Aucun titre retiré de titres_snapshot ({e}) : panne de téléchargement probable")
    db.upsert_rows("sector_medians", _records(med), on_conflict="secteur")
    db.upsert_rows("market_overview", [overview], on_conflict="id")


def publier_modeles_horizon(raw_horizon: pd.DataFrame, snap: pd.DataFrame, composition) -> int:
    """Modèles « horizon » (1 mois, 6 mois, 1 an) : classement relatif des titres. Retourne le nombre de scores."""
    n_scores = 0
    for k, nom in enumerate(modele_horizon.HORIZONS):
        db.progression(65 + 10 * k, f"Modèle IA {LIBELLES_HORIZON.get(nom, nom)}")
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
            avertir(f"Modèle horizon {nom} non calculé : {e}")
    return n_scores


def source_volatilite() -> dict:
    """Fiabilité et source de la prévision de volatilité, d'après les derniers essais du laboratoire.
    Source (docs/METHODE.md § 4.9) : « examen_hybride » décide entre l'hybride (ordre de l'IA, niveaux HAR)
    et HAR seul ; sans examen, l'IA seule. Règle 6 : si l'IA ne bat pas HAR sur l'ordre des titres, HAR seul."""
    lab = dernier_essai(modele_risque.NOM_LABO, "nom,horizon,verdict,t_stat,seuil_t_global,diagnostics,cree_le", "6m")
    fiab = modele_risque.verdict_labo(lab)
    ex_h = dernier_essai("examen_hybride", "diagnostics->decision,cree_le")
    decision = (ex_h[0].get("decision") if ex_h else None) or "ia"
    ex_r = dernier_essai("examen_ia_contre_har", "diagnostics->decision")
    if ex_r and ex_r[0].get("decision") == "har":
        decision = "har"
    fiab["source"] = {"hybride": "hybride", "har": "har"}.get(decision, "ia")
    if fiab["source"] == "har":
        fiab["probant"] = True       # HAR : méthode de référence retenue par l'examen, sans dépendre de l'IA
    return fiab


def publier_volatilite(raw: pd.DataFrame, raw_horizon: pd.DataFrame, snap: pd.DataFrame, composition) -> pd.Series | None:
    """Volatilité prévue à 6 mois : calculée et SUIVIE à chaque passage, mais montrée dans l'appli seulement
    si le dernier test du laboratoire est probant. Retourne la prévision publiée (None si non publiée)."""
    vol_publiee = None
    try:
        db.progression(93, "Volatilité prévue par l'IA")
        fiab = source_volatilite()
        niveaux = {"hybride": "har", "har": "har_seul"}.get(fiab["source"], "vol_3m")
        vol_ia = modele_risque.predire_volatilite(raw_horizon, snap["symbol"].tolist(), composition, niveaux=niveaux)
        vol_publiee = filtrer_vol_ia(vol_ia, fiab)
        if vol_publiee is None:
            # Preuve tombée : on efface les anciennes valeurs, l'appli revient à l'historique
            db.get_client().table("titres_snapshot").update({"vol_ia": None}).not_.is_("vol_ia", "null").execute()
            print(f"[PUBLISH] Volatilité IA NON publiée : dernier test « {fiab.get('verdict')} »")
        else:
            db.upsert_rows("titres_snapshot", [{"symbol": s, "vol_ia": float(v)} for s, v in vol_publiee.items()],
                           on_conflict="symbol")
            print(f"[PUBLISH] Volatilité prévue ({fiab['source']}) : {len(vol_publiee)} titres "
                  f"(test t {fiab.get('t_stat') or 0:.1f} > seuil {fiab.get('seuil') or 0:.1f})")
        bilan = suivre_volatilite(vol_ia, raw, snap["date"].max(), fiab)
        print(f"[PUBLISH] Bilan réel : {bilan.get('verdict', 'en attente')} "
              f"({bilan.get('n_dates', 0)} dates jugées, premier bilan {bilan.get('premier_bilan')})")
    except Exception as e:
        avertir(f"Volatilité IA non calculée : {e}")
    return vol_publiee


def ajouter_vol_publiee(reco: dict, vol_publiee: pd.Series | None) -> None:
    """Joint la volatilité prévue (si publiée) à l'univers et aux titres du portefeuille."""
    if vol_publiee is None:
        return
    syms = (reco.get("univers_facteurs") or {}).get("symbols", [])
    if syms:
        reco["univers_facteurs"]["vol_ia"] = [float(vol_publiee[s]) if s in vol_publiee else None for s in syms]
    for s, t in (reco.get("titres") or {}).items():
        if s in vol_publiee:
            t["vol_ia"] = float(vol_publiee[s])


def ajouter_stress_test(reco: dict, raw_horizon: pd.DataFrame) -> None:
    """Stress test (docs/METHODE.md § 14) : crises passées rejouées sur les titres d'aujourd'hui."""
    try:
        u = reco.get("univers_facteurs") or {}
        if u.get("symbols"):
            u["chocs"] = portefeuille.chocs_historiques(raw_horizon, u["symbols"])
            print(f"[PUBLISH] Stress test : {len((u['chocs'] or {}).get('crises', []))} crises rejouées")
    except Exception as e:
        avertir(f"Stress test non calculé : {e}")


def ajouter_risque_mois(reco: dict, raw: pd.DataFrame, raw_horizon: pd.DataFrame, snap: pd.DataFrame, composition) -> None:
    """Risque du mois à venir (docs/METHODE.md §§ 4.16-4.18) : publié seulement si la dernière confirmation
    du laboratoire est réussie et si HAR-X ne fait pas pire que HAR en conditions réelles."""
    try:
        u = reco.get("univers_facteurs") or {}
        ex_1m = dernier_essai(modele_risque.NOM_LABO_1M,
                              "decision:diagnostics->>decision,avert:diagnostics->avertissement_couverture,"
                              "part:diagnostics->midcaps->couverture->harx->part_depassements")
        if not (u.get("symbols") and ex_1m and ex_1m[0].get("decision") == "confirme"):
            print("[PUBLISH] Risque du mois à venir NON publié : confirmation absente ou non réussie")
            return
        vol_1m, vol_har_1m, info = modele_risque.niveaux_harx_1m_du_jour(raw_horizon, u["symbols"], vix_long(), composition)
        bilan_1m = suivre_risque_mois(vol_1m, vol_har_1m, raw, snap["date"].max())
        if bilan_1m.get("garde_fou"):
            print("[PUBLISH] Risque du mois à venir NON publié : moins bon que HAR en conditions réelles (§ 4.18)")
            return
        u["vol_1m"] = [float(vol_1m[s]) if s in vol_1m.index else None for s in u["symbols"]]
        u["info_1m"] = {**info, "avertissement": bool(ex_1m[0].get("avert")), "part_depassements": ex_1m[0].get("part"),
                        "reel": {k: bilan_1m.get(k) for k in ("verdict", "n_dates", "premier_bilan", "couverture_mauvais_cas")}}
        print(f"[PUBLISH] Risque du mois à venir : {len(vol_1m)} titres (VIX {info['vix']:.1f}) ; "
              f"réel : {bilan_1m.get('verdict')} ({bilan_1m.get('n_dates', 0)} dates jugées)")
    except Exception as e:
        avertir(f"Risque du mois à venir non calculé : {e}")


def taux_du_jour() -> tuple[float, str | None]:
    """Taux sans risque du jour (FRED, docs/METHODE.md § 2.1), ou la valeur de repli avec un avertissement."""
    try:
        lu = fred.taux_sans_risque()
    except Exception as e:
        lu = None
        print(f"[PUBLISH] Taux FRED illisible : {e}")
    if lu is None:
        avertir(f"Taux sans risque FRED indisponible : repli sur {portefeuille.RF:.2%}")
        return portefeuille.RF, None
    print(f"[PUBLISH] Taux sans risque : {lu[0]:.2%} au {lu[1]} (FRED {fred.SERIE_TAUX_3M})")
    return lu


def publier_portefeuille(raw: pd.DataFrame, raw_horizon: pd.DataFrame, snap: pd.DataFrame, composition,
                         vol_publiee: pd.Series | None) -> int:
    """Portefeuille recommandé, avec ses compléments (volatilité prévue, stress test, risque du mois).
    Ne fait jamais échouer la publication. Retourne le nombre de lignes du portefeuille."""
    try:
        db.progression(97, "Portefeuille recommandé")
        rf, date_rf = taux_du_jour()
        reco = portefeuille.portefeuille_recommande(raw, snap, rf=rf, date_rf=date_rf)
        if not reco:
            return 0
        ajouter_vol_publiee(reco, vol_publiee)
        ajouter_stress_test(reco, raw_horizon)
        ajouter_risque_mois(reco, raw, raw_horizon, snap, composition)
        enregistrer_revision(reco, snap["date"].max())
        db.upsert_rows("portefeuille_recommande", [_clean({
            "id": 1, "date": snap["date"].max(), **reco,
            "updated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        })], on_conflict="id")
        return len(reco["lignes"])
    except Exception as e:
        avertir(f"Portefeuille recommandé non calculé : {e}")
        return 0


if __name__ == "__main__":
    print(json.dumps(_clean({"exemple": np.float64("nan")})))
