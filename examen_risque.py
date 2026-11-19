# examen_risque.py
# ==============================================================================
# EXAMEN APPROFONDI DE L'IA DE VOLATILITÉ (laboratoire seulement)
#
# L'IA de volatilité à 6 mois est le seul modèle probant de Thésée. Ce module la
# confronte à des épreuves plus dures que son test habituel (journal : docs/METHODE.md § 4.8) :
#   1. références reconnues : EWMA (RiskMetrics), GARCH(1,1), HAR (Corsi), comparées en
#      perte QLIKE avec un test de Diebold-Mariano ;
#   2. calibration du NIVEAU prévu (l'appli s'en sert pour « 15 % de risque ») ;
#   3. crises, marchés nerveux / calmes, secteurs, tailles ;
#   4. placebo (cible mélangée, facteur aléatoire, fuite volontaire) ;
#   5. sensibilité aux réglages du modèle.
# Même protocole que modele_risque.evaluer_risque : walk-forward, embargo, membres de
# l'indice à chaque date, réglage choisi sur le passé seulement.
# ==============================================================================
import numpy as np
import pandas as pd

import modele_horizon as mh
import modele_risque as mr

H = mh.HORIZONS["6m"]          # 126 jours de bourse
LAMBDA_EWMA = 0.94             # RiskMetrics (J.P. Morgan, 1996)
REFERENCES = ["vol_3m", "ewma", "garch", "har"]
CRISES = {
    "2008-2009 (crise financière)": ("2008-01-01", "2009-06-30"),
    "2011 (dette européenne)": ("2011-07-01", "2011-12-31"),
    "2015-2016 (Chine, pétrole)": ("2015-08-01", "2016-02-29"),
    "fin 2018 (taux)": ("2018-10-01", "2018-12-31"),
    "2020 (Covid)": ("2020-02-15", "2020-06-30"),
    "2022 (inflation)": ("2022-01-01", "2022-10-31"),
}


# ------------------------------------------------------------------------------
# Références de prévision de la volatilité (niveaux annualisés à chaque date)
# ------------------------------------------------------------------------------
def ewma(ret: pd.DataFrame, lam: float = LAMBDA_EWMA) -> pd.DataFrame:
    """Volatilité EWMA : variance = λ·variance d'hier + (1 − λ)·rendement²."""
    return np.sqrt(ret.pow(2).ewm(alpha=1 - lam, adjust=False, min_periods=63).mean() * 252)


def _garch_vraisemblance(params, r2_moy: np.ndarray, r2: np.ndarray) -> float:
    """−log-vraisemblance gaussienne d'un GARCH(1,1) à variance ciblée, empilée sur plusieurs titres.
    r2 : rendements² (jours x titres), r2_moy : variance de long terme de chaque titre."""
    a, b = params
    if a < 0 or b < 0 or a + b >= 0.999:
        return 1e12
    w = r2_moy * (1 - a - b)
    s2 = r2_moy.copy()
    nll = 0.0
    for t in range(r2.shape[0]):
        x = r2[t]
        ok = ~np.isnan(x)
        nll += float(np.sum(np.log(s2[ok]) + x[ok] / s2[ok]))
        s2 = w + a * np.where(ok, x, s2) + b * s2
    return nll


def garch_parametres(ret_train: pd.DataFrame, n_titres: int = 60, graine: int = 0) -> tuple[float, float]:
    """(α, β) communs, estimés sur le PASSÉ seulement, sur un échantillon de titres (variance ciblée)."""
    from scipy.optimize import minimize
    rng = np.random.default_rng(graine)
    cols = [c for c in ret_train.columns if ret_train[c].notna().sum() > 500]
    cols = list(rng.choice(cols, size=min(n_titres, len(cols)), replace=False)) if cols else []
    r = ret_train[cols].iloc[-1500:]
    r2 = (r - r.mean()).pow(2).values
    r2_moy = np.nanmean(r2, axis=0)
    res = minimize(_garch_vraisemblance, x0=[0.08, 0.90], args=(r2_moy, r2), method="Nelder-Mead",
                   options={"xatol": 1e-4, "fatol": 1e-2, "maxiter": 300})
    a, b = res.x
    return float(max(a, 1e-4)), float(min(max(b, 0.0), 0.998 - max(a, 1e-4)))


