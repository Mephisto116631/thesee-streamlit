# modele_horizon.py
# ==============================================================================
# MODÈLE IA « HORIZON » : classer les titres selon leur performance attendue
# PAR RAPPORT AU MARCHÉ sur 1 mois, 6 mois ou 1 an.
# ==============================================================================
# Pourquoi pas « hausse ou baisse demain » ? À 1 jour, les cours sont proches du
# hasard (le modèle précédent faisait ~50 %). Pour un placement à 6-12 mois, la
# bonne question est : « parmi ces titres, lesquels feront MIEUX que les autres ? ».
#
# Méthode
#   - Caractéristiques (calculées chaque semaine, pour chaque titre) : momentum
#     12-1 et 6-1 mois, retournement 1 mois, volatilité 3 mois, écart à la MM200,
#     RSI 14, distance au plus haut 1 an, bêta 1 an vs SPY, tendance du volume.
#     Chacune est transformée en RANG du jour (0 = plus faible, 1 = plus fort) :
#     le modèle compare les titres entre eux, il ne prédit pas le marché.
#   - Cible : rang du rendement futur sur H jours, relatif aux autres titres.
#   - Modèle : XGBoost (régression), volontairement peu profond (régularisé).
#   - Évaluation honnête : validation « walk-forward » (entraîné sur le passé,
#     testé sur la période suivante) avec un embargo de H jours entre les deux,
#     sinon les cibles qui se chevauchent font croire à un faux signal.
#   - Mesures : IC (corrélation de rang entre prédiction et réalité, par date),
#     écart de rendement entre le 1er et le dernier quintile, et comparaison
#     avec la règle simple « momentum 12-1 » : si le modèle ne fait pas mieux,
#     c'est le meilleur classement simple qui est publié : momentum seul ou
#     score multi-facteurs (diagnostics.source). Le code XGBoost reste en place
#     et reprend la main automatiquement s'il fait mieux un jour.
#   - Historique : depuis 2005 (téléchargé à chaque passage, non stocké).
#   - Biais du survivant : à chaque date, l'évaluation et l'entraînement ne gardent
#     que les titres qui étaient VRAIMENT dans le S&P 500 ce jour-là
#     (data/sp500_historique.csv, outils/composition_sp500.py). Sinon un titre
#     entré dans l'indice après avoir flambé compterait comme « gagnant » dès 2012.
#     Limite restante : Yahoo n'a plus les cours des titres disparus (faillites,
#     rachats), ils manquent encore — les résultats restent un peu optimistes.
# ==============================================================================
from pathlib import Path

import numpy as np
import pandas as pd

HORIZONS = {"court": 21, "6m": 126, "1a": 252}
FICHIER_COMPOSITION = Path(__file__).resolve().parent / "data" / "sp500_historique.csv"
MIN_MEMBRES = 50             # en dessous, la date est ignorée (classement peu représentatif)
PAS_ECHANTILLON = 5          # une observation par titre et par semaine
N_FENETRES = 4               # nombre de périodes de test (walk-forward)
INDICE = "SPY"
FEATURES = ["mom_12_1", "mom_6_1", "rev_1m", "vol_3m", "ecart_mm200",
            "rsi_14", "dist_plus_haut", "beta_1a", "tendance_volume",
            # Facteurs long terme documentés (ajoutés après les premiers tests sur 20 ans)
            "mom_36_12", "vol_idio", "max_1m", "liquidite", "mom_secteur"]
