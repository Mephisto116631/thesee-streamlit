# backtest_risque.py
# ==============================================================================
# BACKTEST : la volatilité prédite par l'IA améliore-t-elle le portefeuille ?
#
# Chaque mois de 2013 à aujourd'hui, on reconstruit le portefeuille comme l'appli
# (membres du S&P 500 ce jour-là, 3 ans d'historique, au plus 12 lignes, 20 % max
# par ligne, covariance factorielle et optimiseur FISTA de portefeuille.py), avec
# deux bases de candidats possibles :
#   sp500      : tous les membres (méthode de l'appli depuis la PR #25) ;
#   momentum40 : les 40 meilleurs au momentum 12-1 / volatilité (ancienne méthode) ;
# et trois estimations des volatilités :
#   hist_3a : covariance sur 3 ans (ce que fait l'appli aujourd'hui) ;
#   naif_3m : corrélations sur 3 ans, volatilités des 3 derniers mois ;
#   ia      : corrélations sur 3 ans, volatilités prédites par l'IA de risque,
#             réentraînée chaque année sur le passé SEULEMENT.
# Puis on mesure la volatilité RÉELLE du portefeuille le mois suivant.
# Deux portefeuilles : variance minimale (test pur du risque) et Sharpe maximal
# (le portefeuille « Hold » de l'appli).
# ==============================================================================
import numpy as np
import pandas as pd

import modele_horizon as mh
import modele_risque as mr
import portefeuille as pf

VARIANTES = ["hist_3a", "naif_3m", "ia"]   # + "hybride" (rang IA, niveaux HAR) sur demande
PORTEFEUILLES = {"variance_min": np.nan, "sharpe_max": None}   # cible passée à pf.optimiser
# Mode « Je limite le risque » de l'appli : le plus rentable sous une volatilité maximale
PORTEFEUILLES_RISQUE = {"risque_12": 0.12, "risque_15": 0.15}
BASES = ["sp500", "momentum40"]
TENUE = 21              # jours de bourse entre deux rééquilibrages
HORIZON_IA = "6m"


def _predictions_ia(data: pd.DataFrame, dates_rebal: list, h: int) -> pd.DataFrame:
    """Rang de volatilité future prédit pour chaque date de rééquilibrage, avec un modèle
    réentraîné chaque 1er janvier sur les seules données connues à ce moment-là."""
    embargo = pd.Timedelta(days=int(h * 7 / 5) + 1)
    sorties = []
    for annee in sorted({pd.Timestamp(d).year for d in dates_rebal}):
        debut = pd.Timestamp(f"{annee}-01-01")
        train = data[data["date"] < debut - embargo]
        cible = data[data["date"].isin([d for d in dates_rebal if pd.Timestamp(d).year == annee])].copy()
        if len(train) < 2000 or cible.empty:
            continue
        config, _ = mh.choisir_config(train, h)
        cible["pred"] = mh._modele(config).fit(train[mh.FEATURES], train["y"]).predict(cible[mh.FEATURES])
        cible["rang_ia"] = cible.groupby("date")["pred"].rank(pct=True)
        sorties.append(cible[["date", "symbol", "rang_ia"]])
    return pd.concat(sorties, ignore_index=True) if sorties else pd.DataFrame(columns=["date", "symbol", "rang_ia"])


def _niveaux_har(data: pd.DataFrame, ret: pd.DataFrame, dates_rebal: list, h: int) -> pd.DataFrame:
    """Niveau de volatilité prévu par HAR à chaque date de rééquilibrage, régression réajustée chaque
    1er janvier sur le passé seulement (cible connue : volatilité réalisée `brut`)."""
    import examen_risque as ex
    entrees = ex.har_entrees(ret)
    dates = pd.DatetimeIndex(sorted(set(pd.to_datetime(data["date"].unique())) | set(pd.to_datetime(dates_rebal))))
    tab = None
    for nom, t in entrees.items():
        s = t.reindex(dates).stack(future_stack=True).rename(nom)
        s.index.names = ["date", "symbol"]
        tab = s.to_frame() if tab is None else tab.join(s)
    tab = tab.reset_index()
    base = data[["date", "symbol", "brut"]].merge(tab, on=["date", "symbol"], how="left")
    embargo = pd.Timedelta(days=int(h * 7 / 5) + 1)
    sorties = []
    for annee in sorted({pd.Timestamp(d).year for d in dates_rebal}):
        train = base[base["date"] < pd.Timestamp(f"{annee}-01-01") - embargo].dropna()
        cible = tab[tab["date"].isin([d for d in dates_rebal if pd.Timestamp(d).year == annee])].copy()
        if len(train) < 2000 or cible.empty:
            continue
        cible["lvl_har"] = ex.har_prevoir(cible, ex.har_ajuster(train))
        sorties.append(cible[["date", "symbol", "lvl_har"]])
    return pd.concat(sorties, ignore_index=True) if sorties else pd.DataFrame(columns=["date", "symbol", "lvl_har"])