def garch(ret: pd.DataFrame, a: float, b: float, h: int = H, fenetre_lt: int = 756) -> pd.DataFrame:
    """Volatilité moyenne prévue sur h jours par un GARCH(1,1) à paramètres communs.
    Variance de long terme de chaque titre : moyenne des 3 années passées."""
    r2 = ret.pow(2)
    lt = r2.rolling(fenetre_lt, min_periods=252).mean()
    s2 = pd.DataFrame(np.nan, index=ret.index, columns=ret.columns)
    cur = lt.iloc[0].fillna(r2.mean())
    vals = np.empty(ret.shape)
    r2v, ltv = r2.values, lt.ffill().values
    cur = cur.values.astype(float)
    for t in range(ret.shape[0]):
        lt_t = np.where(np.isnan(ltv[t]), cur, ltv[t])
        x = np.where(np.isnan(r2v[t]), cur, r2v[t])
        cur = lt_t * (1 - a - b) + a * x + b * cur          # variance de demain
        vals[t] = cur
    s2[:] = vals
    phi = a + b
    k = (1 - phi ** h) / ((1 - phi) * h) if phi < 1 else 1.0  # moyenne sur l'horizon : retour vers le long terme
    moy = lt + (s2 - lt) * k
    return np.sqrt(moy * 252)