# Facteurs qui demandent beaucoup d'historique : manquants au début -> rang neutre 0,5
FEATURES_TOLERANTS = ["mom_36_12", "mom_secteur"]
LABELS = {
    "mom_12_1": "Momentum 12 mois (hors dernier mois)",
    "mom_6_1": "Momentum 6 mois (hors dernier mois)",
    "rev_1m": "Performance du dernier mois",
    "vol_3m": "Volatilité 3 mois",
    "ecart_mm200": "Écart à la moyenne 200 j",
    "rsi_14": "RSI 14 j (Relative Strength Index, force relative)",
    "dist_plus_haut": "Distance au plus haut 1 an",
    "beta_1a": "Bêta 1 an (sensibilité au marché)",
    "tendance_volume": "Volume récent vs habituel",
    "mom_36_12": "Performance 3 ans (hors dernière année)",
    "vol_idio": "Volatilité propre (hors marché) 3 mois",
    "max_1m": "Plus forte hausse d'un jour (1 mois)",
    "liquidite": "Montants échangés (taille)",
    "mom_secteur": "Momentum 12 mois vs son secteur",
}

# Réglages candidats. À chaque période de test, le réglage est choisi sur le PASSÉ seulement
# (validation interne), jamais sur la période testée : l'IC affiché reste honnête.
CONFIGS = {
    "xgb_prudent": {"n_estimators": 300, "max_depth": 2, "learning_rate": 0.03, "min_child_weight": 200},
    "xgb_standard": {"n_estimators": 200, "max_depth": 3, "learning_rate": 0.05, "min_child_weight": 50},
    "xgb_riche": {"n_estimators": 400, "max_depth": 4, "learning_rate": 0.03, "min_child_weight": 100},
    "lineaire": {"alpha": 10.0},   # régression ridge sur les rangs : robuste quand le signal est faible
}
CONFIG_DEFAUT = "xgb_standard"
PART_VALIDATION = 0.3              # dernière part du passé servant à choisir le réglage
LIBELLES_CONFIGS = {"xgb_prudent": "XGBoost prudent", "xgb_standard": "XGBoost standard",
                    "xgb_riche": "XGBoost riche", "lineaire": "Linéaire (ridge)"}


def _rsi(px: pd.DataFrame, n: int = 14) -> pd.DataFrame:
    d = px.diff()
    up = d.clip(lower=0).ewm(com=n - 1, adjust=False).mean()
    down = (-d.clip(upper=0)).ewm(com=n - 1, adjust=False).mean()
    return 100 - 100 / (1 + up / down.replace(0, np.nan))