def _vol_ia(rangs: pd.Series, vol_3m_membres: pd.Series) -> pd.Series:
    """Rang prédit -> niveau : quantile correspondant de la distribution actuelle des volatilités
    3 mois de tous les membres (garde le niveau de marché du moment, l'IA ne change que l'ordre)."""
    v = np.sort(vol_3m_membres.dropna().values)
    return pd.Series(np.quantile(v, rangs.clip(0, 1).values), index=rangs.index)


def backtest(market_raw: pd.DataFrame, symboles: list[str], composition: pd.DataFrame | None,
             debut: str = "2013-01-01", pas_semaines: int = 4, base: str | list[str] = "momentum40",
             variantes: list[str] | None = None, secteurs: dict | None = None,
             portefeuilles: dict | None = None, garder_poids: bool = False,
             garder_frontieres: bool = False) -> pd.DataFrame:
    variantes = variantes or VARIANTES
    portefeuilles = portefeuilles or PORTEFEUILLES
    bases = [base] if isinstance(base, str) else list(base)   # plusieurs bases : IA entraînée une seule fois
    h = mh.HORIZONS[HORIZON_IA]
    px_tout, X = mh.caracteristiques(market_raw, symboles)
    Y = mr.cible_risque(px_tout, pd.DatetimeIndex(X["date"].unique()), h, "volatilite")
    data = X.merge(Y, on=["date", "symbol"]).dropna(subset=mh.FEATURES + ["y"])
    if composition is not None:
        data = mh.membres_a_date(data, composition)
    # Dates de rééquilibrage : toutes les 4 semaines (les caractéristiques existent à ces dates)
    toutes = sorted(d for d in X["date"].unique() if d >= pd.Timestamp(debut))
    dates_rebal = toutes[::pas_semaines]
    besoin_ia = bool({"ia", "hybride"} & set(variantes))
    preds = _predictions_ia(data, dates_rebal, h) if besoin_ia else pd.DataFrame(columns=["date", "symbol", "rang_ia"])
    har = (_niveaux_har(data, px_tout.pct_change(), dates_rebal, h) if {"hybride", "har"} & set(variantes)
           else pd.DataFrame(columns=["date", "symbol", "lvl_har"]))
    frontieres = {}

    ret = px_tout.pct_change()
    marche = market_raw[market_raw["symbol"] == mh.INDICE].set_index("date")["close"].sort_index().pct_change()
    lignes = []
    for d in dates_rebal:
        membres = data.loc[data["date"] == d, "symbol"].tolist() if composition is not None else list(px_tout.columns)
        i = px_tout.index.get_loc(d)
        if i < pf.JOURS_ESTIMATION or i + TENUE >= len(px_tout) or len(membres) < 50:
            continue
        passe = ret.iloc[i - pf.JOURS_ESTIMATION + 1:i + 1][membres]
        passe = passe.dropna(axis=1, thresh=int(len(passe) * 0.95)).fillna(0.0)
        vol_3m = ret.iloc[i - 62:i + 1][membres].std() * np.sqrt(pf.JOURS)
        p = preds[preds["date"] == d].set_index("symbol")["rang_ia"]
        if besoin_ia and p.empty:
            continue
        lh = har[har["date"] == d].set_index("symbol")["lvl_har"]
        for base in bases:
            if base == "momentum40":
                # Ancienne présélection : momentum 12-1 / volatilité 1 an
                cand = pf.score_momentum(px_tout.iloc[i - pf.JOURS:i + 1][passe.columns]).index[:pf.N_CANDIDATS].tolist()
            else:
                cand = list(passe.columns)
            if len(cand) < 10:
                continue
            R = passe[cand]
            mu, cov_hist = pf.estimations(R, marche.reindex(R.index))
            sd_hist = np.sqrt(np.diag(cov_hist))
            corr = cov_hist / np.outer(sd_hist, sd_hist)
            vols = {
                "hist_3a": lambda: sd_hist,
                "naif_3m": lambda: vol_3m.reindex(cand).fillna(pd.Series(sd_hist, index=cand)).values,
                "ia": lambda: _vol_ia(p.reindex(cand).fillna(0.5), vol_3m).values,
                # Hybride : ordre de l'IA, niveaux de HAR (docs/METHODE.md § 4.9)
                "hybride": lambda: _vol_ia(p.reindex(cand).fillna(0.5), lh.reindex(membres).dropna()
                                            if lh.notna().sum() > 20 else vol_3m).values,
                # HAR seul : niveau ET ordre donnés par HAR (repli : volatilité historique si HAR manque)
                "har": lambda: lh.reindex(cand).fillna(pd.Series(sd_hist, index=cand)).values,
            }
            futur = ret.iloc[i + 1:i + TENUE + 1][cand].fillna(0.0)
            for variante in variantes:
                sd = vols[variante]()
                B, D = pf.facteurs(corr * np.outer(sd, sd))
                pts = pf.frontiere_lambdas(B, D, mu)
                if not pts:
                    continue
                if garder_frontieres:
                    frontieres[(pd.Timestamp(d), base, variante)] = (
                        list(cand), [{"volatilite": q["volatilite"], "rendement": q["rendement"], "sharpe": q["sharpe"],
                                      "poids": {cand[k]: float(w) for k, w in zip(q["idx"], q["w"] / q["w"].sum())}}
                                     for q in pts])
                for nom_pf, cible in portefeuilles.items():
                    pt = _choisir(pts, cible)
                    wv = np.zeros(len(cand))
                    wv[pt["idx"]] = pt["w"] / pt["w"].sum()
                    r = futur.values @ wv
                    poids_sect = (pd.Series(wv, index=cand).groupby(lambda s: (secteurs or {}).get(s, "?")).sum()
                                  if secteurs else pd.Series(dtype=float))
                    lignes.append({"date": d, "variante": variante, "portefeuille": nom_pf, "base": base,
                                   "vol_reelle": float(r.std() * np.sqrt(pf.JOURS)),
                                   "vol_prevue": float(np.sqrt(pf.variance(B, D, wv))),
                                   "rendement": float(np.prod(1 + r) - 1), "n_lignes": int((wv > 1e-6).sum()),
                                   "poids_secteur_max": float(poids_sect.max()) if len(poids_sect) else None,
                                   "rendement_attendu": float(wv @ mu),
                                   **({"poids": {cand[k]: float(wv[k]) for k in np.flatnonzero(wv > 1e-6)}}
                                      if garder_poids else {})})
        # Référence : l'indice lui-même (SPY) sur le même mois
        rm = marche.iloc[marche.index.get_indexer([px_tout.index[i]])[0] + 1:][:TENUE].fillna(0.0).values
        if len(rm):
            lignes.append({"date": d, "variante": "indice", "portefeuille": "indice", "base": "sp500",
                           "vol_reelle": float(rm.std() * np.sqrt(pf.JOURS)), "vol_prevue": None,
                           "rendement": float(np.prod(1 + rm) - 1), "n_lignes": 1, "poids_secteur_max": None})
    out = pd.DataFrame(lignes)
    if garder_frontieres:
        out.attrs["frontieres"] = frontieres
    return out