def har_entrees(ret: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Variances réalisées sur 1 jour, 5 jours et 22 jours (modèle HAR de Corsi, 2009)."""
    r2 = ret.pow(2)
    return {"v1": r2, "v5": r2.rolling(5).mean(), "v22": r2.rolling(22).mean(), "v63": r2.rolling(63).mean()}


def har_ajuster(train: pd.DataFrame) -> np.ndarray:
    """Régression (moindres carrés) de la variance future sur v1, v5, v22, v63 : sur le passé seulement."""
    X = np.column_stack([np.ones(len(train))] + [train[c].values for c in ["v1", "v5", "v22", "v63"]])
    y = train["brut"].values ** 2 / 252
    ok = np.isfinite(X).all(axis=1) & np.isfinite(y)
    coef, *_ = np.linalg.lstsq(X[ok], y[ok], rcond=None)
    return coef


def har_prevoir(df: pd.DataFrame, coef: np.ndarray) -> np.ndarray:
    X = np.column_stack([np.ones(len(df))] + [df[c].values for c in ["v1", "v5", "v22", "v63"]])
    v = X @ coef
    plancher = df["v63"].values * 0.25                  # garde-fou : jamais de variance négative
    return np.sqrt(np.maximum(v, plancher) * 252)


# ------------------------------------------------------------------------------
# Pertes et tests
# ------------------------------------------------------------------------------
def qlike(prevu: np.ndarray, reel: np.ndarray) -> np.ndarray:
    """Perte QLIKE sur les variances : r/p − log(r/p) − 1 (0 si parfait ; robuste aux erreurs
    de mesure de la volatilité réalisée, Patton 2011)."""
    p, r = np.asarray(prevu, float) ** 2, np.asarray(reel, float) ** 2
    q = r / p
    return q - np.log(q) - 1


def diebold_mariano(perte_a: pd.Series, perte_b: pd.Series, decalage: int) -> dict:
    """Test de Diebold-Mariano sur des pertes moyennes par date. d = a − b ; t < 0 : a meilleure.
    Écart-type de Newey-West (les prévisions à 6 mois se chevauchent d'une date à l'autre)."""
    d = (perte_a - perte_b).dropna().values
    n = len(d)
    if n < 10:
        return {"t": 0.0, "ecart": float(np.mean(d)) if n else 0.0, "n": n}
    m = d.mean()
    e = d - m
    var = e @ e / n
    for k in range(1, min(decalage, n - 1) + 1):
        var += 2 * (1 - k / (decalage + 1)) * (e[k:] @ e[:-k]) / n
    t = m / np.sqrt(max(var, 1e-18) / n)
    return {"t": float(t), "ecart": float(m), "n": n}


def calibration(df: pd.DataFrame, col: str) -> dict:
    """Biais du niveau prévu : médiane de prévu / réel, globale et par décile de prévision."""
    r = (df[col] / df["brut"]).replace([np.inf, -np.inf], np.nan).dropna()
    dec = pd.qcut(df.loc[r.index, col], 10, labels=False, duplicates="drop")
    par = r.groupby(dec).median()
    return {"biais_median": float(r.median() - 1), "par_decile": [float(x - 1) for x in par.values],
            "part_sous_estime": float((r < 1).mean())}


# ------------------------------------------------------------------------------
# Préparation et walk-forward
# ------------------------------------------------------------------------------
def preparer(market_raw: pd.DataFrame, symboles: list[str], composition: pd.DataFrame | None,
             secteurs: dict | None = None, h: int = H) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Échantillon (date, titre) : facteurs (rangs), cible (rang `y` et niveau réalisé `brut`),
    entrées HAR et références de niveau. Retourne (data, rendements quotidiens)."""
    px, X = mh.caracteristiques(market_raw, symboles)
    Y = mr.cible_risque(px, pd.DatetimeIndex(X["date"].unique()), h, "volatilite")
    data = X.merge(Y, on=["date", "symbol"]).dropna(subset=mh.FEATURES + ["y"])
    if composition is not None:
        filtre = mh.membres_a_date(data, composition)
        if not filtre.empty:
            data = filtre
    ret = px.pct_change()
    dates = pd.DatetimeIndex(data["date"].unique())
    niveaux = {"lvl_vol_3m": ret.rolling(63).std() * np.sqrt(252), "lvl_ewma": ewma(ret)}
    niveaux.update({k: v for k, v in har_entrees(ret).items()})
    for nom, tab in niveaux.items():
        s = tab.reindex(dates).stack(future_stack=True).rename(nom)
        s.index.names = ["date", "symbol"]
        data = data.merge(s.reset_index(), on=["date", "symbol"], how="left")
    if secteurs:
        data["secteur"] = data["symbol"].map(secteurs).fillna("?")
    return data.dropna(subset=["lvl_vol_3m", "brut"]).reset_index(drop=True), ret


def _rang_vers_niveau(df: pd.DataFrame, col_rang: str) -> pd.Series:
    """Rang prédit -> niveau : quantile correspondant des volatilités 3 mois du jour
    (même méthode que modele_risque.predire_volatilite)."""
    out = pd.Series(np.nan, index=df.index)
    for _, g in df.groupby("date"):
        v = np.sort(g["lvl_vol_3m"].dropna().values)
        if len(v):
            out.loc[g.index] = np.quantile(v, g[col_rang].rank(pct=True).clip(0, 1).values)
    return out


def walk_forward(data: pd.DataFrame, ret: pd.DataFrame, feats: list[str] | None = None,
                 forcer_config: str | None = None, h: int = H, transformer=None) -> pd.DataFrame:
    """Prévisions de test de l'IA et des références, fenêtre par fenêtre (passé seulement).
    `transformer(train, test) -> (train, test)` : variantes placebo. Colonnes ajoutées :
    pred (rang IA), lvl_ia, lvl_garch, lvl_har, fenetre, config."""
    feats = feats or mh.FEATURES
    dates = np.sort(data["date"].unique())
    bornes = np.array_split(dates[len(dates) // 3:], mh.N_FENETRES)
    embargo = pd.Timedelta(days=int(h * 7 / 5) + 1)
    sorties = []
    for k, bloc in enumerate(bornes):
        debut = pd.Timestamp(bloc[0])
        train = data[data["date"] < debut - embargo]
        test = data[data["date"].isin(bloc)].copy()
        if len(train) < 2000 or test.empty:
            continue
        if transformer is not None:
            train, test = transformer(train.copy(), test)
        config = forcer_config or mh.choisir_config(train, h, feats)[0]
        m = mh._modele(config).fit(train[feats], train["y"])
        test["pred"] = m.predict(test[feats])
        test["lvl_ia"] = _rang_vers_niveau(test, "pred")
        # GARCH : paramètres estimés sur les rendements antérieurs à la fenêtre de test
        a, b = garch_parametres(ret[ret.index < debut - embargo])
        g = garch(ret, a, b, h).reindex(pd.DatetimeIndex(bloc))
        gs = g.stack(future_stack=True).rename("lvl_garch")
        gs.index.names = ["date", "symbol"]
        test = test.merge(gs.reset_index(), on=["date", "symbol"], how="left")
        test["lvl_har"] = har_prevoir(test, har_ajuster(train))
        test["fenetre"], test["config"] = k, config
        test["garch_ab"] = f"{a:.3f}/{b:.3f}"
        sorties.append(test)
    return pd.concat(sorties, ignore_index=True) if sorties else pd.DataFrame()


def _pertes_par_date(t: pd.DataFrame, col: str) -> pd.Series:
    ok = t[[col, "brut"]].notna().all(axis=1) & (t[col] > 0) & (t["brut"] > 0)
    return t[ok].assign(_q=qlike(t.loc[ok, col], t.loc[ok, "brut"])).groupby("date")["_q"].mean()


def comparer_references(t: pd.DataFrame, h: int = H) -> dict:
    """QLIKE moyenne de chaque méthode, IC de classement, et Diebold-Mariano IA contre chaque référence.
    Règle (docs/METHODE.md § 4.8) : l'IA reste si elle bat la MEILLEURE référence avec une force
    de preuve ≥ 100 % (seuil corrigé pour 3 comparaisons)."""
    cols = {"ia": "lvl_ia", "vol_3m": "lvl_vol_3m", "ewma": "lvl_ewma", "garch": "lvl_garch", "har": "lvl_har"}
    pertes = {k: _pertes_par_date(t, c) for k, c in cols.items()}
    n_dates = len(pertes["ia"])
    n_eff = max(1.0, n_dates * mh.PAS_ECHANTILLON / h)
    seuil = mh.seuil_t(n_eff, n_candidats=3)
    out = {"qlike": {k: float(v.mean()) for k, v in pertes.items()},
           "ic": {k: float(mh._ic_par_date(t.assign(rel=t["brut"]).dropna(subset=[c]), c).mean())
                  for k, c in cols.items()},
           "n_dates": n_dates, "n_effectif": n_eff, "seuil": seuil, "dm": {}}
    for ref in ["ewma", "garch", "har"]:
        dm = diebold_mariano(pertes["ia"], pertes[ref], decalage=max(1, h // mh.PAS_ECHANTILLON))
        dm["force"] = -dm["t"] / seuil            # > 100 % : l'IA est nettement meilleure
        out["dm"][ref] = dm
    meilleure = min(["ewma", "garch", "har"], key=lambda k: out["qlike"][k])
    out["meilleure_reference"] = meilleure
    out["ia_reste"] = bool(out["dm"][meilleure]["force"] >= 1.0)
    return out


def par_periode(t: pd.DataFrame, vix: pd.Series | None = None, ref: str = "lvl_har") -> dict:
    """Gain de l'IA (QLIKE de la référence − QLIKE de l'IA : > 0 = IA meilleure) et IC, par sous-groupe."""
    t = t.assign(rel=t["brut"])

    def bloc(g: pd.DataFrame) -> dict | None:
        if g["date"].nunique() < 3:
            return None
        pi, pr = _pertes_par_date(g, "lvl_ia"), _pertes_par_date(g, ref)
        ic_i = mh._ic_par_date(g, "lvl_ia").mean()
        ic_r = mh._ic_par_date(g.dropna(subset=[ref]), ref).mean()
        return {"gain_qlike": float((pr - pi).mean()), "ic_ia": float(ic_i), "ic_ref": float(ic_r),
                "part_dates_gagnantes": float(((pr - pi) > 0).mean()), "n_dates": int(g["date"].nunique())}
    out = {"crises": {}, "vix": {}, "secteurs": {}, "tailles": {}}
    for nom, (a, b) in CRISES.items():
        r = bloc(t[(t["date"] >= a) & (t["date"] <= b)])
        if r:
            out["crises"][nom] = r
    hors = pd.Series(True, index=t.index)
    for a, b in CRISES.values():
        hors &= ~((t["date"] >= a) & (t["date"] <= b))
    out["hors_crises"] = bloc(t[hors])
    if vix is not None and not vix.empty:
        v = vix.reindex(pd.DatetimeIndex(t["date"]), method="ffill").values
        out["vix"] = {"nerveux (VIX > 25)": bloc(t[v > 25]), "normal (15-25)": bloc(t[(v >= 15) & (v <= 25)]),
                      "calme (VIX < 15)": bloc(t[v < 15])}
    if "secteur" in t:
        out["secteurs"] = {s: r for s, g in t.groupby("secteur") if (r := bloc(g))}
    if "liquidite" in t:
        q = pd.qcut(t["liquidite"], 5, labels=["1 (petites)", "2", "3", "4", "5 (grandes)"], duplicates="drop")
        out["tailles"] = {str(s): r for s, g in t.groupby(q, observed=True) if (r := bloc(g))}
    return out


# ------------------------------------------------------------------------------
# Placebo et sensibilité
# ------------------------------------------------------------------------------
def _melanger(graine: int = 0):
    rng = np.random.default_rng(graine)

    def f(train, test):
        train["y"] = train.groupby("date")["y"].transform(lambda s: rng.permutation(s.values))
        return train, test
    return f


def _fuite(graine: int = 0):
    """Contrôle POSITIF : on donne au modèle la réponse (bruitée). Il doit exploser l'IC, ce qui
    prouve que le test saurait détecter une fuite si le vrai pipeline en avait une."""
    rng = np.random.default_rng(graine)

    def f(train, test):
        for d in (train, test):
            d["vol_3m"] = (d["y"] + rng.normal(0, 0.1, len(d))).clip(0, 1)
        return train, test
    return f


def placebo(data: pd.DataFrame, ret: pd.DataFrame, config: str = "xgb_prudent") -> dict:
    t_mel = walk_forward(data, ret, forcer_config=config, transformer=_melanger())
    t_fui = walk_forward(data, ret, forcer_config=config, transformer=_fuite())
    rng = np.random.default_rng(1)
    d2 = data.assign(bruit=rng.uniform(0, 1, len(data)))
    feats = mh.FEATURES + ["bruit"]
    train = d2[d2["date"] < d2["date"].quantile(0.6)]
    m = mh._modele(config).fit(train[feats], train["y"])
    imp = pd.Series(mh._importances(m, config), index=feats)
    imp = imp / imp.sum() if imp.sum() > 0 else imp
    ic = lambda t: float(mh._ic_par_date(t.assign(rel=t["brut"]), "pred").mean()) if not t.empty else None
    return {"ic_cible_melangee": ic(t_mel), "ic_fuite_volontaire": ic(t_fui),
            "importance_facteur_aleatoire": float(imp["bruit"]),
            "importance_rang_facteur_aleatoire": int((imp > imp["bruit"]).sum()) + 1, "n_facteurs": len(feats)}


def sensibilite(data: pd.DataFrame, ret: pd.DataFrame) -> dict:
    """Gain d'IC (IA − volatilité 3 mois) pour chaque réglage du modèle, imposé sur toutes les fenêtres."""
    out = {}
    for config in mh.CONFIGS:
        t = walk_forward(data, ret, forcer_config=config).assign(rel=lambda x: x["brut"])
        if t.empty:
            continue
        ic_ia, ic_ref = mh._ic_par_date(t, "pred"), mh._ic_par_date(t, "lvl_vol_3m")
        g = (ic_ia - ic_ref).dropna()
        n_eff = max(1.0, len(g) * mh.PAS_ECHANTILLON / H)
        out[config] = {"ic_ia": float(ic_ia.mean()), "ic_ref": float(ic_ref.mean()), "gain": float(g.mean()),
                       "t": float(g.mean() / g.std() * np.sqrt(n_eff)) if g.std() > 0 else 0.0}
    return out


def autre_marche(data_train: pd.DataFrame, data_autre: pd.DataFrame, config: str | None = None) -> dict:
    """Modèle entraîné sur le S&P 500 (dates antérieures au test), appliqué tel quel à un autre univers."""
    debut_test = np.sort(data_autre["date"].unique())[len(data_autre["date"].unique()) // 3]
    embargo = pd.Timedelta(days=int(H * 7 / 5) + 1)
    train = data_train[data_train["date"] < pd.Timestamp(debut_test) - embargo]
    config = config or mh.choisir_config(train, H)[0]
    m = mh._modele(config).fit(train[mh.FEATURES], train["y"])
    t = data_autre[data_autre["date"] >= debut_test].copy()
    t["pred"] = m.predict(t[mh.FEATURES])
    t["rel"] = t["brut"]
    ic_ia, ic_ref = mh._ic_par_date(t, "pred"), mh._ic_par_date(t, "lvl_vol_3m")
    g = (ic_ia - ic_ref).dropna()
    n_eff = max(1.0, len(g) * mh.PAS_ECHANTILLON / H)
    return {"ic_ia": float(ic_ia.mean()), "ic_ref": float(ic_ref.mean()), "gain": float(g.mean()),
            "t": float(g.mean() / g.std() * np.sqrt(n_eff)) if g.std() > 0 else 0.0,
            "n_titres": int(t["symbol"].nunique()), "n_dates": int(len(g)), "config": config,
            "debut_test": str(pd.Timestamp(debut_test).date())}


# ------------------------------------------------------------------------------
# Probabilité de sur-ajustement d'un backtest (Bailey, Borwein, López de Prado, Zhu 2017)
# ------------------------------------------------------------------------------
def pbo(rendements: pd.DataFrame, n_blocs: int = 16) -> dict:
    """CSCV : on coupe la période en n_blocs, et pour chaque moitié des blocs prise comme « passé »,
    on choisit la meilleure variante (Sharpe) puis on regarde son rang sur l'autre moitié.
    PBO = part des cas où la variante choisie finit dans la moitié basse."""
    from itertools import combinations
    R = rendements.dropna(how="all").fillna(0.0).values
    T, N = R.shape
    if N < 2 or T < n_blocs * 2:
        return {"pbo": None, "n_variantes": N}
    blocs = np.array_split(np.arange(T), n_blocs)
    sharpe = lambda x: x.mean(axis=0) / (x.std(axis=0) + 1e-12)
    logits = []
    for c in combinations(range(n_blocs), n_blocs // 2):
        is_idx = np.concatenate([blocs[i] for i in c])
        oos_idx = np.concatenate([blocs[i] for i in range(n_blocs) if i not in c])
        meilleur = int(np.argmax(sharpe(R[is_idx])))
        rang = (sharpe(R[oos_idx]).argsort().argsort()[meilleur] + 1) / (N + 1)
        logits.append(np.log(rang / (1 - rang)))
    logits = np.array(logits)
    return {"pbo": float((logits <= 0).mean()), "n_variantes": N, "n_combinaisons": len(logits)}
