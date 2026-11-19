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

VARIANTES = ["hist_3a", "naif_3m", "ia"]
PORTEFEUILLES = {"variance_min": np.nan, "sharpe_max": None}   # cible passée à pf.optimiser
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


def _vol_ia(rangs: pd.Series, vol_3m_membres: pd.Series) -> pd.Series:
    """Rang prédit -> niveau : quantile correspondant de la distribution actuelle des volatilités
    3 mois de tous les membres (garde le niveau de marché du moment, l'IA ne change que l'ordre)."""
    v = np.sort(vol_3m_membres.dropna().values)
    return pd.Series(np.quantile(v, rangs.clip(0, 1).values), index=rangs.index)


def backtest(market_raw: pd.DataFrame, symboles: list[str], composition: pd.DataFrame | None,
             debut: str = "2013-01-01", pas_semaines: int = 4, base: str | list[str] = "momentum40",
             variantes: list[str] | None = None, secteurs: dict | None = None) -> pd.DataFrame:
    variantes = variantes or VARIANTES
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
    preds = _predictions_ia(data, dates_rebal, h) if "ia" in variantes else pd.DataFrame(columns=["date", "symbol", "rang_ia"])

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
        if "ia" in variantes and p.empty:
            continue
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
            }
            futur = ret.iloc[i + 1:i + TENUE + 1][cand].fillna(0.0)
            for variante in variantes:
                sd = vols[variante]()
                B, D = pf.facteurs(corr * np.outer(sd, sd))
                pts = pf.frontiere_lambdas(B, D, mu)
                if not pts:
                    continue
                for nom_pf, cible in PORTEFEUILLES.items():
                    pt = max(pts, key=lambda q: q["sharpe"]) if cible is None else min(pts, key=lambda q: q["volatilite"])
                    wv = np.zeros(len(cand))
                    wv[pt["idx"]] = pt["w"] / pt["w"].sum()
                    r = futur.values @ wv
                    poids_sect = (pd.Series(wv, index=cand).groupby(lambda s: (secteurs or {}).get(s, "?")).sum()
                                  if secteurs else pd.Series(dtype=float))
                    lignes.append({"date": d, "variante": variante, "portefeuille": nom_pf, "base": base,
                                   "vol_reelle": float(r.std() * np.sqrt(pf.JOURS)),
                                   "vol_prevue": float(np.sqrt(pf.variance(B, D, wv))),
                                   "rendement": float(np.prod(1 + r) - 1), "n_lignes": int((wv > 1e-6).sum()),
                                   "poids_secteur_max": float(poids_sect.max()) if len(poids_sect) else None})
        # Référence : l'indice lui-même (SPY) sur le même mois
        rm = marche.iloc[marche.index.get_indexer([px_tout.index[i]])[0] + 1:][:TENUE].fillna(0.0).values
        if len(rm):
            lignes.append({"date": d, "variante": "indice", "portefeuille": "indice", "base": "sp500",
                           "vol_reelle": float(rm.std() * np.sqrt(pf.JOURS)), "vol_prevue": None,
                           "rendement": float(np.prod(1 + rm) - 1), "n_lignes": 1, "poids_secteur_max": None})
    return pd.DataFrame(lignes)


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
    for nom_pf, g in res[res["portefeuille"] != "indice"].groupby("portefeuille"):
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
