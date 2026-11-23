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

import inference as inf
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


def _rang_vers_niveau(df: pd.DataFrame, col_rang: str, col_niveaux: str = "lvl_vol_3m") -> pd.Series:
    """Rang prédit -> niveau : quantile correspondant des niveaux du jour (volatilités 3 mois, ou
    niveaux HAR pour l'hybride : l'ordre vient de l'IA, le niveau de HAR)."""
    out = pd.Series(np.nan, index=df.index)
    for _, g in df.groupby("date"):
        v = np.sort(g[col_niveaux].dropna().values)
        if len(v):
            out.loc[g.index] = np.quantile(v, g[col_rang].rank(pct=True).clip(0, 1).values)
    return out


def walk_forward(data: pd.DataFrame, ret: pd.DataFrame, feats: list[str] | None = None,
                 forcer_config: str | None = None, h: int = H, transformer=None,
                 references: bool = True) -> pd.DataFrame:
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
        test["fenetre"], test["config"] = k, config
        if not references:            # placebo, sensibilité : seul le classement de l'IA compte
            sorties.append(test)
            continue
        # GARCH : paramètres estimés sur les rendements antérieurs à la fenêtre de test
        a, b = garch_parametres(ret[ret.index < debut - embargo])
        g = garch(ret, a, b, h).reindex(pd.DatetimeIndex(bloc))
        gs = g.stack(future_stack=True).rename("lvl_garch")
        gs.index.names = ["date", "symbol"]
        test = test.merge(gs.reset_index(), on=["date", "symbol"], how="left")
        test["lvl_har"] = har_prevoir(test, har_ajuster(train))
        test["lvl_hybride"] = _rang_vers_niveau(test, "pred", "lvl_har")
        test["garch_ab"] = f"{a:.3f}/{b:.3f}"
        sorties.append(test)
    return pd.concat(sorties, ignore_index=True) if sorties else pd.DataFrame()


def _pertes_par_date(t: pd.DataFrame, col: str, winsor: bool = False) -> pd.Series:
    """QLIKE moyenne par date. `winsor` (§ 4.17, étape 2) : QLIKE ramenées aux centiles 1 % et 99 % des titres de la date."""
    ok = t[[col, "brut"]].notna().all(axis=1) & (t[col] > 0) & (t["brut"] > 0)
    q = t[ok].assign(_q=qlike(t.loc[ok, col], t.loc[ok, "brut"]))
    if winsor:
        g = q.groupby("date")["_q"]
        q["_q"] = q["_q"].clip(g.transform(lambda x: x.quantile(0.01)), g.transform(lambda x: x.quantile(0.99)))
    return q.groupby("date")["_q"].mean()


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