def _choisir(pts: list[dict], cible) -> dict:
    """None : meilleur Sharpe ; nan : variance minimale ; nombre : le plus rentable sous ce risque
    (comme choisirPointRisque dans l'appli), sinon le moins risqué."""
    if cible is None:
        return max(pts, key=lambda q: q["sharpe"])
    if not np.isfinite(cible):
        return min(pts, key=lambda q: q["volatilite"])
    sous = [q for q in pts if q["volatilite"] <= cible]
    return max(sous, key=lambda q: q["rendement"]) if sous else min(pts, key=lambda q: q["volatilite"])


# ------------------------------------------------------------------------------
# Backtest « réel » : frais, rééquilibrage par seuil, promesse de risque, fourchette
# ------------------------------------------------------------------------------
FRAIS_ORDRE = 1.0       # € par ordre (préréglage Trade Republic)
ECART_PRIX = 0.001      # 0,1 % payé sur chaque montant échangé (écart achat / vente)
CAPITAL = 5000.0        # € investis
DERIVE_MAX = 0.05       # on rééquilibre si une ligne s'écarte de plus de 5 pts de sa cible


def frais_et_ordres(poids_avant: dict, poids_cible: dict, capital: float, frais_ordre: float = FRAIS_ORDRE,
                    ecart: float = ECART_PRIX) -> tuple[float, int, float]:
    """(coût en €, nombre d'ordres, rotation) pour passer de poids_avant à poids_cible."""
    titres = set(poids_avant) | set(poids_cible)
    echanges = {s: abs(poids_cible.get(s, 0.0) - poids_avant.get(s, 0.0)) for s in titres}
    ordres = sum(1 for v in echanges.values() if v * capital >= 1.0)
    rotation = sum(echanges.values())
    return ordres * frais_ordre + rotation * capital * ecart, ordres, rotation