def caracteristiques(market_raw: pd.DataFrame, symboles: list[str],
                     secteurs: dict[str, str] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retourne (tableau large des cours, caractéristiques empilées par date et titre)."""
    m = market_raw[market_raw["symbol"].isin(set(symboles) | {INDICE})]
    px = m.pivot_table(index="date", columns="symbol", values="close").sort_index().ffill(limit=5)
    vol = m.pivot_table(index="date", columns="symbol", values="volume").sort_index().reindex(px.index)
    ret = px.pct_change()

    f = {
        "mom_12_1": px.shift(21) / px.shift(252) - 1,
        "mom_6_1": px.shift(21) / px.shift(126) - 1,
        "rev_1m": px / px.shift(21) - 1,
        "vol_3m": ret.rolling(63).std() * np.sqrt(252),
        "ecart_mm200": px / px.rolling(200).mean() - 1,
        "rsi_14": _rsi(px),
        "dist_plus_haut": px / px.rolling(252).max() - 1,
        "tendance_volume": vol.rolling(20).mean() / vol.rolling(120).mean(),
    }
    if INDICE in ret.columns:
        rm = ret[INDICE]
        f["beta_1a"] = ret.rolling(252).cov(rm).div(rm.rolling(252).var(), axis=0)
        # Volatilité propre : variance totale - part expliquée par le marché (3 mois)
        cov63, var_m63 = ret.rolling(63).cov(rm), rm.rolling(63).var()
        idio = ret.rolling(63).var() - cov63.pow(2).div(var_m63, axis=0)
        f["vol_idio"] = idio.clip(lower=0).pow(0.5) * np.sqrt(252)
    else:
        f["beta_1a"] = ret * np.nan
        f["vol_idio"] = ret.rolling(63).std() * np.sqrt(252)
    f["mom_36_12"] = px.shift(252) / px.shift(756) - 1          # retournement long terme (De Bondt-Thaler)
    f["max_1m"] = ret.rolling(21).max()                          # effet « loterie » (Bali et al.)
    f["liquidite"] = np.log((px * vol).rolling(63).mean().replace(0, np.nan))  # taille approchée
    if secteurs:
        sect = pd.Series({c: secteurs.get(c, "?") for c in px.columns})
        mom = f["mom_12_1"]
        f["mom_secteur"] = mom - mom.T.groupby(sect).transform("median").T
    else:
        f["mom_secteur"] = f["mom_12_1"] * np.nan

    dates = px.index[252::PAS_ECHANTILLON]
    cols = [c for c in px.columns if c != INDICE and c in symboles]
    blocs = []
    for nom, tab in f.items():
        t = tab.reindex(index=dates, columns=cols)
        blocs.append(t.rank(axis=1, pct=True).stack(future_stack=True).rename(nom))  # rang du jour
    X = pd.concat(blocs, axis=1)
    X.index.names = ["date", "symbol"]
    X[FEATURES_TOLERANTS] = X[FEATURES_TOLERANTS].fillna(0.5)
    return px[cols], X.reset_index()


def score_multifacteurs(X: pd.DataFrame) -> pd.Series:
    """Score multi-facteurs fixe (aucun apprentissage, donc aucun sur-ajustement) :
    moyenne des rangs du jour de trois facteurs documentés dans la littérature :
      - momentum 12-1 mois (les gagnants de l'année continuent un peu),
      - faible volatilité 3 mois (les titres calmes ont un meilleur rendement ajusté du risque),
      - proximité du plus haut 1 an (« 52-week high », George & Hwang 2004).
    La qualité des bilans n'est pas incluse : les fondamentaux ne sont disponibles que
    pour une douzaine de titres (quota gratuit Alpha Vantage)."""
    return (X["mom_12_1"] + (1 - X["vol_3m"]) + X["dist_plus_haut"]) / 3


# Ce que le modèle cherche à prédire (le modèle publié utilise « relatif »)
MODES_CIBLE = {
    "relatif": "rendement futur, comparé à la médiane des titres",
    "alpha": "alpha de Jensen : rendement futur − bêta × rendement du marché (retire l'effet du risque de marché)",
    "alpha_secteur": "alpha de Jensen comparé aux titres du même secteur (retire aussi les paris sectoriels)",
}


def _relatif(df: pd.DataFrame, par_secteur: bool) -> pd.DataFrame:
    """rel = brut − médiane du jour (ou du jour et du secteur) ; y = rang du jour de rel."""
    cles = ["date", "secteur"] if par_secteur and "secteur" in df else ["date"]
    df["rel"] = df["brut"] - df.groupby(cles)["brut"].transform("median")
    df["y"] = df.groupby("date")["rel"].rank(pct=True)
    return df


def cible(px: pd.DataFrame, dates: pd.Index, h: int, mode: str = "relatif",
          marche: pd.Series | None = None, secteurs: dict[str, str] | None = None) -> pd.DataFrame:
    """Rendement futur sur h jours (ou alpha), relatif aux autres titres du jour, et son rang.
    Colonnes : brut (rendement ou alpha), marche_fut (rendement futur du marché), rel, y."""
    fut = (px.shift(-h) / px - 1).reindex(dates)
    brut = fut
    fut_m = None
    if marche is not None:
        m = marche.reindex(px.index).ffill(limit=5)
        fut_m = (m.shift(-h) / m - 1).reindex(dates)
        if mode.startswith("alpha"):
            # Bêta mesuré sur l'année PASSÉE (aucune information future), ajusté selon Blume
            # (0,67 × bêta + 0,33) : les bêtas extrêmes reviennent vers 1 avec le temps.
            ret, rm = px.pct_change(), m.pct_change()
            beta = ret.rolling(252).cov(rm).div(rm.rolling(252).var(), axis=0).reindex(dates)
            beta = 0.67 * beta + 0.33
            brut = fut - beta.mul(fut_m, axis=0)
    out = brut.stack(future_stack=True).rename("brut").to_frame()
    out.index.names = ["date", "symbol"]
    out = out.reset_index()
    if fut_m is not None:
        out["marche_fut"] = out["date"].map(fut_m)
    if secteurs:
        out["secteur"] = out["symbol"].map(secteurs).fillna("?")
    return _relatif(out, mode == "alpha_secteur")


def _modele(config: str = CONFIG_DEFAUT):
    c = CONFIGS[config]
    if config == "lineaire":
        from sklearn.linear_model import Ridge
        return Ridge(alpha=c["alpha"])
    from xgboost import XGBRegressor
    return XGBRegressor(**c, subsample=0.8, colsample_bytree=0.8, reg_lambda=5.0, random_state=42)


def _importances(m, config: str) -> np.ndarray:
    if config == "lineaire":
        v = np.abs(m.coef_)
        return v / v.sum() if v.sum() > 0 else v
    return m.feature_importances_


def choisir_config(train: pd.DataFrame, h: int) -> tuple[str, dict]:
    """Choisit le réglage sur le passé seulement : entraînement sur les 70 % les plus anciens,
    validation (IC) sur les 30 % les plus récents, avec embargo entre les deux."""
    dates = np.sort(train["date"].unique())
    if len(dates) < 40:
        return CONFIG_DEFAUT, {}
    coupure = pd.Timestamp(dates[int(len(dates) * (1 - PART_VALIDATION))])
    embargo = pd.Timedelta(days=int(h * 7 / 5) + 1)
    fit = train[train["date"] < coupure - embargo]
    val = train[train["date"] >= coupure].copy()
    if len(fit) < 2000 or val.empty:
        return CONFIG_DEFAUT, {}
    scores = {}
    for nom in CONFIGS:
        val["pred"] = _modele(nom).fit(fit[FEATURES], fit["y"]).predict(val[FEATURES])
        ic = _ic_par_date(val, "pred")
        scores[nom] = float(ic.mean()) if len(ic) else -1.0
    return max(scores, key=scores.get), scores


def _ic_par_date(df: pd.DataFrame, col: str) -> pd.Series:
    """Corrélation de rang (Spearman) entre `col` et le rendement relatif réalisé, date par date."""
    return df.groupby("date").apply(lambda g: g[col].rank().corr(g["rel"].rank()) if len(g) > 10 else np.nan,
                                    include_groups=False).dropna()


def _corr_par_date(df: pd.DataFrame, a: str, b: str) -> pd.Series:
    """Corrélation de rang (Spearman) entre deux colonnes, date par date."""
    return df.groupby("date").apply(lambda g: g[a].rank().corr(g[b].rank()) if len(g) > 10 else np.nan,
                                    include_groups=False).dropna()


FACTEURS_SURVEILLES = ["vol_3m", "vol_idio", "liquidite", "beta_1a", "max_1m"]


def sens_facteurs(t: pd.DataFrame) -> dict:
    """Contrôles anti-biais sur les périodes de test.
    - modele : corrélation entre le score du modèle et chaque facteur (> 0 = le modèle
      favorise les titres où ce facteur est élevé : plus volatils, plus grands...).
    - realite : IC du facteur seul (> 0 = ces titres ont réellement fait mieux).
    - quintiles : rendement relatif moyen par quintile du facteur (1 = plus faible).
    - ic_grandes / ic_petites : IC du modèle parmi la moitié la plus liquide (grandes valeurs,
      rarement disparues par faillite) et parmi l'autre moitié. Si le modèle ne marche que
      chez les petites, le biais du survivant restant est suspect."""
    out = {"facteurs": {}}
    for f in FEATURES:
        out["facteurs"][f] = {
            "modele": float(_corr_par_date(t, "pred", f).mean()),
            "realite": float(_ic_par_date(t, f).mean()),
        }
    for f in FACTEURS_SURVEILLES:
        q = t.groupby("date")[f].transform(lambda x: pd.qcut(x.rank(method="first"), 5, labels=False))
        out["facteurs"][f]["quintiles"] = [float(t.loc[q == i, "rel"].mean()) for i in range(5)]
    grande = t.groupby("date")["liquidite"].transform(lambda x: x >= x.median())
    out["ic_grandes"] = float(_ic_par_date(t[grande], "pred").mean())
    out["ic_petites"] = float(_ic_par_date(t[~grande], "pred").mean())
    return out


def ic_par_regime(t: pd.DataFrame) -> dict:
    """IC du modèle selon que le marché a monté ou baissé sur l'horizon. Si le modèle ne
    marche qu'en marché haussier, il prend surtout du risque de marché (bêta)."""
    if "marche_fut" not in t:
        return {}
    out = {}
    for nom, masque in (("hausse", t["marche_fut"] > 0), ("baisse", t["marche_fut"] <= 0)):
        ic = _ic_par_date(t[masque], "pred")
        out[nom] = {"ic": float(ic.mean()) if len(ic) else None, "n_dates": int(len(ic))}
    return out


def evaluer(data: pd.DataFrame, h: int) -> dict:
    """Walk-forward avec embargo de h jours entre entraînement et test."""
    dates = np.sort(data["date"].unique())
    if len(dates) < 60:
        return {}
    bornes = np.array_split(dates[len(dates) // 3:], N_FENETRES)  # 1er tiers : entraînement initial
    embargo = pd.Timedelta(days=int(h * 7 / 5) + 1)                  # h jours de bourse ≈ h·7/5 jours
    tests, fenetres = [], []
    for bloc in bornes:
        debut = pd.Timestamp(bloc[0])
        train = data[data["date"] < debut - embargo]
        test = data[data["date"].isin(bloc)].copy()
        if len(train) < 2000 or test.empty:
            continue
        config, _ = choisir_config(train, h)
        m = _modele(config).fit(train[FEATURES], train["y"])
        test["pred"] = m.predict(test[FEATURES])
        ic = _ic_par_date(test, "pred")
        fenetres.append({"debut": str(debut.date()), "fin": str(pd.Timestamp(bloc[-1]).date()),
                         "ic": float(ic.mean()) if len(ic) else None, "n_dates": int(len(ic)),
                         "config": config})
        tests.append(test)
    if not tests:
        return {}
    t = pd.concat(tests)
    ic = _ic_par_date(t, "pred")
    ic_mom = _ic_par_date(t, "mom_12_1")
    t["multi"] = score_multifacteurs(t)
    ic_multi = _ic_par_date(t, "multi")
    # Les dates se chevauchent (cible sur h jours, une date par semaine) :
    # nombre effectif d'observations indépendantes ≈ n_dates / (h / 5).
    n_eff = max(1.0, len(ic) / max(1.0, h / PAS_ECHANTILLON))
    t_stat = float(ic.mean() / ic.std() * np.sqrt(n_eff)) if ic.std() > 0 else 0.0
    t_mom = float(ic_mom.mean() / ic_mom.std() * np.sqrt(n_eff)) if len(ic_mom) and ic_mom.std() > 0 else 0.0
    t_multi = float(ic_multi.mean() / ic_multi.std() * np.sqrt(n_eff)) if len(ic_multi) and ic_multi.std() > 0 else 0.0
    t["quintile"] = t.groupby("date")["pred"].transform(lambda s: pd.qcut(s.rank(method="first"), 5, labels=False))
    q = t.groupby("quintile")["rel"].mean()
    haut_bat_mediane = t[t["quintile"] == 4].groupby("date")["rel"].mean()
    return {
        "horizon_jours": h,
        "ic_moyen": float(ic.mean()), "ic_ecart_type": float(ic.std()), "t_stat": t_stat,
        "ic_momentum": float(ic_mom.mean()) if len(ic_mom) else None,
        "t_momentum": t_mom,
        "ic_multifacteurs": float(ic_multi.mean()) if len(ic_multi) else None,
        "t_multifacteurs": t_multi,
        "spread_quintiles": float(q.get(4, np.nan) - q.get(0, np.nan)),   # rendement relatif Q5 - Q1 sur h jours
        "rendement_par_quintile": [float(q.get(i, np.nan)) for i in range(5)],
        "taux_reussite_top": float((haut_bat_mediane > 0).mean()) if len(haut_bat_mediane) else None,
        "n_dates_test": int(len(ic)), "n_effectif": float(n_eff),
        "debut_donnees": str(pd.Timestamp(dates[0]).date()),
        "debut_test": str(pd.Timestamp(t["date"].min()).date()),
        "fenetres": fenetres,
        "controles": sens_facteurs(t),
        "regimes": ic_par_regime(t),
    }


N_CANDIDATS = 3              # classements comparés (modèle, momentum, multi-facteurs) : on publie le meilleur
MIN_PERIODES_SIGNAL = 8      # en dessous, aucune conclusion possible, quel que soit le t


def seuil_t(n_effectif: float | None, n_candidats: int = N_CANDIDATS) -> float:
    """Valeur de t à dépasser pour parler de signal : loi de Student (peu de périodes
    indépendantes -> seuil plus haut) au risque de 5 % bilatéral, corrigé de Bonferroni
    car on retient le meilleur de `n_candidats` classements (sinon le hasard en fait gagner un)."""
    from scipy.stats import t as student
    ddl = max(1.0, (n_effectif or 1.0) - 1.0)
    return float(student.ppf(1 - 0.025 / n_candidats, ddl))


def verdict(ic: float | None, t: float | None, n_effectif: float | None = None) -> str:
    """signal : IC > 0,03, assez de périodes indépendantes et t au-delà du seuil corrigé ;
    bruit : IC > 0,01 ; sinon aucun."""
    if ic is None:
        return "aucun"
    if (ic > 0.03 and (n_effectif or 0) >= MIN_PERIODES_SIGNAL
            and (t or 0) > seuil_t(n_effectif)):
        return "signal"
    if ic > 0.01:
        return "bruit"
    return "aucun"


def charger_composition(fichier: Path = FICHIER_COMPOSITION) -> pd.DataFrame | None:
    """Périodes d'appartenance au S&P 500 (symbol, debut, fin) ; None si le fichier manque."""
    try:
        c = pd.read_csv(fichier, parse_dates=["debut", "fin"])
    except (FileNotFoundError, ValueError):
        return None
    return c if not c.empty else None


def membres_a_date(data: pd.DataFrame, composition: pd.DataFrame, par_secteur: bool = False) -> pd.DataFrame:
    """Ne garde, à chaque date, que les titres membres de l'indice ce jour-là, puis
    recalcule les rangs du jour (caractéristiques et cible) parmi ces seuls membres."""
    m = data.merge(composition, on="symbol", how="inner")
    fin = m["fin"].fillna(pd.Timestamp.max)
    m = m[(m["date"] >= m["debut"]) & (m["date"] < fin)].drop(columns=["debut", "fin"])
    m = m.drop_duplicates(["date", "symbol"])
    m = m[m.groupby("date")["symbol"].transform("size") >= MIN_MEMBRES].copy()
    g = m.groupby("date")
    for f in FEATURES:
        m[f] = g[f].rank(pct=True)
    return _relatif(m, par_secteur).reset_index(drop=True)


def entrainer_horizon(market_raw: pd.DataFrame, symboles: list[str], nom: str,
                      composition: pd.DataFrame | None = None,
                      secteurs: dict[str, str] | None = None,
                      cible_mode: str = "relatif") -> tuple[dict, pd.DataFrame]:
    """Évalue puis entraîne le modèle final ; retourne (ligne model_runs, scores du jour).
    `composition` (charger_composition()) : évaluation sur les seuls membres de l'indice à chaque date."""
    h = HORIZONS[nom]
    px, X = caracteristiques(market_raw, symboles, secteurs)
    if X.empty:
        return {}, pd.DataFrame()
    serie_m = market_raw[market_raw["symbol"] == INDICE].set_index("date")["close"].sort_index()
    Y = cible(px, pd.DatetimeIndex(X["date"].unique()), h, cible_mode,
              serie_m if not serie_m.empty else None, secteurs)
    data = X.merge(Y, on=["date", "symbol"]).dropna(subset=FEATURES + ["y"])
    point_in_time = False
    if composition is not None:
        filtre = membres_a_date(data, composition, cible_mode == "alpha_secteur")
        if not filtre.empty:
            data, point_in_time = filtre, True
    ev = evaluer(data, h)
    if ev:
        ev["cible"] = cible_mode
        ev["composition_historique"] = point_in_time
        ev["titres_par_date"] = float(data.groupby("date")["symbol"].size().mean())
    if data.empty:
        return {}, pd.DataFrame()
    config, ic_validation = choisir_config(data, h)      # réglage du modèle final : même règle, sur tout le passé
    m = _modele(config).fit(data[FEATURES], data["y"])
    if ev:
        ev["config"] = config
        ev["config_libelle"] = LIBELLES_CONFIGS[config]
        ev["ic_validation_configs"] = ic_validation

    # Classement publié : celui qui a le mieux marché en test. Si le modèle ne bat
    # pas la règle simple « momentum 12-1 », c'est le momentum qui est utilisé
    # (et l'appli l'indique) : mieux vaut une règle simple qui marche qu'un modèle qui ne marche pas.
    source = "modele"
    if ev:
        candidats = {"modele": ev.get("ic_moyen"), "momentum": ev.get("ic_momentum"),
                     "multifacteurs": ev.get("ic_multifacteurs")}
        source = max(candidats, key=lambda k: candidats[k] if candidats[k] is not None else -9)
    derniere = X["date"].max()
    aujourd_hui = X[X["date"] == derniere].dropna(subset=FEATURES).copy()
    if source == "modele":
        aujourd_hui["pred"] = m.predict(aujourd_hui[FEATURES])
    elif source == "multifacteurs":
        aujourd_hui["pred"] = score_multifacteurs(aujourd_hui)
    else:
        aujourd_hui["pred"] = aujourd_hui["mom_12_1"]
    aujourd_hui["score"] = aujourd_hui["pred"].rank(pct=True)
    scores = aujourd_hui[["symbol", "score"]].assign(horizon=nom, date=str(pd.Timestamp(derniere).date()))

    imp = sorted([{"feature": f, "label": LABELS[f], "importance": float(v)}
                  for f, v in zip(FEATURES, _importances(m, config))], key=lambda d: -d["importance"])
    cle_ic = {"modele": ("ic_moyen", "t_stat"), "momentum": ("ic_momentum", "t_momentum"),
              "multifacteurs": ("ic_multifacteurs", "t_multifacteurs")}[source]
    ic, t = ev.get(cle_ic[0]), ev.get(cle_ic[1])
    if ev:
        ev["source"] = source
        ev["seuil_t"] = seuil_t(ev.get("n_effectif"))
    ligne = {
        "kind": f"horizon_{nom}",
        "trained_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "accuracy": ev.get("taux_reussite_top", 0) * 100 if ev.get("taux_reussite_top") is not None else None,
        "baseline": 50.0,
        "gain_pts": ic * 100 if ic is not None else None,   # IC en points (ex. 3,5 = IC 0,035)
        "verdict": verdict(ic, t, ev.get("n_effectif")),
        "importance": imp,
        "diagnostics": ev,
    }
    return ligne, scores