def comparer_hybride(t: pd.DataFrame, h: int = H) -> dict:
    """Règle 1 de la PR #27 (docs/METHODE.md § 4.9) : l'hybride est publié si (a) il n'est pas nettement
    moins bon que HAR en QLIKE et (b) son IC bat la volatilité 3 mois avec une force ≥ 100 %.
    4ᵉ essai de la famille « références » : seuil corrigé pour 4."""
    p_hyb, p_har = _pertes_par_date(t, "lvl_hybride"), _pertes_par_date(t, "lvl_har")
    n_eff = max(1.0, len(p_hyb) * mh.PAS_ECHANTILLON / h)
    seuil = mh.seuil_t(n_eff, n_candidats=4)
    dm = diebold_mariano(p_hyb, p_har, decalage=max(1, h // mh.PAS_ECHANTILLON))
    tt = t.assign(rel=t["brut"])
    ic_h, ic_r = mh._ic_par_date(tt.dropna(subset=["lvl_hybride"]), "lvl_hybride"), mh._ic_par_date(tt, "lvl_vol_3m")
    g = (ic_h - ic_r).dropna()
    t_ic = float(g.mean() / g.std() * np.sqrt(n_eff)) if g.std() > 0 else 0.0
    force_har = dm["t"] / seuil              # > 100 % : HAR nettement meilleur que l'hybride
    force_ic = t_ic / seuil
    publie = bool(force_har < 1.0 and force_ic >= 1.0)
    return {"qlike": {"hybride": float(p_hyb.mean()), "har": float(p_har.mean()),
                      "ia": float(_pertes_par_date(t, "lvl_ia").mean())},
            "ic": {"hybride": float(ic_h.mean()), "vol_3m": float(ic_r.mean()),
                   "har": float(mh._ic_par_date(tt.dropna(subset=["lvl_har"]), "lvl_har").mean())},
            "dm_contre_har": dm, "force_har_meilleur": force_har, "t_ic": t_ic, "force_ic": force_ic,
            "seuil": seuil, "n_effectif": n_eff, "calibration": calibration(t, "lvl_hybride"),
            "publie": publie, "decision": "hybride" if publie else "har"}


def ia_contre_har(t: pd.DataFrame, h: int = H) -> dict:
    """Règle 6 de la PR #27 : l'IA reste dans l'hybride seulement si elle bat HAR sur l'ORDRE des titres
    (écart d'IC par date hybride − HAR, force de la preuve ≥ 100 %, seuil corrigé pour 5 essais)."""
    tt = t.assign(rel=t["brut"]).dropna(subset=["lvl_hybride", "lvl_har"])
    ic_h, ic_r = mh._ic_par_date(tt, "lvl_hybride"), mh._ic_par_date(tt, "lvl_har")
    g = (ic_h - ic_r).dropna()
    n_eff = max(1.0, len(g) * mh.PAS_ECHANTILLON / h)
    seuil = mh.seuil_t(n_eff, n_candidats=5)
    t_ic = float(g.mean() / g.std() * np.sqrt(n_eff)) if g.std() > 0 else 0.0
    force = t_ic / seuil
    return {"ic_hybride": float(ic_h.mean()), "ic_har": float(ic_r.mean()), "gain": float(g.mean()),
            "part_dates_gagnantes": float((g > 0).mean()), "t": t_ic, "seuil": seuil, "force": force,
            "n_effectif": n_eff, "ia_reste": bool(force >= 1.0), "decision": "hybride" if force >= 1.0 else "har"}


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


def placebo(data: pd.DataFrame, ret: pd.DataFrame, config: str = "xgb_prudent", n_tirages: int = 10) -> dict:
    """Règle 4 de la PR #27 : moyenne de n_tirages cibles mélangées, |moyenne| < 2 %."""
    ic_tirages = []
    for g in range(n_tirages):
        tm = walk_forward(data, ret, forcer_config=config, transformer=_melanger(g), references=False)
        if not tm.empty:
            ic_tirages.append(float(mh._ic_par_date(tm.assign(rel=tm["brut"]), "pred").mean()))
    t_fui = walk_forward(data, ret, forcer_config=config, transformer=_fuite(), references=False)
    rng = np.random.default_rng(1)
    d2 = data.assign(bruit=rng.uniform(0, 1, len(data)))
    feats = mh.FEATURES + ["bruit"]
    train = d2[d2["date"] < d2["date"].quantile(0.6)]
    m = mh._modele(config).fit(train[feats], train["y"])
    imp = pd.Series(mh._importances(m, config), index=feats)
    imp = imp / imp.sum() if imp.sum() > 0 else imp
    ic = lambda t: float(mh._ic_par_date(t.assign(rel=t["brut"]), "pred").mean()) if not t.empty else None
    moy = float(np.mean(ic_tirages)) if ic_tirages else None
    return {"ic_cible_melangee": moy, "ic_tirages": ic_tirages,
            "ecart_type_tirages": float(np.std(ic_tirages)) if ic_tirages else None,
            "ic_fuite_volontaire": ic(t_fui),
            "importance_facteur_aleatoire": float(imp["bruit"]),
            "importance_rang_facteur_aleatoire": int((imp > imp["bruit"]).sum()) + 1, "n_facteurs": len(feats)}


def sensibilite(data: pd.DataFrame, ret: pd.DataFrame) -> dict:
    """Gain d'IC (IA − volatilité 3 mois) pour chaque réglage du modèle, imposé sur toutes les fenêtres."""
    out = {}
    for config in mh.CONFIGS:
        t = walk_forward(data, ret, forcer_config=config, references=False).assign(rel=lambda x: x["brut"])
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


# ------------------------------------------------------------------------------
# Essai « XGBoost sur le niveau » (protocole : docs/METHODE.md § 4.10, écrit avant l'essai)
# ------------------------------------------------------------------------------
FEATURES_NIVEAU = ["ln_vol_3m", "ln_ewma", "ln_v5", "ln_v22", "ln_har", "ln_marche", "disp_marche"]
N_CANDIDATS_NIVEAU = 7          # 5 essais déjà comptés dans la famille « références » + A et B


def _ln(x) -> pd.Series:
    return np.log(np.maximum(pd.Series(x, dtype=float), 1e-8))


def ajouter_niveaux(df: pd.DataFrame, coef_har: np.ndarray) -> pd.DataFrame:
    """Variables de niveau (en logarithme), toutes connues à la date t."""
    df = df.copy()
    df["lvl_har"] = har_prevoir(df, coef_har)
    df["ln_vol_3m"] = _ln(df["lvl_vol_3m"]).values
    df["ln_ewma"] = _ln(df["lvl_ewma"]).values
    df["ln_v5"] = 0.5 * _ln(df["v5"] * 252).values
    df["ln_v22"] = 0.5 * _ln(df["v22"] * 252).values
    df["ln_har"] = _ln(df["lvl_har"]).values
    g = df.groupby("date")["ln_vol_3m"]
    df["ln_marche"] = g.transform("median")
    df["disp_marche"] = g.transform("std")
    return df.replace([np.inf, -np.inf], np.nan)


def walk_forward_niveau(data: pd.DataFrame, variante: str = "B", h: int = H, melange: bool = False,
                        graine: int = 0) -> pd.DataFrame:
    """Prévision du NIVEAU de volatilité par XGBoost prudent (config fixe, aucun réglage).
    variante « A » : cible ln(σ réalisée) ; « B » : cible ln(σ réalisée / σ HAR). `melange` : placebo."""
    feats = list(mh.FEATURES) + FEATURES_NIVEAU
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
        coef = har_ajuster(train)
        train, test = ajouter_niveaux(train, coef), ajouter_niveaux(test, coef)
        train = train[(train["brut"] > 0) & (train["lvl_har"] > 0)]
        ancre = np.log(train["lvl_har"]) if variante == "B" else 0.0
        y = np.log(train["brut"]) - ancre
        if melange:
            y = pd.Series(np.random.default_rng(graine + k).permutation(y.values), index=y.index)
        m = mh._modele("xgb_prudent").fit(train[feats], y)
        lissage = float(np.sqrt(np.mean(np.exp(2 * (y.values - m.predict(train[feats]))))))
        base = test["lvl_har"].values if variante == "B" else 1.0
        test["lvl_xgb"] = base * np.exp(m.predict(test[feats])) * lissage
        test["fenetre"], test["lissage"] = k, lissage
        sorties.append(test)
    return pd.concat(sorties, ignore_index=True) if sorties else pd.DataFrame()


def comparer_niveau(tb: pd.DataFrame, ta: pd.DataFrame | None = None, tp: pd.DataFrame | None = None,
                    h: int = H) -> dict:
    """Règles 1 à 5 du § 4.10. tb : variante B ; ta : variante A (diagnostic) ; tp : placebo de B."""
    lag = max(1, h // mh.PAS_ECHANTILLON)

    def dm_contre_har(t, col):
        a, b = _pertes_par_date(t, col), _pertes_par_date(t, "lvl_har")
        n_eff = max(1.0, len(a) * mh.PAS_ECHANTILLON / h)
        seuil = mh.seuil_t(n_eff, n_candidats=N_CANDIDATS_NIVEAU)
        dm = diebold_mariano(a, b, decalage=lag)
        return {"qlike": float(a.mean()), "qlike_har": float(b.mean()), "ecart": dm["ecart"], "t": dm["t"],
                "seuil": seuil, "force": -dm["t"] / seuil, "n_effectif": n_eff}

    out = {"B": dm_contre_har(tb, "lvl_xgb")}
    _b, _h = _pertes_par_date(tb, "lvl_xgb"), _pertes_par_date(tb, "lvl_har")
    out["inference_v2"] = inf.rapport_dm((_b - _h.reindex(_b.index)).dropna().values, h / mh.PAS_ECHANTILLON)
    r1 = out["B"]["force"] >= 1.0
    if ta is not None and not ta.empty:
        out["A"] = dm_contre_har(ta, "lvl_xgb")
    placebo_ok = True
    if tp is not None and not tp.empty:
        out["placebo"] = dm_contre_har(tp, "lvl_xgb")
        placebo_ok = not (out["placebo"]["force"] >= 1.0 or out["placebo"]["ecart"] < 0)
    # Règle 3 : crises (rapport des QLIKE moyennes B / HAR, dates de test dans la crise)
    pb, ph = _pertes_par_date(tb, "lvl_xgb"), _pertes_par_date(tb, "lvl_har")
    crises = {}
    for nom, (d0, d1) in CRISES.items():
        i = (pb.index >= pd.Timestamp(d0)) & (pb.index <= pd.Timestamp(d1))
        if i.sum() >= 3:
            crises[nom] = {"ratio": float(pb[i].mean() / ph.reindex(pb.index)[i].mean()), "n_dates": int(i.sum())}
    cles = [k for k in crises if k.startswith("2008") or k.startswith("2020")]
    crises_ok = bool(cles) and all(crises[k]["ratio"] <= 1.10 for k in cles)
    tt = tb.assign(rel=tb["brut"])
    out.update({
        "crises": crises, "crises_ok": crises_ok, "placebo_ok": placebo_ok,
        "ic": {"xgb": float(mh._ic_par_date(tt.dropna(subset=["lvl_xgb"]), "lvl_xgb").mean()),
               "har": float(mh._ic_par_date(tt.dropna(subset=["lvl_har"]), "lvl_har").mean())},
        "calibration": calibration(tb, "lvl_xgb"), "calibration_har": calibration(tb, "lvl_har"),
        "lissage_moyen": float(tb["lissage"].mean()),
        "regles": {"1_niveau": bool(r1), "2_placebo": placebo_ok, "3_crises": crises_ok},
    })
    out["candidate"] = bool(r1 and placebo_ok and crises_ok)
    return out


# ------------------------------------------------------------------------------
# Essai « HAR remis à l'échelle » (protocole : docs/METHODE.md § 4.11, écrit avant l'essai)
# ------------------------------------------------------------------------------
N_CANDIDATS_ECHELLE = 8          # 7 essais déjà comptés + celui-ci


def walk_forward_echelle(data: pd.DataFrame, h: int = H) -> pd.DataFrame:
    """HAR × k : k² = moyenne(σ_réelle² / σ_HAR²) sur l'entraînement de chaque fenêtre (passé seulement)."""
    dates = np.sort(data["date"].unique())
    bornes = np.array_split(dates[len(dates) // 3:], mh.N_FENETRES)
    embargo = pd.Timedelta(days=int(h * 7 / 5) + 1)
    sorties = []
    for k_, bloc in enumerate(bornes):
        debut = pd.Timestamp(bloc[0])
        train = data[data["date"] < debut - embargo]
        test = data[data["date"].isin(bloc)].copy()
        if len(train) < 2000 or test.empty:
            continue
        coef = har_ajuster(train)
        lvl_tr = har_prevoir(train, coef)
        ok = np.isfinite(lvl_tr) & (lvl_tr > 0) & (train["brut"].values > 0)
        k = float(np.sqrt(np.mean(train["brut"].values[ok] ** 2 / lvl_tr[ok] ** 2)))
        test["lvl_har"] = har_prevoir(test, coef)
        test["lvl_echelle"] = test["lvl_har"] * k
        test["fenetre"], test["k"] = k_, k
        sorties.append(test)
    return pd.concat(sorties, ignore_index=True) if sorties else pd.DataFrame()


def comparer_echelle(t: pd.DataFrame, h: int = H) -> dict:
    """Règles 1 à 4 du § 4.11."""
    a, b = _pertes_par_date(t, "lvl_echelle"), _pertes_par_date(t, "lvl_har")
    n_eff = max(1.0, len(a) * mh.PAS_ECHANTILLON / h)
    seuil = mh.seuil_t(n_eff, n_candidats=N_CANDIDATS_ECHELLE)
    dm = diebold_mariano(a, b, decalage=max(1, h // mh.PAS_ECHANTILLON))
    force = -dm["t"] / seuil
    crises = {}
    for nom, (d0, d1) in CRISES.items():
        i = (a.index >= pd.Timestamp(d0)) & (a.index <= pd.Timestamp(d1))
        if i.sum() >= 3:
            crises[nom] = {"ratio": float(a[i].mean() / b.reindex(a.index)[i].mean()), "n_dates": int(i.sum())}
    cles = [c for c in crises if c.startswith("2008") or c.startswith("2020")]
    crises_ok = bool(cles) and all(crises[c]["ratio"] <= 1.10 for c in cles)
    par_fenetre = {}
    for f, g in t.groupby("fenetre"):
        pe, ph = _pertes_par_date(g, "lvl_echelle"), _pertes_par_date(g, "lvl_har")
        par_fenetre[int(f)] = {"qlike": float(pe.mean()), "qlike_har": float(ph.mean()), "k": float(g["k"].iloc[0]),
                               "debut": str(pd.Timestamp(g["date"].min()).date())}
    n_mieux = sum(1 for v in par_fenetre.values() if v["qlike"] < v["qlike_har"])
    stable = n_mieux >= 3
    regles = {"1_niveau": bool(force >= 1.0), "2_crises": crises_ok, "3_stabilite": stable}
    return {"inference_v2": inf.rapport_dm((a - b.reindex(a.index)).dropna().values, h / mh.PAS_ECHANTILLON),
            "qlike": float(a.mean()), "qlike_har": float(b.mean()), "ecart": dm["ecart"], "t": dm["t"], "seuil": seuil,
            "force": float(force), "n_effectif": n_eff, "crises": crises, "par_fenetre": par_fenetre,
            "fenetres_meilleures": n_mieux, "calibration": calibration(t, "lvl_echelle"),
            "calibration_har": calibration(t, "lvl_har"), "regles": regles, "candidate": bool(all(regles.values()))}


# ------------------------------------------------------------------------------
# Essai « multi-horizon » (protocole : docs/METHODE.md § 4.13, écrit avant l'essai)
# ------------------------------------------------------------------------------
HORIZONS_MULTI = [5, 22, 63, 126]
MARGE_EQUIVALENCE = 0.01          # Δ de QLIKE pour le test d'équivalence (TOST), fixée avant l'essai


def _ecarts_par_horizon(par_h: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """Une colonne par horizon : QLIKE(B) − QLIKE(HAR) par date (moyenne sur les titres), dates communes."""
    cols = {}
    for h, t in par_h.items():
        cols[h] = _pertes_par_date(t, "lvl_xgb") - _pertes_par_date(t, "lvl_har")
    return pd.DataFrame(cols).dropna()


def comparer_multi(par_h: dict[int, pd.DataFrame], placebo: dict[int, pd.DataFrame] | None = None) -> dict:
    """Règles 1 à 5 du § 4.13. Statistique primaire : moyenne (poids égaux) des écarts de QLIKE sur les horizons."""
    from scipy import stats
    D = _ecarts_par_horizon(par_h)
    h_max = max(par_h)
    d = D.mean(axis=1)
    out = {"horizons": sorted(par_h), "n_dates_communes": int(len(D))}
    r = inf.rapport_dm(d.values, h_max / mh.PAS_ECHANTILLON)
    nu = r.get("nu", 18)
    tq = float(stats.t.ppf(0.95, nu))
    r["ic90"] = [r["ecart"] - tq * r["erreur_type"], r["ecart"] + tq * r["erreur_type"]]
    out["aspa"] = r
    out["par_horizon"] = {int(h): inf.rapport_dm(D[h].values, h / mh.PAS_ECHANTILLON) for h in D.columns}
    out["holm"] = inf.holm({str(h): v["p_bilatere"] for h, v in out["par_horizon"].items()})
    blocs = np.array_split(d.values, 4)
    out["blocs_negatifs"] = int(sum(b.mean() < 0 for b in blocs))
    out["blocs"] = [float(b.mean()) for b in blocs]
    out["ic"] = {int(h): {"xgb": float(mh._ic_par_date(t.assign(rel=t["brut"]).dropna(subset=["lvl_xgb"]), "lvl_xgb").mean()),
                          "har": float(mh._ic_par_date(t.assign(rel=t["brut"]).dropna(subset=["lvl_har"]), "lvl_har").mean())}
                 for h, t in par_h.items()}
    crises = {}
    for nom, (d0, d1) in CRISES.items():
        i = (d.index >= pd.Timestamp(d0)) & (d.index <= pd.Timestamp(d1))
        if i.sum() >= 3:
            crises[nom] = {"ecart_moyen": float(d[i].mean()), "n_dates": int(i.sum())}
    out["crises"] = crises
    t_pl = None
    if placebo:
        rp = inf.rapport_dm(_ecarts_par_horizon(placebo).mean(axis=1).values, h_max / mh.PAS_ECHANTILLON)
        out["placebo"] = rp
        t_pl = rp.get("t")
    t = r.get("t", 0.0)
    out["regles"] = {
        "1_piste": bool(t <= -2 and out["blocs_negatifs"] >= 3 and (t_pl is None or t_pl > -2)),
        "2_fuite_probable": bool(t_pl is not None and t_pl <= -2),
        "3_B_pire": bool(t >= 2),
        "4_equivalence": bool(r["ic90"][0] > -MARGE_EQUIVALENCE and r["ic90"][1] < MARGE_EQUIVALENCE),
    }
    out["peut_conclure_equivalence"] = bool(r["mde_80"] < MARGE_EQUIVALENCE)
    return out


# ------------------------------------------------------------------------------
# Essai « HAR-X : HAR + VIX » (protocole : docs/METHODE.md § 4.14, écrit avant tout code)
# ------------------------------------------------------------------------------
HORIZONS_HARX = [126, 22, 5]          # 126 : primaire ; 22 : secondaire ; 5 : constat (additif du § 4.14)
FAMILLE_HARX = [126, 22]              # famille confirmatoire, corrigée par Holm
ALPHA_HARX = 0.005                    # règle 2 (a) : p unilatéral corrigé < 0,5 %
DECALAGE_PLACEBO_VIX = 252            # règle 3 : vrai VIX, un an trop tôt
MDE_MAX_HARX = 0.03                   # additif : au-delà, ni candidat ni équivalence (règle v2 n° 2)
SEUIL_CRISE_HARX = 1.10               # règle 2 (c)
N_ESSAIS_HARX = 10                    # famille « références » : 8 (§ 9) + multi-horizon (§ 10) + HAR-X
COLS_HAR = ["v1", "v5", "v22", "v63"]


def beta_brut(ret: pd.DataFrame, rm: pd.Series | None = None) -> pd.DataFrame:
    """Bêta sur 1 an (252 jours) de chaque titre contre le marché, valeurs brutes (pas des rangs), passé seulement."""
    rm = ret[mh.INDICE] if rm is None else rm
    return ret.rolling(252).cov(rm).div(rm.rolling(252).var(), axis=0)


def beta_depuis_cours(market_raw: pd.DataFrame, symboles: list[str]) -> pd.DataFrame:
    """Bêta brut sur 1 an à partir des cours bruts (les rendements de `preparer` n'ont pas l'indice)."""
    m = market_raw[market_raw["symbol"].isin(set(symboles) | {mh.INDICE})]
    px = m.pivot_table(index="date", columns="symbol", values="close").sort_index().ffill(limit=5)
    return beta_brut(px.pct_change()).drop(columns=[mh.INDICE])


def ajouter_x_vix(data: pd.DataFrame, beta: pd.DataFrame, vix: pd.Series, decalage: int = 0) -> pd.DataFrame:
    """Ajoute `x = β̂² × (VIX/100)² / 252` (variance quotidienne « marché » anticipée par les options).
    `decalage` > 0 : VIX de `decalage` jours de bourse plus tôt (placebo, règle 3). Clôture du jour de la prévision."""
    v = vix.dropna().sort_index()
    v = v.shift(decalage) if decalage else v
    dates = pd.DatetimeIndex(np.sort(data["date"].unique()))
    v = v.reindex(v.index.union(dates)).ffill(limit=5).reindex(dates)
    b = beta.reindex(dates).stack(future_stack=True).rename("beta_brut")
    b.index.names = ["date", "symbol"]
    out = data.drop(columns=["beta_brut", "vix_j", "x_vix"], errors="ignore").merge(b.reset_index(), on=["date", "symbol"], how="left")
    out["vix_j"] = out["date"].map(v)
    out["x_vix"] = out["beta_brut"] ** 2 * (out["vix_j"] / 100) ** 2 / 252
    return out


def _mco(train: pd.DataFrame, cols: list[str]) -> np.ndarray:
    X = np.column_stack([np.ones(len(train))] + [train[c].values for c in cols])
    coef, *_ = np.linalg.lstsq(X, train["brut"].values ** 2 / 252, rcond=None)
    return coef


def _prevoir(df: pd.DataFrame, cols: list[str], coef: np.ndarray) -> np.ndarray:
    X = np.column_stack([np.ones(len(df))] + [df[c].values for c in cols])
    return np.sqrt(np.maximum(X @ coef, df["v63"].values * 0.25) * 252)      # même garde-fou que har_prevoir


def walk_forward_harx(data: pd.DataFrame, h: int = H) -> pd.DataFrame:
    """HAR et HAR-X ajustés sur les MÊMES lignes du passé (fenêtres et embargo de `walk_forward`), prévus sur les mêmes
    lignes de test. `data` doit contenir `x_vix` (voir `ajouter_x_vix`). Seule différence entre les deux : la variable x."""
    cols_x = COLS_HAR + ["x_vix"]
    d = data[np.isfinite(data[cols_x + ["brut"]]).all(axis=1) & (data["brut"] > 0)]
    dates = np.sort(data["date"].unique())
    bornes = np.array_split(dates[len(dates) // 3:], mh.N_FENETRES)
    embargo = pd.Timedelta(days=int(h * 7 / 5) + 1)
    sorties = []
    for k, bloc in enumerate(bornes):
        debut = pd.Timestamp(bloc[0])
        train = d[d["date"] < debut - embargo]
        test = d[d["date"].isin(bloc)].copy()
        if len(train) < 2000 or test.empty:
            continue
        c_har, c_x = _mco(train, COLS_HAR), _mco(train, cols_x)
        test["lvl_har"] = _prevoir(test, COLS_HAR, c_har)
        test["lvl_harx"] = _prevoir(test, cols_x, c_x)
        test["fenetre"] = k
        test["coef_vix"] = float(c_x[-1])
        # Part de variance prévue venant du VIX (médiane), pour lire le coefficient en ordre de grandeur
        var_prevue = np.maximum(test["lvl_harx"].values ** 2 / 252, 1e-12)
        test["part_vix"] = float(np.median(c_x[-1] * test["x_vix"].values / var_prevue))
        sorties.append(test)
    return pd.concat(sorties, ignore_index=True) if sorties else pd.DataFrame()


def _ecart_harx(t: pd.DataFrame, winsor: bool = False) -> pd.Series:
    return (_pertes_par_date(t, "lvl_harx", winsor) - _pertes_par_date(t, "lvl_har", winsor)).dropna()


def comparer_harx(par_h: dict[int, pd.DataFrame], placebo_h: dict[int, pd.DataFrame], n_essais_total: int = N_ESSAIS_HARX,
                  winsor: bool = False) -> dict:
    """Règles 1 à 7 du § 4.14 (et son additif). d = QLIKE(HAR-X) − QLIKE(HAR) par date ; d < 0 : HAR-X meilleur."""
    from scipy import stats
    out = {"horizons": {}, "n_essais_total": n_essais_total, "t_max_attendu": inf.t_max_attendu(n_essais_total)}
    for h, t in sorted(par_h.items(), reverse=True):
        d = _ecart_harx(t, winsor)
        r = inf.rapport_dm(d.values, h / mh.PAS_ECHANTILLON)
        fen = t.groupby("date")["fenetre"].first().reindex(d.index)
        par_fen = d.groupby(fen).mean()
        rp = inf.rapport_dm(_ecart_harx(placebo_h[h], winsor).values, h / mh.PAS_ECHANTILLON) if h in placebo_h else {}
        # Constat (précision du 22/11/2026, avant tout résultat) : x = β² × VIX² porte aussi le bêta, que le placebo garde.
        # HAR-X contre son placebo isole l'apport du VIX lui-même (même bêta, VIX au bon moment ou un an trop tôt).
        vp = (inf.rapport_dm((_pertes_par_date(t, "lvl_harx", winsor) - _pertes_par_date(placebo_h[h], "lvl_harx", winsor)).dropna().values,
                             h / mh.PAS_ECHANTILLON) if h in placebo_h else {})
        crises = {}
        for nom, (d0, d1) in CRISES.items():
            g = t[(t["date"] >= pd.Timestamp(d0)) & (t["date"] <= pd.Timestamp(d1))]
            if g["date"].nunique() >= 3:
                qh, qx = _pertes_par_date(g, "lvl_har", winsor).mean(), _pertes_par_date(g, "lvl_harx", winsor).mean()
                crises[nom] = {"ratio_qlike_harx_sur_har": float(qx / qh) if qh > 0 else None, "n_dates": int(g["date"].nunique())}
        ok = t[["lvl_har", "lvl_harx", "brut"]].notna().all(axis=1)
        mse = {c: float(((t.loc[ok, c] - t.loc[ok, "brut"]) ** 2).mean()) for c in ["lvl_har", "lvl_harx"]}
        tt = t.assign(rel=t["brut"])
        res = {
            "dm": r, "n_dates": int(len(d)),
            "qlike": {"har": float(_pertes_par_date(t, "lvl_har", winsor).mean()), "harx": float(_pertes_par_date(t, "lvl_harx", winsor).mean())},
            "par_fenetre": {int(k): float(v) for k, v in par_fen.items()},
            "fenetres_negatives": int((par_fen < 0).sum()), "n_fenetres": int(len(par_fen)),
            "coef_vix_par_fenetre": {int(k): float(v) for k, v in t.groupby("fenetre")["coef_vix"].first().items()},
            "part_vix_par_fenetre": {int(k): float(v) for k, v in t.groupby("fenetre")["part_vix"].first().items()},
            "placebo": rp, "harx_contre_placebo": vp, "crises": crises, "mse": mse,
            "calibration": {"har": calibration(t, "lvl_har"), "harx": calibration(t, "lvl_harx")},
            "ic": {"har": float(mh._ic_par_date(tt, "lvl_har").mean()), "harx": float(mh._ic_par_date(tt, "lvl_harx").mean())},
        }
        tq = float(stats.t.ppf(0.95, r.get("nu", 18)))
        res["ic90"] = [r["ecart"] - tq * r["erreur_type"], r["ecart"] + tq * r["erreur_type"]] if "ecart" in r else None
        out["horizons"][int(h)] = res
    H_ = out["horizons"]
    out["holm"] = inf.holm({str(h): H_[h]["dm"].get("p_unilateral_A_meilleur", 1.0) for h in FAMILLE_HARX if h in H_}, alpha=ALPHA_HARX)
    regles = {}
    for h, res in H_.items():
        r, t_ = res["dm"], res["dm"].get("t", 0.0)
        t_pl = res["placebo"].get("t")
        mde_ok = r.get("mde_80", 1.0) <= MDE_MAX_HARX
        regles[h] = {
            "1_piste": bool(t_ <= -2 and r.get("ecart", 0) < 0 and res["fenetres_negatives"] >= 3),
            "3_placebo_ne_bat_pas_har": bool(t_pl is None or t_pl > -2),
            "4_pire_que_har": bool(t_ >= 2),
            "5_equivalence": bool(mde_ok and r.get("mde_80", 1.0) < MARGE_EQUIVALENCE and res["ic90"] is not None
                                  and res["ic90"][0] > -MARGE_EQUIVALENCE and res["ic90"][1] < MARGE_EQUIVALENCE),
            "mde_permet_candidat": bool(mde_ok),
            "coef_vix_signe_stable": bool(len({np.sign(v) for v in res["coef_vix_par_fenetre"].values()}) == 1),
        }
    r126 = H_.get(126)
    if r126:
        ratios = [r126["crises"].get(k, {}).get("ratio_qlike_harx_sur_har") for k in ("2008-2009 (crise financière)", "2020 (Covid)")]
        regles[126].update({
            "2a_holm": bool(out["holm"].get("126", {}).get("rejete", False)),
            "2b_ecart_economique": bool(r126["dm"].get("ecart", 0) <= -MARGE_EQUIVALENCE),
            "2c_crises": bool(all(x is not None and x <= SEUIL_CRISE_HARX for x in ratios)),
        })
        regles[126]["2abc"] = bool(regles[126]["mde_permet_candidat"] and regles[126]["2a_holm"]
                                   and regles[126]["2b_ecart_economique"] and regles[126]["2c_crises"])
    out["regles"] = regles
    return out


def replication_harx(t_mid: pd.DataFrame) -> dict:
    """Règle 2 (d) : même essai sur le S&P MidCap 400, 126 jours ; t ≤ −2 dans le même sens."""
    r = inf.rapport_dm(_ecart_harx(t_mid).values, H / mh.PAS_ECHANTILLON)
    return {"dm": r, "replique": bool(r.get("t", 0) <= -2 and r.get("ecart", 0) < 0)}


def verdict_harx(c: dict, replication: dict | None = None) -> str:
    """Verdict selon le § 4.14 (ordre : placebo, candidat, piste, pire, équivalence, sans pouvoir de conclure)."""
    R = c["regles"]
    morceaux = []
    for h in sorted(R, reverse=True):
        r = R[h]
        if h not in FAMILLE_HARX:
            continue
        if r["1_piste"] and not r["3_placebo_ne_bat_pas_har"]:
            morceaux.append(f"{h} j : écarté (placebo significatif)")
        elif h == 126 and r.get("2abc") and replication and replication["replique"] and r["coef_vix_signe_stable"]:
            morceaux.append(f"{h} j : CANDIDAT")
        elif r["1_piste"] and r["coef_vix_signe_stable"]:
            morceaux.append(f"{h} j : piste")
        elif r["1_piste"]:
            morceaux.append(f"{h} j : écarté (coefficient du VIX instable)")
        elif r["4_pire_que_har"]:
            morceaux.append(f"{h} j : pire que HAR")
        elif r["5_equivalence"]:
            morceaux.append(f"{h} j : équivalent à HAR")
        else:
            morceaux.append(f"{h} j : sans pouvoir de conclure")
    return " ; ".join(morceaux)


# ------------------------------------------------------------------------------
# Essai « HAR étendu » (protocole : docs/METHODE.md § 4.15, écrit avant tout code)
# ------------------------------------------------------------------------------
COLS_COURS = ["v126", "v252", "rsm22", "x_beta"]        # M1 : informations tirées des cours, au-delà de HAR
COLS_MARCHE = ["x_vix", "credit_v63", "pente_v63"]      # M2 : marché (options) et macro, décalées au placebo
N_ESSAIS_ETENDU = 11


def variables_cours(market_raw: pd.DataFrame, symboles: list[str]) -> dict[str, pd.DataFrame]:
    """Tables larges (date × titre), passé seulement : v126, v252, semivariance négative 22 j, β̂² × variance du SPY 22 j, β̂."""
    m = market_raw[market_raw["symbol"].isin(set(symboles) | {mh.INDICE})]
    px = m.pivot_table(index="date", columns="symbol", values="close").sort_index().ffill(limit=5)
    ret = px.pct_change()
    beta = beta_brut(ret)
    r2 = ret.pow(2)
    var_m22 = r2[mh.INDICE].rolling(22).mean()
    out = {"v126": r2.rolling(126).mean(), "v252": r2.rolling(252).mean(),
           "rsm22": r2.where(ret < 0, 0.0).where(ret.notna()).rolling(22).mean(),
           "x_beta": beta.pow(2).mul(var_m22, axis=0), "beta": beta}
    return {k: v.drop(columns=[mh.INDICE]) for k, v in out.items()}


def ajouter_etendu(data: pd.DataFrame, tables: dict[str, pd.DataFrame], vix: pd.Series, macro: pd.DataFrame,
                   decalage: int = 0) -> pd.DataFrame:
    """Ajoute les variables de M1 et M2. `macro` : colonnes credit (BAA10Y) et pente (T10Y2Y), au jour de publication ;
    on prend la valeur de la VEILLE. `decalage` (placebo) ne touche que VIX, crédit et pente."""
    dates = pd.DatetimeIndex(np.sort(data["date"].unique()))
    out = data.drop(columns=COLS_COURS + ["credit_v63", "pente_v63"], errors="ignore")
    for nom in COLS_COURS:
        s = tables[nom].reindex(dates).stack(future_stack=True).rename(nom)
        s.index.names = ["date", "symbol"]
        out = out.merge(s.reset_index(), on=["date", "symbol"], how="left")
    out = ajouter_x_vix(out, tables["beta"], vix, decalage)
    for col in ["credit", "pente"]:
        f = macro[col].dropna().sort_index().shift(1)                   # valeur connue la veille (publication)
        f = f.shift(decalage) if decalage else f
        f = f.reindex(f.index.union(dates)).ffill(limit=5).reindex(dates)
        out[f"{col}_v63"] = out["date"].map(f) * out["v63"]
    return out


def modeles_etendus(data: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    """Indicatrices de secteur (si `secteur` existe) et listes de variables de HAR, M1 et M2."""
    sect = []
    if "secteur" in data.columns and data["secteur"].nunique() > 1:
        dums = pd.get_dummies(data["secteur"], prefix="sect", drop_first=True).astype(float)
        data = pd.concat([data.drop(columns=[c for c in data.columns if c.startswith("sect_")]), dums], axis=1)
        sect = list(dums.columns)
    m1 = COLS_HAR + COLS_COURS + sect
    return data, {"har": COLS_HAR, "m1": m1, "m2": m1 + COLS_MARCHE}


def walk_forward_lineaire(data: pd.DataFrame, modeles: dict[str, list[str]], h: int = H) -> pd.DataFrame:
    """Plusieurs modèles linéaires ajustés sur les MÊMES lignes du passé (fenêtres et embargo de `walk_forward`).
    Colonnes ajoutées : lvl_<nom>, fenetre. Coefficients par fenêtre dans `attrs["coefs"]`."""
    toutes = sorted({c for cols in modeles.values() for c in cols})
    d = data[np.isfinite(data[toutes + ["brut"]].astype(float)).all(axis=1) & (data["brut"] > 0)]
    dates = np.sort(data["date"].unique())
    bornes = np.array_split(dates[len(dates) // 3:], mh.N_FENETRES)
    embargo = pd.Timedelta(days=int(h * 7 / 5) + 1)
    sorties, coefs = [], {}
    for k, bloc in enumerate(bornes):
        debut = pd.Timestamp(bloc[0])
        train = d[d["date"] < debut - embargo]
        test = d[d["date"].isin(bloc)].copy()
        if len(train) < 2000 or test.empty:
            continue
        coefs[k] = {}
        for nom, cols in modeles.items():
            c = _mco(train, cols)
            test[f"lvl_{nom}"] = _prevoir(test, cols, c)
            coefs[k][nom] = dict(zip(["constante"] + cols, map(float, c)))
        test["fenetre"] = k
        sorties.append(test)
    out = pd.concat(sorties, ignore_index=True) if sorties else pd.DataFrame()
    out.attrs["coefs"] = coefs
    return out


def _dm_cols(t: pd.DataFrame, a: str, b: str, h: int, t_b: pd.DataFrame | None = None) -> dict:
    """DM de QLIKE(a) − QLIKE(b) par date (d < 0 : a meilleur). `t_b` : autre tableau pour b (placebo)."""
    d = (_pertes_par_date(t, a) - _pertes_par_date(t if t_b is None else t_b, b)).dropna()
    r = inf.rapport_dm(d.values, h / mh.PAS_ECHANTILLON)
    fen = t.groupby("date")["fenetre"].first().reindex(d.index)
    par_fen = d.groupby(fen).mean()
    r["par_fenetre"] = {int(k): float(v) for k, v in par_fen.items()}
    r["fenetres_negatives"] = int((par_fen < 0).sum())
    return r


def comparer_etendu(t: pd.DataFrame, tp: pd.DataFrame, h: int = H) -> dict:
    """Règles 1 à 6 du § 4.15. `t` : vraies variables ; `tp` : placebo (marché et macro décalés de 252 jours)."""
    prim = _dm_cols(t, "lvl_m2", "lvl_har", h)
    out = {"m2_contre_har": prim,
           "m1_contre_har": _dm_cols(t, "lvl_m1", "lvl_har", h),
           "m2_contre_m1": _dm_cols(t, "lvl_m2", "lvl_m1", h),
           "placebo_contre_m1": _dm_cols(tp, "lvl_m2", "lvl_m1", h),
           "m2_contre_placebo": _dm_cols(t, "lvl_m2", "lvl_m2", h, t_b=tp),
           "qlike": {m: float(_pertes_par_date(t, f"lvl_{m}").mean()) for m in ("har", "m1", "m2")},
           "n_essais_total": N_ESSAIS_ETENDU, "t_max_attendu": inf.t_max_attendu(N_ESSAIS_ETENDU)}
    crises = {}
    for nom, (d0, d1) in CRISES.items():
        g = t[(t["date"] >= pd.Timestamp(d0)) & (t["date"] <= pd.Timestamp(d1))]
        if g["date"].nunique() >= 3:
            qh = _pertes_par_date(g, "lvl_har").mean()
            crises[nom] = {m: float(_pertes_par_date(g, f"lvl_{m}").mean() / qh) for m in ("m1", "m2")} | {"n_dates": int(g["date"].nunique())}
    out["crises_ratio_sur_har"] = crises
    mse = {m: float(((t[f"lvl_{m}"] - t["brut"]) ** 2).mean()) for m in ("har", "m1", "m2")}
    out["r2_hors_echantillon_sur_har"] = {m: 1 - mse[m] / mse["har"] for m in ("m1", "m2")}
    tt = t.assign(rel=t["brut"])
    out["ic"] = {m: float(mh._ic_par_date(tt, f"lvl_{m}").mean()) for m in ("har", "m1", "m2")}
    out["calibration"] = {m: calibration(t, f"lvl_{m}") for m in ("har", "m1", "m2")}
    coefs = t.attrs.get("coefs", {})
    out["coefs_m2_par_fenetre"] = {int(k): v.get("m2", {}) for k, v in coefs.items()}
    signes = {}
    for k, v in out["coefs_m2_par_fenetre"].items():
        for var, c in v.items():
            if not var.startswith("sect_") and var != "constante":
                signes.setdefault(var, set()).add(int(np.sign(c)))
    out["variables_signe_instable"] = sorted(var for var, s in signes.items() if len(s) > 1)
    ratios = [crises.get(k, {}).get("m2") for k in ("2008-2009 (crise financière)", "2020 (Covid)")]
    tval = prim.get("t", 0.0)
    out["regles"] = {
        "1_piste": bool(tval <= -2 and prim.get("ecart", 0) < 0 and prim["fenetres_negatives"] >= 3),
        "2a_p": bool(prim.get("p_unilateral_A_meilleur", 1.0) < ALPHA_HARX),
        "2b_ecart_economique": bool(prim.get("ecart", 0) <= -MARGE_EQUIVALENCE),
        "2c_crises": bool(all(x is not None and x <= SEUIL_CRISE_HARX for x in ratios)),
        "2d_mde": bool(prim.get("mde_80", 1.0) <= MDE_MAX_HARX),
        "3_placebo_ne_bat_pas_m1": bool(out["placebo_contre_m1"].get("t", 0.0) > -2),
        "4_pire_que_har": bool(tval >= 2),
    }
    R = out["regles"]
    R["2abcd"] = bool(R["2a_p"] and R["2b_ecart_economique"] and R["2c_crises"] and R["2d_mde"])
    return out


def verdict_etendu(c: dict, replication: dict | None = None) -> str:
    """Verdict du § 4.15 (règles 1 à 5) ; la lecture fine (M1, M2 contre M1) est dans les constats."""
    R = c["regles"]
    m1 = c["m1_contre_har"]
    m2m1 = c["m2_contre_m1"]
    suffixe = " ; marché et macro écartés (placebo bat M1)" if not R["3_placebo_ne_bat_pas_m1"] else ""
    if c["variables_signe_instable"] and R["1_piste"]:
        suffixe += " ; signes instables : " + ", ".join(c["variables_signe_instable"])
    if R["4_pire_que_har"]:
        return "M2 pire que HAR" + suffixe
    if R["2abcd"] and replication and replication["replique"] and R["3_placebo_ne_bat_pas_m1"]:
        return "M2 CANDIDAT" + suffixe
    if R["1_piste"]:
        source = ("marché et macro" if R["3_placebo_ne_bat_pas_m1"] and m2m1.get("t", 0) <= -2 else "cours (M1)"
                  if m1.get("t", 0) <= -2 else "non attribuée")
        return f"M2 piste (gain attribué : {source})" + suffixe
    return "sans pouvoir de conclure" + suffixe if c["m2_contre_har"].get("mde_80", 1) > MDE_MAX_HARX else "M2 ne bat pas HAR" + suffixe


def replication_etendu(t_mid: pd.DataFrame) -> dict:
    r = _dm_cols(t_mid, "lvl_m2", "lvl_har", H)
    return {"dm": r, "replique": bool(r.get("t", 0) <= -2 and r.get("ecart", 0) < 0)}


# ------------------------------------------------------------------------------
# Essai « Confirmation de HAR-X à 1 mois » (protocole : docs/METHODE.md § 4.16, écrit avant tout code)
# ------------------------------------------------------------------------------
H_MOIS = 22
N_ESSAIS_HARX_1M = 12
Z_STUDENT5_5PC = -2.015048372669157      # quantile 5 % de la loi de Student à 5 degrés (échelle σ, comme l'appli)
SEUIL_COUVERTURE = 0.075                 # 1,5 × 5 % (règle 5 de la PR #27)


def ajouter_rendement_futur(t: pd.DataFrame, market_raw: pd.DataFrame, h: int = H_MOIS) -> pd.DataFrame:
    """Ajoute `ret_futur` : rendement du titre de la date t à t + h séances (pour la couverture, jamais comme entrée)."""
    px = market_raw.pivot_table(index="date", columns="symbol", values="close").sort_index().ffill(limit=5)
    fut = (px.shift(-h) / px - 1).stack(future_stack=True).rename("ret_futur")
    fut.index.names = ["date", "symbol"]
    return t.drop(columns=["ret_futur"], errors="ignore").merge(fut.reset_index(), on=["date", "symbol"], how="left")


def couverture_1m(t: pd.DataFrame, col: str, h: int = H_MOIS) -> dict:
    """Part des (titre, date) où la baisse sur h séances dépasse le « mauvais cas 5 % » : z(Student 5) × σ prévue × √(h/252)."""
    ok = t[[col, "ret_futur"]].notna().all(axis=1) & (t[col] > 0)
    seuil = Z_STUDENT5_5PC * t.loc[ok, col] * np.sqrt(h / 252)
    part = float((t.loc[ok, "ret_futur"] < seuil).mean()) if ok.any() else None
    return {"part_depassements": part, "attendu": 0.05, "n": int(ok.sum()),
            "avertissement": bool(part is not None and part > SEUIL_COUVERTURE)}


def verdict_harx_1m(c_mid: dict) -> tuple[str, dict]:
    """Règle 1 du § 4.16 sur les midcaps à 22 jours. Retourne (verdict, conditions)."""
    r = c_mid["horizons"][H_MOIS]
    cond = {
        "a_t_et_ecart": bool(r["dm"].get("t", 0) <= -2 and r["dm"].get("ecart", 0) < 0),
        "b_fenetres": bool(r["fenetres_negatives"] >= 3),
        "c_placebo": bool(r["placebo"].get("t", 0) > -2),
        "d_signe_vix": bool(len({np.sign(v) for v in r["coef_vix_par_fenetre"].values()}) == 1),
    }
    if all(cond.values()):
        return "confirmé", cond
    return "non confirmé : " + ", ".join(k for k, ok in cond.items() if not ok), cond


COURS_MIN_NETTOYAGE = 5.0            # § 4.17, étape 1
SAUT_MAX_NETTOYAGE = 0.50            # |rendement quotidien| > 50 % entre t − 63 et t + h : donnée retirée
MDE_ETAPE_2 = 0.10                   # § 4.17 : la winsorisation n'est déclenchée que si le MDE dépasse ce seuil
N_ESSAIS_HARX_1M_V2 = 13


def nettoyer(data: pd.DataFrame, market_raw: pd.DataFrame, h: int = H_MOIS) -> tuple[pd.DataFrame, float]:
    """§ 4.17, étape 1 : retire (titre, date) si cours < 5 $ à la date, ou si un rendement quotidien dépasse ±50 %
    entre t − 63 et t + h séances. Règle de qualité des données, fixée avant l'essai. Retourne (données, part retirée)."""
    px = market_raw.pivot_table(index="date", columns="symbol", values="close").sort_index().ffill(limit=5)
    a = px.pct_change().abs()
    passe = a.rolling(64, min_periods=1).max()                                   # t − 63 à t
    futur = a[::-1].rolling(h, min_periods=1).max()[::-1].shift(-1)              # t + 1 à t + h
    mauvais = (px < COURS_MIN_NETTOYAGE) | (passe > SAUT_MAX_NETTOYAGE) | (futur > SAUT_MAX_NETTOYAGE)
    m = mauvais.stack(future_stack=True).rename("_mauvais")
    m.index.names = ["date", "symbol"]
    d = data.merge(m.reset_index(), on=["date", "symbol"], how="left")
    retire = d["_mauvais"].fillna(False).astype(bool)
    return d[~retire].drop(columns="_mauvais").reset_index(drop=True), float(retire.mean()) if len(d) else 0.0


def essai_harx_1m(market_raw: pd.DataFrame, symboles: list[str], vix: pd.Series, composition=None, secteurs=None,
                  nettoyage: bool = False, winsor: bool | None = None) -> dict:
    """HAR et HAR-X à 22 jours sur un univers : comparaison, placebo, couverture (§ 4.16).
    `nettoyage` (§ 4.17) : étape 1 ; puis étape 2 (QLIKE winsorisées) si `winsor` est True, ou, si `winsor` est None,
    seulement quand le MDE après nettoyage dépasse 0,10."""
    d = preparer(market_raw, symboles, composition, secteurs, h=H_MOIS)[0]
    part_retiree = None
    if nettoyage:
        d, part_retiree = nettoyer(d, market_raw)
    beta = beta_depuis_cours(market_raw, symboles)
    t = walk_forward_harx(ajouter_x_vix(d, beta, vix), h=H_MOIS)
    tp = walk_forward_harx(ajouter_x_vix(d, beta, vix, decalage=DECALAGE_PLACEBO_VIX), h=H_MOIS)
    n_essais = N_ESSAIS_HARX_1M_V2 if nettoyage else N_ESSAIS_HARX_1M
    c = comparer_harx({H_MOIS: t}, {H_MOIS: tp}, n_essais_total=n_essais)
    etape = 1
    if nettoyage:
        mde = c["horizons"][H_MOIS]["dm"].get("mde_80", np.inf)
        if winsor or (winsor is None and mde > MDE_ETAPE_2):
            c = comparer_harx({H_MOIS: t}, {H_MOIS: tp}, n_essais_total=n_essais, winsor=True)
            c["mde_etape_1"] = float(mde)
            etape = 2
        c["part_retiree"] = part_retiree
    c["etape"] = etape
    t = ajouter_rendement_futur(t, market_raw)
    c["couverture"] = {"harx": couverture_1m(t, "lvl_harx"), "har": couverture_1m(t, "lvl_har")}
    c["n_titres"] = int(t["symbol"].nunique())
    c["debut_test"] = str(pd.Timestamp(t["date"].min()).date()) if not t.empty else None
    return c