SEUIL_LIGNE = 0.25      # entre deux révisions : on ne rééquilibre que si une ligne dépasse 25 % (seuil de l'appli)


def dates_revision(dates, revision_mois: int) -> list:
    """Premières dates de chaque période de révision (1 : chaque mois ; 6 : janvier et juillet ; 12 : janvier)."""
    out, vues = [], set()
    for d in sorted(pd.to_datetime(list(dates))):
        cle = (d.year, (d.month - 1) // revision_mois)
        if cle not in vues:
            vues.add(cle)
            out.append(d)
    return out


def backtest_reel(res: pd.DataFrame, px: pd.DataFrame, nom_pf: str, variante: str = "ia", base: str = "sp500",
                  capital: float = CAPITAL, derive_max: float = DERIVE_MAX, revision_mois: int = 1,
                  seuil_ligne: float = SEUIL_LIGNE) -> dict:
    """Rejoue jour par jour un portefeuille du backtest (lignes avec `poids`), frais déduits.
    revision_mois = 1 : on suit chaque nouvelle recommandation (si la composition change ou si une ligne dérive
    de plus de `derive_max`). revision_mois = 6 ou 12 : la cible n'est révisée qu'à ces dates ; entre deux,
    on ne rééquilibre que si une ligne dépasse `seuil_ligne` du portefeuille (comme l'appli)."""
    g = res[(res["portefeuille"] == nom_pf) & (res["variante"] == variante) & (res["base"] == base)]
    g = g.dropna(subset=["poids"]).sort_values("date") if "poids" in g else g.iloc[0:0]
    if g.empty:
        return {}
    ret = px.pct_change().fillna(0.0)
    cibles = {pd.Timestamp(d): p for d, p in zip(g["date"], g["poids"])}
    if revision_mois > 1:
        garder = set(dates_revision(cibles, revision_mois))
        controles = sorted(cibles)                       # dates de contrôle du seuil par ligne
        revisees = {}
        courante = None
        for d in controles:
            if d in garder:
                courante = cibles[d]
            revisees[d] = courante
        cibles = {d: c for d, c in revisees.items() if c is not None}
    jours = ret.index[(ret.index > g["date"].min()) & (ret.index <= g["date"].max() + pd.Timedelta(days=31))]
    valeur, w, cible = capital, {}, {}
    serie, cout_total, n_ordres, n_reeq = [], 0.0, 0, 0
    dates_cibles = sorted(cibles)
    j = 0
    for jour in jours:
        while j < len(dates_cibles) and dates_cibles[j] < jour:
            nouvelle = cibles[dates_cibles[j]]
            change = nouvelle is not cible
            cible = nouvelle
            j += 1
            derive = max([abs(w.get(s, 0) - cible.get(s, 0)) for s in set(w) | set(cible)] or [1])
            if revision_mois > 1:
                agir = change or (max(w.values()) if w else 1) > seuil_ligne
            else:
                agir = set(k for k, v in w.items() if v > 1e-4) != set(cible) or derive > derive_max
            if agir:
                cout, ordres, _ = frais_et_ordres(w, cible, valeur)
                valeur -= cout
                cout_total += cout
                n_ordres += ordres
                n_reeq += 1
                w = dict(cible)
        r = sum(wi * ret.at[jour, s] for s, wi in w.items() if s in ret.columns)
        valeur *= 1 + r
        if w:
            tot = sum(wi * (1 + ret.at[jour, s]) for s, wi in w.items() if s in ret.columns) or 1
            w = {s: wi * (1 + ret.at[jour, s]) / tot for s, wi in w.items() if s in ret.columns}
        serie.append((jour, r))
    r = pd.Series(dict(serie))
    annees = len(r) / 252
    courbe = (1 + r).cumprod()
    # Rendement brut (sans frais) des mêmes positions, pour mesurer ce que coûtent les frais
    brut = float(courbe.iloc[-1] ** (1 / annees) - 1) if annees > 0 else None
    net = float((valeur / capital) ** (1 / annees) - 1) if annees > 0 else None
    out = {"rendement_brut": brut, "rendement_net": net, "volatilite": float(r.std() * np.sqrt(252)),
           "ordres_par_an": n_ordres / annees if annees else None, "reequilibrages_par_an": n_reeq / annees if annees else None,
           "frais_par_an": cout_total / annees if annees else None, "annees": annees}
    # Promesse de risque : volatilité réelle par semestre, comparée à la limite
    limite = PORTEFEUILLES_RISQUE.get(nom_pf)
    if limite:
        sem = r.groupby([r.index.year, (r.index.month - 1) // 6]).std() * np.sqrt(252)
        out["limite"] = limite
        out["part_semestres_au_dessus"] = float((sem > limite).mean())
        out["rapport_reel_limite_median"] = float((sem / limite).median())
        out["n_semestres"] = int(len(sem))
    return out


LIMITES_MARGE = [0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25, 0.28, 0.30, 0.35]   # grille affichée par l'appli (METHODE § 7.4)


def marge_walk_forward(res: pd.DataFrame, px: pd.DataFrame, limite: float, variante: str = "hybride",
                       base: str = "sp500", revision_mois: int = 6, q: float = 0.70, min_hist: int = 4) -> dict:
    """Marge de sécurité apprise sur le passé (docs/METHODE.md § 4.9, règle 3) : à chaque révision, on vise
    limite x m avec m = 1 / quantile q du rapport (risque réel / risque prévu) des semestres PASSÉS.
    Retourne la part des semestres où la limite a été respectée, avec et sans marge, et la marge actuelle."""
    fr = res.attrs.get("frontieres", {})
    dates = sorted(d for (d, b, v) in fr if b == base and v == variante)
    revs = dates_revision(dates, revision_mois)
    ret = px.pct_change()
    rapports, avec, sans, ms = [], [], [], []
    for k, d in enumerate(revs):
        fin = revs[k + 1] if k + 1 < len(revs) else None
        cand, pts = fr[(d, base, variante)]
        m = 1.0 / float(np.quantile(rapports, q)) if len(rapports) >= min_hist else 1.0
        m = float(np.clip(m, 0.5, 1.5))
        periode = ret[(ret.index > d) & ((ret.index <= fin) if fin is not None else True)]
        if len(periode) < 60:
            continue

        def reel(pt):
            w = pd.Series(pt["poids"])
            cols = w.index.intersection(periode.columns)
            r = periode[cols].fillna(0.0) @ w[cols]
            return float(r.std() * np.sqrt(252))
        pt_m = _choisir(pts, limite * m)
        pt_0 = _choisir(pts, limite)
        v_m, v_0 = reel(pt_m), reel(pt_0)
        if len(rapports) >= min_hist:                     # mesure seulement quand la marge est apprise
            avec.append(v_m <= limite)
            sans.append(v_0 <= limite)
            ms.append(m)
        rapports.append(v_0 / pt_0["volatilite"] if pt_0["volatilite"] > 0 else 1.0)
    m_actuelle = float(np.clip(1.0 / np.quantile(rapports, q), 0.5, 1.5)) if len(rapports) >= min_hist else 1.0
    return {"limite": limite, "part_respectee_avec_marge": float(np.mean(avec)) if avec else None,
            "part_respectee_sans_marge": float(np.mean(sans)) if sans else None, "n_semestres": len(avec),
            "marge_actuelle": m_actuelle, "marge_moyenne": float(np.mean(ms)) if ms else None,
            "rapport_reel_prevu_median": float(np.median(rapports)) if rapports else None}


def couverture_fourchette(res: pd.DataFrame, px: pd.DataFrame, nom_pf: str = "sharpe_max", variante: str = "ia",
                          base: str = "sp500", z: float = 1.6449) -> dict:
    """La fourchette à 1 an de l'appli (log-normale, 5 % / 95 %) contient-elle bien 90 % des résultats ?
    Pour chaque date : portefeuille gardé 1 an, comparé aux bornes calculées avec le risque prévu et la
    rentabilité de long terme (hypothèse CAPM)."""
    g = res[(res["portefeuille"] == nom_pf) & (res["variante"] == variante) & (res["base"] == base)]
    g = g.dropna(subset=["poids"]) if "poids" in g else g.iloc[0:0]
    bas = haut = n = 0
    for _, l in g.iterrows():
        d = pd.Timestamp(l["date"])
        i = px.index.searchsorted(d, side="right")
        if i + 252 > len(px):
            continue
        fen = px.iloc[i - 1:i + 252]
        syms = [s for s in l["poids"] if s in fen.columns]
        if not syms:
            continue
        w = np.array([l["poids"][s] for s in syms])
        r1 = float(((fen[syms].iloc[-1] / fen[syms].iloc[0]).fillna(1).values @ w) / w.sum() - 1)
        sig, mu = l["vol_prevue"], l.get("rendement_attendu", 0.08)
        m = np.log1p(mu) - sig ** 2 / 2
        q05, q95 = np.expm1(m - z * sig), np.expm1(m + z * sig)
        bas += r1 < q05
        haut += r1 > q95
        n += 1
    return {"n": n, "part_sous_mauvais_cas": bas / n if n else None, "part_au_dessus_bon_cas": haut / n if n else None,
            "attendu": 0.05}


def comparer_bases(res: pd.DataFrame, nom_pf: str = "sharpe_max", variante: str = "hist_3a") -> dict:
    """Base large (sp500) contre ancienne base (momentum40), mêmes mois : rendement, risque,
    rendement / risque, perte maximale, poids du premier secteur, et l'indice en repère.
    t : écart mensuel de rendement ajusté du risque (rendement / volatilité réelle), apparié."""
    def serie(base, pf_, var):
        g = res[(res["base"] == base) & (res["portefeuille"] == pf_) & (res["variante"] == var)]
        return g.drop_duplicates("date").set_index("date")

    def bilan(g):
        r = g["rendement"]
        courbe = (1 + r).cumprod()
        an = float(courbe.iloc[-1] ** (12 / len(r)) - 1)
        vol = float(r.std() * np.sqrt(12))
        return {"rendement_annuel": an, "volatilite": vol, "rendement_risque": an / vol if vol > 0 else None,
                "perte_max": float((courbe / courbe.cummax() - 1).min()),
                "poids_secteur_max": float(g["poids_secteur_max"].mean()) if g["poids_secteur_max"].notna().any() else None,
                "n_mois": int(len(r))}
    large, ancien = serie("sp500", nom_pf, variante), serie("momentum40", nom_pf, variante)
    communs = large.index.intersection(ancien.index)
    out = {"sp500": bilan(large.loc[communs]), "momentum40": bilan(ancien.loc[communs])}
    idx = serie("sp500", "indice", "indice")
    if not idx.empty:
        out["indice"] = bilan(idx.loc[idx.index.intersection(communs)])
    # Écart mensuel de rendement (large − ancien), apparié sur les mêmes mois
    d = (large.loc[communs, "rendement"] - ancien.loc[communs, "rendement"]).dropna()
    out["ecart"] = {"rendement_mensuel": float(d.mean()),
                    "t": float(d.mean() / d.std() * np.sqrt(len(d))) if d.std() > 0 else 0.0,
                    "part_mois_meilleurs": float((d > 0).mean())}
    return out


def resume(res: pd.DataFrame) -> dict:
    """Moyennes par variante et comparaisons appariées (mêmes mois) de l'IA contre les deux autres."""
    out = {}
    for nom_pf, g in res[res["portefeuille"] != "indice"].drop(columns=["poids"], errors="ignore").groupby("portefeuille"):
        tab = g.pivot_table(index="date", columns="variante", values="vol_reelle")
        prev = g.pivot_table(index="date", columns="variante", values="vol_prevue")
        rend = g.pivot_table(index="date", columns="variante", values="rendement")
        bloc = {"n_mois": int(len(tab)), "variantes": {}}
        for v in VARIANTES:
            if v not in tab:
                continue
            erreur = (prev[v] - tab[v]).abs() / tab[v]
            bloc["variantes"][v] = {
                "vol_reelle": float(tab[v].mean()), "vol_prevue": float(prev[v].mean()),
                "erreur_prevision": float(erreur.mean()),
                "rendement_annuel": float((1 + rend[v]).prod() ** (12 / max(1, len(rend))) - 1),
            }
        for ref in ["hist_3a", "naif_3m"]:
            if ref in tab and "ia" in tab:
                d = (tab["ia"] - tab[ref]).dropna()
                bloc[f"ia_vs_{ref}"] = {
                    "ecart_vol": float(d.mean()),
                    "t": float(d.mean() / d.std() * np.sqrt(len(d))) if d.std() > 0 else 0.0,
                    "part_mois_moins_risque": float((d < 0).mean()),
                }
        out[nom_pf] = bloc
    return out
