# experiences.py
# ==============================================================================
# LABORATOIRE — essais de variantes du modèle « horizon », sans toucher aux
# scores publiés. Lancé à la demande par .github/workflows/experiences.yml.
#
# Garde-fou : plus on essaie de variantes, plus le hasard finit par en faire
# gagner une. Chaque essai (variante × horizon) est enregistré dans la table
# `experiences`, et une variante n'est jugée « probante » que si son t dépasse
# un seuil corrigé du NOMBRE TOTAL d'essais faits depuis le début (Bonferroni).
# ==============================================================================
import os
import sys
import time
from dataclasses import dataclass

import pandas as pd
import yfinance as yf

import data_pipeline as dp
import db
import fondamentaux_sec as fsec
import modele_horizon as mh
import modele_risque as mr
import backtest_risque as bt
import modele_regime as mreg
import modele_cnn as mcnn
import examen_risque as ex
import audit_modeles as am
import universe
from publish import _clean

# nom -> (mode de cible, facteurs retirés, description[, fondamentaux SEC])
EXPERIENCES = {
    "reference": ("relatif", [], "Modèle publié : rendement futur comparé à la médiane"),
    "alpha": ("alpha", [], "Cible ajustée du bêta (alpha de Jensen)"),
    "alpha_secteur": ("alpha_secteur", [], "Alpha de Jensen comparé au secteur"),
    # Lot 2 : le signal d'alpha_secteur vient-il seulement d'un pari sur les petites valeurs ?
    "alpha_secteur_sans_taille": ("alpha_secteur", ["liquidite"],
                                  "Alpha sectoriel, sans le facteur taille (montants échangés)"),
    # Lot 3 : fondamentaux SEC publiés à chaque date (valeur, rentabilité, investissement, émissions)
    "fondamentaux": ("alpha_secteur", [], "Alpha sectoriel, cours + fondamentaux SEC", True),
    "fondamentaux_seuls": ("alpha_secteur", list(mh.FEATURES),
                           "Alpha sectoriel, fondamentaux SEC uniquement (aucun facteur de cours)", True),
    # Algorithme 3 : ensemble XGBoost prudent + linéaire, cours + comptes, alpha sectoriel
    "ensemble": ("alpha_secteur", [], "Ensemble XGBoost + linéaire, cours + comptes, alpha sectoriel", True, "ensemble"),
}
# Famille distincte : prédire le RISQUE (et non le rendement), jugé sur son gain par
# rapport à la référence naïve (volatilité des 3 derniers mois). C'est une autre question
# de recherche : son seuil est corrigé du nombre d'essais de CETTE famille.
EXPERIENCES_RISQUE = {
    "risque_volatilite": ("volatilite", "IA de risque : volatilité future, comparée à la volatilité passée"),
    "risque_perte_max": ("perte_max", "IA de risque : perte maximale future, comparée à la volatilité passée"),
    # Algorithme 1 : le risque de chute vient souvent des bilans fragiles -> comptes SEC publiés à chaque date
    "risque_perte_max_comptes": ("perte_max", "IA de risque : perte maximale future, avec les comptes des entreprises (SEC)", True),
    "risque_volatilite_comptes": ("volatilite", "IA de risque : volatilité future, avec les comptes des entreprises (SEC)", True),
}
# Famille « portefeuille » : backtest mensuel du portefeuille construit avec la volatilité IA
EXPERIENCES_PORTEFEUILLE = {
    "backtest_volatilite": "Portefeuille rééquilibré chaque mois avec la volatilité IA, comparé à l'historique 3 ans et aux 3 derniers mois",
    # PR #25 : Markowitz sur tout le S&P 500 au lieu des 40 meilleurs au momentum (pari non prouvé)
    "backtest_base_large": "Markowitz sur tout le S&P 500, comparé à l'ancienne base (40 meilleurs au momentum) et à l'indice",
}
# Famille « régime de marché » : probabilité d'une baisse du S&P 500 de plus de 10 % en 6 mois
EXPERIENCES_REGIME = {
    "regime_logistique": ("logistique", "Régime de marché : régression logistique (coefficients lisibles)"),
    "regime_xgboost": ("xgboost", "Régime de marché : XGBoost prudent"),
}
# Algorithme 4 : CNN 1D sur les courbes (famille « rendement », même seuil corrigé)
EXPERIENCES_CNN = {"cnn": "CNN sur les courbes de cours (forme de la dernière année), alpha sectoriel"}
HORIZONS_TEST = ["6m", "1a"]
# Essai de confirmation (METHODE § 4.31) : famille « rendement », un seul passage, jamais dans la liste par défaut
EXPERIENCES_CONFIRMATION = {
    "confirmation_ensemble_midcap": "Ensemble XGBoost + linéaire appliqué tel quel au S&P MidCap 400 (titres jamais membres du S&P 500), 6 mois",
}
HORIZON_CONFIRMATION = "6m"
# Audit des quatre autres modèles (docs/METHODE.md § 4.27) : constats, aucun nouvel essai compté
EXPERIENCES_AUDIT = {
    "audit_rendement": "Modèle de rendement publié (1 mois, 6 mois, 1 an) : anciens membres, placebo, biais par groupe (§ 4.27)",
    "audit_ensemble": "Ensemble XGBoost + linéaire (6 mois, 1 an) : anciens membres, placebo, biais par groupe (§ 4.27)",
    "audit_cnn": "CNN sur les courbes (6 mois) : anciens membres, placebo, biais par groupe (§ 4.27)",
    "audit_regime": "Régime de marché (logistique, XGBoost) : placebo à 12 mois, calibration, AUC sans 2008 (§ 4.27)",
}
# Examen approfondi de l'IA de volatilité (docs/METHODE.md § 4.8), historique depuis 1998 pour inclure 2008.
# Les règles de décision ont été fixées AVANT de lancer ces essais.
EXPERIENCES_EXAMEN = {
    "examen_references": "IA de volatilité contre EWMA, GARCH(1,1) et HAR, perte QLIKE et test de Diebold-Mariano",
    "examen_calibration": "Niveau de volatilité prévu contre niveau réel (biais), IA et références",
    "examen_crises": "Gain de l'IA par crise (2008, 2011, 2015, 2018, 2020, 2022), VIX, secteur, taille",
    "examen_placebo": "Cible mélangée, facteur aléatoire, fuite volontaire (le test sait-il voir une fuite ?)",
    "examen_sensibilite": "Gain de l'IA avec chacun des 4 réglages du modèle",
    "examen_midcap": "IA entraînée sur le S&P 500, appliquée telle quelle au S&P MidCap 400",
    "examen_backtest_reel": "Portefeuille avec frais réels, promesse « Je limite le risque », fourchette à 1 an, PBO",
    # PR #27 (docs/METHODE.md § 4.9) : décisions de l'utilisateur après l'examen
    "examen_hybride": "Hybride : ordre des titres par l'IA, niveau par HAR ; publié s'il vaut HAR en niveau et bat la volatilité 3 mois en ordre",
    "examen_ia_contre_har": "L'IA bat-elle HAR sur l'ordre des titres ? Sinon : HAR seul. Backtest hybride contre HAR seul (frais, révision 6 mois)",
    # Essai du 20/11/2026 (docs/METHODE.md § 4.10) : protocole écrit avant l'essai
    "examen_xgb_niveau": "XGBoost sur le NIVEAU de volatilité (cible ln σ − ln σ HAR) contre HAR, QLIKE, placebo, crises",
    # Essai du 20/11/2026 (docs/METHODE.md § 4.11) : protocole écrit avant l'essai
    "examen_echelle_har": "HAR remis à l'échelle (un facteur k appris sur le passé) contre HAR, QLIKE, crises, stabilité",
    # Essai du 20/11/2026 (docs/METHODE.md § 4.13) : protocole écrit avant l'essai
    "examen_multi_horizon": "IA de niveau contre HAR aux horizons 5, 22, 63 et 126 jours (aSPA simplifié, Holm, placebo, équivalence)",
    # Essai du 21/11/2026 (docs/METHODE.md § 4.14) : protocole écrit avant tout code
    "examen_harx": "HAR-X (HAR + VIX × bêta²) contre HAR à 126, 22 et 5 jours ; placebo VIX décalé d'un an ; réplication midcaps",
    # Essai du 22/11/2026 (docs/METHODE.md § 4.15) : protocole écrit avant tout code
    "examen_har_etendu": "HAR étendu : M1 (retards longs, baisses, bêta, secteurs) et M2 (+ VIX, crédit, pente) contre HAR à 126 jours, placebo",
    # Essai du 22/11/2026 (docs/METHODE.md § 4.16) : protocole écrit avant tout code ; re-test mensuel
    "examen_harx_1m": "Confirmation de HAR-X à 1 mois sur le S&P MidCap 400 (titres jamais utilisés), placebo, couverture du mauvais cas",
    # Essai du 22/11/2026 (docs/METHODE.md § 4.17) : données nettoyées, protocole écrit avant tout code ; re-test mensuel
    "examen_harx_1m_v2": "Confirmation de HAR-X à 1 mois sur les midcaps, données nettoyées (cours < 5 $, sauts > 50 %), winsorisation si non informatif",
    # Essai du 23/11/2026 (docs/METHODE.md § 4.19) : protocole écrit avant tout code
    "examen_asymetrie": "Part baissière du risque : persiste-t-elle (22 et 126 j) et prévoit-elle le sens du rendement ? Holm, placebo",
    "examen_marge": "Marge de sécurité apprise sur le passé ; rythmes de révision mensuel, semestriel, annuel avec frais ; fourchette avec l'hybride",
    "examen_audit_biais": "Audit des biais (§ 4.21) : calibration et classement par secteur, taille, bêta, volatilité, année ; alertes fixées à l'avance ; biais du survivant",
    "examen_marge_verif": "Vérification de la marge (§ 4.30) : actuelle, sur les seuls survivants, sans les pics aberrants",
    "examen_har_relatif": "HAR relatif au titre (variance rapportée au risque habituel du titre) contre HAR : QLIKE, crises, stabilité, biais, placebo (§ 4.23)",
    "examen_ia_informee": "IA plus informée (+ volatilités 1 jour, 1 semaine, 1 mois, part baissière) contre l'IA actuelle sur l'ordre des titres, placebo (§ 4.24)",
    "examen_har_protege": "HAR relatif protégé en crise (le plus élevé du relatif et de HAR quand v22 > 2 × risque habituel) contre HAR (§ 4.25)",
    "examen_ia_climat": "IA + climat de marché (log VIX, VIX / sa moyenne 1 an) contre l'IA actuelle sur l'ordre des titres, placebo VIX décalé d'un an (§ 4.26)",
}
DEBUT_EXAMEN = "1998-01-01"


def _vix(debut: str) -> pd.Series:
    """Clôture quotidienne du VIX (`^VIX`, Yahoo)."""
    v = yf.download("^VIX", start=debut, progress=False, auto_adjust=False)["Close"]
    v = v.iloc[:, 0] if isinstance(v, pd.DataFrame) else v
    v.index = pd.to_datetime(v.index).tz_localize(None)
    return v.dropna()


def charger_cours(symboles: list[str], debut: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cours (ajustés des divisions, comme toujours chez Yahoo) + historique des divisions d'actions."""
    frames, divisions = [], []
    for i in range(0, len(symboles), 100):
        lot = symboles[i:i + 100]
        try:
            d = yf.download(lot, start=debut or dp.HISTORIQUE_LONG_DEBUT, progress=False, auto_adjust=False,
                            actions=True, threads=True)
            if d is None or d.empty:
                continue
            if isinstance(d.columns, pd.MultiIndex):
                d = d.stack(level=1, future_stack=True).rename_axis(["date", "symbol"]).reset_index()
            else:
                d = d.reset_index().assign(symbol=lot[0])
            d.columns = [str(c).lower() for c in d.columns]
            d = d.rename(columns={"index": "date"})
            if "stock splits" in d:
                sp = d[d["stock splits"].fillna(0) > 0][["symbol", "date", "stock splits"]]
                divisions.append(sp.rename(columns={"stock splits": "ratio"}))
            d["adj_close"] = d["adj close"] if "adj close" in d else d["close"]   # dividendes compris (§ 4.28)
            frames.append(d.dropna(subset=["close"])[["symbol", "date", "open", "high", "low", "close", "adj_close", "volume"]])
        except Exception as e:
            print(f"[LABO][WARN] Yahoo, lot {lot[:3]}... : {e}")
    raw = pd.concat(frames, ignore_index=True)
    raw["date"] = pd.to_datetime(raw["date"]).dt.tz_localize(None)
    splits = pd.concat(divisions, ignore_index=True) if divisions else pd.DataFrame(columns=["symbol", "date", "ratio"])
    splits["date"] = pd.to_datetime(splits["date"]).dt.tz_localize(None)
    print(f"[LABO] {raw['symbol'].nunique()} titres, {len(splits)} divisions d'actions")
    return raw, splits


def verdict_labo(ic, t, n_eff, seuil) -> str:
    if ic is not None and ic > 0.03 and (n_eff or 0) >= mh.MIN_PERIODES_SIGNAL and (t or 0) > seuil:
        return "probant"
    return "non probant"


BIBLIOTHEQUES = ["numpy", "pandas", "scipy", "scikit-learn", "xgboost", "shap", "yfinance", "torch"]


def versions_bibliotheques() -> dict:
    """Versions de Python et des bibliothèques de calcul : enregistrées avec chaque essai, pour qu'un
    changement de verdict au re-test mensuel puisse être rapproché d'un changement de bibliothèque."""
    from importlib.metadata import PackageNotFoundError, version
    out = {"python": sys.version.split()[0]}
    for b in BIBLIOTHEQUES:
        try:
            out[b] = version(b)
        except PackageNotFoundError:
            out[b] = None
    return out


def _ecrire(cli, ligne: dict):
    """Enregistre un essai dans `experiences`, avec les versions des bibliothèques dans ses diagnostics."""
    diag = ligne.get("diagnostics")
    diag = dict(diag) if isinstance(diag, dict) else ({"valeur": diag} if diag is not None else {})
    diag["versions"] = versions_bibliotheques()
    return cli.table("experiences").insert(_clean({**ligne, "diagnostics": diag})).execute()


def _inserer(cli, lot: str, nom: str, verdict: str, diag: dict, ic=None, t=None, seuil=None, n_essais=1):
    _ecrire(cli, {
        "lot": lot, "nom": nom, "horizon": "6m", "description": EXPERIENCES_EXAMEN[nom],
        "ic": ic, "t_stat": t, "seuil_t_global": seuil, "n_essais": n_essais, "verdict": verdict, "diagnostics": diag,
    })
    print(f"[LABO] {nom} -> {verdict} : {diag if len(str(diag)) < 1500 else str(diag)[:1500] + '…'}")


@dataclass
class Contexte:
    """Données communes aux examens d'un même lot : chargées une fois, partagées par tous les examens."""
    cli: object
    lot: str
    snap: pd.DataFrame
    secteurs: dict
    raw: pd.DataFrame
    compo: pd.DataFrame | None
    data: pd.DataFrame
    ret: pd.DataFrame
    t: pd.DataFrame | None = None      # walk-forward commun (IA et références), calculé si un examen en a besoin
    symboles: list[str] | None = None  # titres actuels + anciens membres du S&P 500 (METHODE § 4.22)


def _examen_references(ctx: Contexte, nom: str):
    cli, lot, t = ctx.cli, ctx.lot, ctx.t
    c = ex.comparer_references(t)
    b = c["meilleure_reference"]
    v = "l'IA reste" if c["ia_reste"] else f"bascule sur {b.upper()}"
    c["debut_test"] = str(pd.Timestamp(t["date"].min()).date())
    c["garch_ab"] = sorted(t["garch_ab"].unique().tolist())
    _inserer(cli, lot, nom, v, c, ic=c["ic"]["ia"], t=-c["dm"][b]["t"], seuil=c["seuil"], n_essais=3)


def _examen_calibration(ctx: Contexte, nom: str):
    cli, lot, t = ctx.cli, ctx.lot, ctx.t
    c = {k: ex.calibration(t, col) for k, col in
         [("ia", "lvl_ia"), ("vol_3m", "lvl_vol_3m"), ("ewma", "lvl_ewma"), ("garch", "lvl_garch"), ("har", "lvl_har")]
         if t[col].notna().any()}
    b = c["ia"]["biais_median"]
    v = "calibrée" if abs(b) <= 0.10 else ("surestime" if b > 0 else "sous-estime") + f" de {abs(b):.0%}"
    _inserer(cli, lot, nom, v, c, ic=b)


def _examen_crises(ctx: Contexte, nom: str):
    cli, lot, t = ctx.cli, ctx.lot, ctx.t
    vix = None
    try:
        vix = mreg.telecharger(DEBUT_EXAMEN)["vix"]
    except Exception as e:
        print(f"[LABO][WARN] VIX indisponible : {e}")
    c = ex.par_periode(t, vix)
    gagnees = sum(1 for r in c["crises"].values() if r["gain_qlike"] > 0)
    v = f"IA meilleure dans {gagnees}/{len(c['crises'])} crises"
    _inserer(cli, lot, nom, v, c, ic=gagnees / max(1, len(c["crises"])))


def _examen_placebo(ctx: Contexte, nom: str):
    cli, lot, data, ret = ctx.cli, ctx.lot, ctx.data, ctx.ret
    c = ex.placebo(data, ret)        # 10 tirages : règle 4 de la PR #27, |moyenne| < 2 %
    ok = abs(c["ic_cible_melangee"] or 0) < 0.02 and (c["ic_fuite_volontaire"] or 0) > 0.5
    _inserer(cli, lot, nom, "réussi" if ok else "ÉCHEC : chercher une fuite", c, ic=c["ic_cible_melangee"])


def _examen_sensibilite(ctx: Contexte, nom: str):
    cli, lot, data, ret = ctx.cli, ctx.lot, ctx.data, ctx.ret
    c = ex.sensibilite(data, ret)
    ok = all(r["gain"] > 0 for r in c.values())
    _inserer(cli, lot, nom, "réussi (gain positif partout)" if ok else "fragile", c,
             ic=min(r["gain"] for r in c.values()) if c else None)


def _examen_midcap(ctx: Contexte, nom: str):
    cli, lot, data = ctx.cli, ctx.lot, ctx.data
    m = universe.get_sp400_tickers()
    raw_m, _ = charger_cours(sorted(set(m["symbol"]) | {mh.INDICE}), debut=DEBUT_EXAMEN)
    data_m, _ = ex.preparer(raw_m, m["symbol"].tolist(), None)
    c = ex.autre_marche(data, data_m)
    _inserer(cli, lot, nom, "même résultat" if c["gain"] > 0 else "ne se généralise pas", c,
             ic=c["gain"], t=c["t"])


def _examen_hybride(ctx: Contexte, nom: str):
    cli, lot, t = ctx.cli, ctx.lot, ctx.t
    c = ex.comparer_hybride(t)
    c["debut_test"] = str(pd.Timestamp(t["date"].min()).date())
    v = "publié" if c["publie"] else "HAR seul"
    _inserer(cli, lot, nom, v, c, ic=c["ic"]["hybride"], t=c["t_ic"], seuil=c["seuil"], n_essais=4)


def _examen_ia_contre_har(ctx: Contexte, nom: str):
    cli, lot, raw, compo, secteurs, t = ctx.cli, ctx.lot, ctx.raw, ctx.compo, ctx.secteurs, ctx.t
    c = ex.ia_contre_har(t)
    tous = {"sharpe_max": None, "risque_15": 0.15}
    res = bt.backtest(raw, ctx.symboles, compo, debut="2006-01-01", base="sp500",
                      variantes=["hybride", "har"], secteurs=secteurs, portefeuilles=tous, garder_poids=True)
    px = mh.cours_ajustes(raw)   # rentabilités réalisées, dividendes compris (§ 4.28)
    c["backtest"] = {f"{pf_}_{v}": bt.backtest_reel(res, px, pf_, v, revision_mois=6)
                     for pf_ in tous for v in ["hybride", "har"]}
    v = "l'IA reste (hybride)" if c["ia_reste"] else "HAR seul"
    _inserer(cli, lot, nom, v, c, ic=c["gain"], t=c["t"], seuil=c["seuil"], n_essais=5)


def _examen_xgb_niveau(ctx: Contexte, nom: str):
    cli, lot, data = ctx.cli, ctx.lot, ctx.data
    tb = ex.walk_forward_niveau(data, "B")
    ta = ex.walk_forward_niveau(data, "A")
    tp = ex.walk_forward_niveau(data, "B", melange=True)
    c = ex.comparer_niveau(tb, ta, tp)
    c["debut_test"] = str(pd.Timestamp(tb["date"].min()).date())
    v = ("candidate (règles 1, 2 et 3 réunies)" if c["candidate"]
         else "non candidate : " + ", ".join(k for k, ok in c["regles"].items() if not ok))
    _inserer(cli, lot, nom, v, c, ic=c["ic"]["xgb"], t=c["B"]["t"], seuil=c["B"]["seuil"], n_essais=7)


def _examen_echelle_har(ctx: Contexte, nom: str):
    cli, lot, data = ctx.cli, ctx.lot, ctx.data
    te = ex.walk_forward_echelle(data)
    c = ex.comparer_echelle(te)
    c["debut_test"] = str(pd.Timestamp(te["date"].min()).date())
    v = ("candidat (règles 1, 2 et 3 réunies)" if c["candidate"]
         else "non candidat : " + ", ".join(k for k, ok in c["regles"].items() if not ok))
    _inserer(cli, lot, nom, v, c, ic=c["ecart"], t=c["t"], seuil=c["seuil"], n_essais=8)


def _examen_multi_horizon(ctx: Contexte, nom: str):
    cli, lot, data, raw, compo, secteurs = ctx.cli, ctx.lot, ctx.data, ctx.raw, ctx.compo, ctx.secteurs
    par_h, plc = {}, {}
    for hh in ex.HORIZONS_MULTI:
        d_h = data if hh == ex.H else ex.preparer(raw, ctx.symboles, compo, secteurs, h=hh, couverture_min=ex.COUVERTURE_MIN)[0]
        par_h[hh] = ex.walk_forward_niveau(d_h, "B", h=hh)
        plc[hh] = ex.walk_forward_niveau(d_h, "B", h=hh, melange=True)
        print(f"[LABO] multi-horizon : h = {hh} j terminé")
    c = ex.comparer_multi(par_h, plc)
    r = c["regles"]
    v = ("piste" if r["1_piste"] else "fuite probable" if r["2_fuite_probable"] else "B pire que HAR" if r["3_B_pire"]
         else "équivalence démontrée" if (r["4_equivalence"] and c["peut_conclure_equivalence"]) else "sans pouvoir de conclure")
    _inserer(cli, lot, nom, v, c, ic=c["aspa"]["ecart"], t=c["aspa"]["t"], seuil=2.0, n_essais=1)


def _examen_harx(ctx: Contexte, nom: str):
    cli, lot, data, raw, compo, secteurs = ctx.cli, ctx.lot, ctx.data, ctx.raw, ctx.compo, ctx.secteurs
    vix = _vix(DEBUT_EXAMEN)
    beta = ex.beta_depuis_cours(raw, ctx.symboles)
    par_h, plc = {}, {}
    for hh in ex.HORIZONS_HARX:
        d_h = data if hh == ex.H else ex.preparer(raw, ctx.symboles, compo, secteurs, h=hh, couverture_min=ex.COUVERTURE_MIN)[0]
        par_h[hh] = ex.walk_forward_harx(ex.ajouter_x_vix(d_h, beta, vix), h=hh)
        plc[hh] = ex.walk_forward_harx(ex.ajouter_x_vix(d_h, beta, vix, decalage=ex.DECALAGE_PLACEBO_VIX), h=hh)
        print(f"[LABO] HAR-X : h = {hh} j terminé")
    c = ex.comparer_harx(par_h, plc)
    c["debut_test"] = str(pd.Timestamp(par_h[ex.H]["date"].min()).date())
    rep = None
    if c["regles"].get(ex.H, {}).get("2abc"):      # règle 2 (d), calculée seulement si (a) à (c) tiennent
        m = universe.get_sp400_tickers()
        raw_m, _ = charger_cours(sorted(set(m["symbol"]) | {mh.INDICE}), debut=DEBUT_EXAMEN)
        data_m, _ = ex.preparer(raw_m, m["symbol"].tolist(), None)
        beta_m = ex.beta_depuis_cours(raw_m, m["symbol"].tolist())
        rep = ex.replication_harx(ex.walk_forward_harx(ex.ajouter_x_vix(data_m, beta_m, vix)))
        c["replication_midcap"] = rep
    r = c["horizons"][ex.H]["dm"]
    _inserer(cli, lot, nom, ex.verdict_harx(c, rep), c, ic=r.get("ecart"), t=r.get("t"), seuil=2.0,
             n_essais=ex.N_ESSAIS_HARX)


def _examen_har_etendu(ctx: Contexte, nom: str):
    cli, lot, data, raw = ctx.cli, ctx.lot, ctx.data, ctx.raw
    import fred
    vix = _vix(DEBUT_EXAMEN)
    macro = pd.DataFrame({k: fred._fetch_fred_serie(sid, start_date=DEBUT_EXAMEN).set_index("date")["valeur"]
                          for k, sid in mreg.SERIES_FRED.items()})
    macro.index = pd.to_datetime(macro.index)
    tables = ex.variables_cours(raw, ctx.symboles)
    d, modeles = ex.modeles_etendus(ex.ajouter_etendu(data, tables, vix, macro))
    d_plc, _ = ex.modeles_etendus(ex.ajouter_etendu(data, tables, vix, macro, decalage=ex.DECALAGE_PLACEBO_VIX))
    te, tp = ex.walk_forward_lineaire(d, modeles), ex.walk_forward_lineaire(d_plc, modeles)
    c = ex.comparer_etendu(te, tp)
    c["debut_test"] = str(pd.Timestamp(te["date"].min()).date())
    c["variables"] = modeles
    rep = None
    if c["regles"]["2abcd"] and c["regles"]["3_placebo_ne_bat_pas_m1"]:     # règle 2 (e), conditionnelle
        m = universe.get_sp400_tickers()
        raw_m, _ = charger_cours(sorted(set(m["symbol"]) | {mh.INDICE}), debut=DEBUT_EXAMEN)
        data_m, _ = ex.preparer(raw_m, m["symbol"].tolist(), None)
        dm_, mod_m = ex.modeles_etendus(ex.ajouter_etendu(data_m, ex.variables_cours(raw_m, m["symbol"].tolist()), vix, macro))
        rep = ex.replication_etendu(ex.walk_forward_lineaire(dm_, mod_m))
        c["replication_midcap"] = rep
    r = c["m2_contre_har"]
    _inserer(cli, lot, nom, ex.verdict_etendu(c, rep), c, ic=r.get("ecart"), t=r.get("t"), seuil=2.0,
             n_essais=ex.N_ESSAIS_ETENDU)


def _examen_harx_1m(ctx: Contexte, nom: str):
    cli, lot, raw, compo, secteurs = ctx.cli, ctx.lot, ctx.raw, ctx.compo, ctx.secteurs
    vix = _vix(DEBUT_EXAMEN)
    m = universe.get_sp400_tickers()
    raw_m, _ = charger_cours(sorted(set(m["symbol"]) | {mh.INDICE}), debut=DEBUT_EXAMEN)
    c_mid = ex.essai_harx_1m(raw_m, m["symbol"].tolist(), vix)
    c_sp = ex.essai_harx_1m(raw, ctx.symboles, vix, compo, secteurs)
    v, cond = ex.verdict_harx_1m(c_mid)
    diag = {"midcaps": c_mid, "sp500_reproduction": c_sp, "conditions": cond,
            "decision": "confirme" if v == "confirmé" else "non_confirme",
            "avertissement_couverture": c_mid["couverture"]["harx"]["avertissement"]}
    r = c_mid["horizons"][ex.H_MOIS]["dm"]
    _inserer(cli, lot, nom, v, diag, ic=r.get("ecart"), t=r.get("t"), seuil=2.0, n_essais=ex.N_ESSAIS_HARX_1M)


def _examen_harx_1m_v2(ctx: Contexte, nom: str):
    cli, lot, raw, compo, secteurs = ctx.cli, ctx.lot, ctx.raw, ctx.compo, ctx.secteurs
    vix = _vix(DEBUT_EXAMEN)
    m = universe.get_sp400_tickers()
    raw_m, _ = charger_cours(sorted(set(m["symbol"]) | {mh.INDICE}), debut=DEBUT_EXAMEN)
    c_mid = ex.essai_harx_1m(raw_m, m["symbol"].tolist(), vix, nettoyage=True)
    c_sp = ex.essai_harx_1m(raw, ctx.symboles, vix, compo, secteurs, nettoyage=True,
                            winsor=c_mid["etape"] == 2)      # même étape que les midcaps (§ 4.17)
    v, cond = ex.verdict_harx_1m(c_mid)
    diag = {"midcaps": c_mid, "sp500_reproduction": c_sp, "conditions": cond, "etape": c_mid["etape"],
            "decision": "confirme" if v == "confirmé" else "non_confirme",
            "avertissement_couverture": c_mid["couverture"]["harx"]["avertissement"]}
    r = c_mid["horizons"][ex.H_MOIS]["dm"]
    _inserer(cli, lot, nom, v, diag, ic=r.get("ecart"), t=r.get("t"), seuil=2.0, n_essais=ex.N_ESSAIS_HARX_1M_V2)


def _examen_asymetrie(ctx: Contexte, nom: str):
    cli, lot, data, raw = ctx.cli, ctx.lot, ctx.data, ctx.raw
    c = ex.essai_asymetrie(data, raw)
    pl = ex.essai_asymetrie(data, raw, melange=True)
    v, propre = ex.verdict_asymetrie(c, pl)
    c["placebo"] = {k: {"ic": x.get("ecart"), "t": x.get("t")} for k, x in pl["tests"].items()}
    c["placebo_propre"] = propre
    a = c["tests"]["A_persistance_126"]
    _inserer(cli, lot, nom, v, c, ic=a.get("ecart"), t=a.get("t"), seuil=2.0, n_essais=ex.N_ESSAIS_ASYM)


def calculer_marges(raw: pd.DataFrame, symboles, compo, secteurs) -> tuple[dict, bool]:
    """Marges de « Je limite le risque » apprises sur le backtest (§ 7.4) : (diagnostics, règle 3 tenue)."""
    tous = {**bt.PORTEFEUILLES, **bt.PORTEFEUILLES_RISQUE}
    res = bt.backtest(raw, symboles, compo, debut="2006-01-01", base="sp500",
                      variantes=["hist_3a", "hybride"], secteurs=secteurs, portefeuilles=tous,
                      garder_poids=True, garder_frontieres=True)
    px = mh.cours_ajustes(raw)   # rentabilités réalisées, dividendes compris (§ 4.28)
    c = {"marges": {}, "rythmes": {}, "couverture": {}, "marges_par_source": {}}
    for lim in [0.10, 0.12, 0.15, 0.18]:
        c["marges"][f"{int(lim * 100)}"] = bt.marge_walk_forward(res, px, lim, "hybride", revision_mois=6)
    # Correction du 23/11/2026 (METHODE § 7.4) : chaque source et une grille de limites de 8 à 35 %
    for var in ["hist_3a", "hybride"]:
        c["marges_par_source"][var] = {f"{int(round(lim * 100))}": bt.marge_walk_forward(res, px, lim, var, revision_mois=6)
                                       for lim in bt.LIMITES_MARGE}
    for rythme in [1, 6, 12]:
        for nom_pf in ["sharpe_max", "risque_15"]:
            c["rythmes"][f"{nom_pf}_{rythme}m"] = bt.backtest_reel(res, px, nom_pf, "hybride", revision_mois=rythme)
    c["couverture"] = {var: bt.couverture_fourchette(res, px, "sharpe_max", var) for var in ["hist_3a", "hybride"]}
    # Règle 5 : loi de Student à 5 degrés (90 % des scénarios dans ±2,015 σ), revérifiée
    c["couverture"]["hybride_student5"] = bt.couverture_fourchette(res, px, "sharpe_max", "hybride", z=2.015)
    c["debut"] = str(pd.Timestamp(res["date"].min()).date())
    parts = [m["part_respectee_avec_marge"] for m in c["marges"].values() if m["part_respectee_avec_marge"] is not None]
    c["_parts"] = parts
    return c, bool(parts) and min(parts) >= 0.70                 # règle 3 : au moins 70 % des semestres


def _examen_marge(ctx: Contexte, nom: str):
    cli, lot = ctx.cli, ctx.lot
    c, ok = calculer_marges(ctx.raw, ctx.symboles, ctx.compo, ctx.secteurs)
    parts = c.pop("_parts")
    m15 = c["marges"]["15"]
    # Publication de la marge pour l'appli (lue dans model_runs, kind « marge_risque »)
    cli.table("model_runs").upsert(_clean({
        "kind": "marge_risque", "trained_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "verdict": "respectée" if ok else "insuffisante",
        "diagnostics": {"marge": m15["marge_actuelle"], "marges": c["marges"], "marges_par_source": c["marges_par_source"],
                        "part_respectee": m15["part_respectee_avec_marge"], "depuis": c["debut"]},
    }), on_conflict="kind").execute()
    v = (f"limite tenue {min(parts):.0%} des semestres au moins" if parts else "non calculable")
    _inserer(cli, lot, nom, v, c, ic=m15["marge_actuelle"])


ECART_MARGE_NETTOYEE = 0.05     # § 4.30 : au-delà, les erreurs de cours pèsent sur la marge


def resume_marge(c: dict) -> dict:
    """Résumé d'un calcul de marge pour la comparaison du § 4.30."""
    mps = c.get("marges_par_source", {})
    out = {src: {lim: {"marge": (mps.get(src, {}).get(lim) or {}).get("marge_actuelle"),
                       "part": (mps.get(src, {}).get(lim) or {}).get("part_respectee_avec_marge")} for lim in ("10", "15", "20")}
           for src in ("hist_3a", "hybride")}
    for nom_pf in ("risque_15", "sharpe_max"):
        r = c.get("rythmes", {}).get(f"{nom_pf}_6m") or {}
        out[nom_pf] = {"volatilite": r.get("volatilite"), "rendement_net": r.get("rendement_net")}
    return out


def decision_marge(actuel: dict, nettoye: dict) -> dict:
    """Règle du § 4.30 sur la marge IA + HAR à 15 %."""
    a, n = actuel["hybride"]["15"]["marge"], nettoye["hybride"]["15"]["marge"]
    ecart = (n - a) if a is not None and n is not None else None
    return {"marge_actuelle": a, "marge_nettoyee": n, "ecart": ecart,
            "nettoyage_adopte": bool(ecart is not None and ecart > ECART_MARGE_NETTOYEE)}


def _examen_marge_verif(ctx: Contexte, nom: str):
    """Vérification du § 4.30 : marge actuelle, sur les seuls survivants, et sans les pics aberrants. N'écrit pas la marge publiée."""
    actuels = sorted(set(ctx.snap["symbol"]) | {mh.INDICE})
    calculs = {}
    calculs["actuel"] = resume_marge(calculer_marges(ctx.raw, ctx.symboles, ctx.compo, ctx.secteurs)[0])
    raw_s = ctx.raw[ctx.raw["symbol"].isin(actuels)]
    calculs["survivants"] = resume_marge(calculer_marges(raw_s, [s for s in actuels if s != mh.INDICE], ctx.compo, ctx.secteurs)[0])
    raw_n, pics = ex.nettoyer_pics(ctx.raw)
    calculs["nettoye"] = resume_marge(calculer_marges(raw_n, ctx.symboles, ctx.compo, ctx.secteurs)[0])
    d = decision_marge(calculs["actuel"], calculs["nettoye"])
    anciens = set(ctx.symboles) - set(actuels)
    c = {**calculs, "decision": d, "n_pics": len(pics), "n_titres_pics": len({p["symbol"] for p in pics}),
         "pics_anciens_membres": sum(p["symbol"] in anciens for p in pics), "pics": pics[:60]}
    v = ("nettoyage adopté : les erreurs de cours pesaient" if d["nettoyage_adopte"]
         else "baisse réelle : la marge publiée reste")
    _inserer(ctx.cli, ctx.lot, nom, v, c, ic=d["ecart"], n_essais=0)


def _examen_backtest_reel(ctx: Contexte, nom: str):
    cli, lot, raw, compo, secteurs = ctx.cli, ctx.lot, ctx.raw, ctx.compo, ctx.secteurs
    tous = {**bt.PORTEFEUILLES, **bt.PORTEFEUILLES_RISQUE}
    res = bt.backtest(raw, ctx.symboles, compo, debut="2006-01-01", base=bt.BASES,
                      variantes=["hist_3a", "ia"], secteurs=secteurs, portefeuilles=tous, garder_poids=True)
    px = mh.cours_ajustes(raw)   # rentabilités réalisées, dividendes compris (§ 4.28)
    c = {"reel": {}, "couverture": {}}
    for nom_pf in tous:
        for var in ["hist_3a", "ia"]:
            c["reel"][f"{nom_pf}_{var}"] = bt.backtest_reel(res, px, nom_pf, var)
    c["couverture"] = {var: bt.couverture_fourchette(res, px, "sharpe_max", var) for var in ["hist_3a", "ia"]}
    mat = (res[res["portefeuille"] != "indice"]
           .assign(col=lambda x: x["base"] + "_" + x["variante"] + "_" + x["portefeuille"])
           .pivot_table(index="date", columns="col", values="rendement"))
    c["pbo"] = ex.pbo(mat)
    c["debut"] = str(pd.Timestamp(res["date"].min()).date())
    p = c["pbo"]["pbo"]
    _inserer(cli, lot, nom, f"PBO {p:.0%}" if p is not None else "PBO non calculable", c, ic=p)


def _examen_audit_biais(ctx: Contexte, nom: str):
    """Constats du § 4.21 (aucun essai compté : n_essais = 0)."""
    a = ex.audit_biais(ctx.t, ctx.ret, ctx.compo)
    a["debut_test"] = str(pd.Timestamp(ctx.t["date"].min()).date())
    g = a["global"]
    _inserer(ctx.cli, ctx.lot, nom, ex.verdict_audit(a), a, ic=g.get("rapport_variance"), n_essais=0)


def _examen_har_relatif(ctx: Contexte, nom: str):
    """Essai du § 4.23 (16e de la famille « références »)."""
    d = ex.ajouter_risque_habituel(ctx.data, ctx.ret)
    tr = ex.walk_forward_har_relatif(d)
    tp = ex.walk_forward_har_relatif(d, placebo=True)
    c = ex.comparer_har_relatif(tr, tp)
    c["debut_test"] = str(pd.Timestamp(tr["date"].min()).date())
    # Constat : l'hybride construit sur le relatif (ordre de l'IA, niveaux HAR relatif)
    t = ctx.t.merge(tr[["date", "symbol", "lvl_rel"]], on=["date", "symbol"], how="inner")
    t["lvl_hyb_rel"] = ex._rang_vers_niveau(t, "pred", "lvl_rel")
    c["hybride_relatif"] = {"qlike": float(ex._pertes_par_date(t, "lvl_hyb_rel").mean()),
                            "qlike_hybride": float(ex._pertes_par_date(t, "lvl_hybride").mean()),
                            "rapport_variance": ex._rapport_variance(t, "lvl_hyb_rel"),
                            "rapport_variance_hybride": ex._rapport_variance(t, "lvl_hybride")}
    c["decision"] = "har_relatif" if c["adopte"] else "har"
    _inserer(ctx.cli, ctx.lot, nom, ex.verdict_har_relatif(c), c, ic=c["dm"].get("ecart"), t=c["dm"].get("t"),
             n_essais=ex.N_ESSAIS_HAR_RELATIF)


def _examen_ia_informee(ctx: Contexte, nom: str):
    """Essai du § 4.24 (6e de la famille « classement »)."""
    dplus = ex.ajouter_variables_ia(ctx.data, ctx.ret)
    feats = mh.FEATURES + ex.FEATURES_INFORMEE
    t_plus = ex.walk_forward(dplus, ctx.ret, feats=feats, references=False)
    t_plc = ex.walk_forward(dplus, ctx.ret, feats=feats, references=False, transformer=ex._melanger_informee())
    c = ex.comparer_informee(ctx.t, t_plus, t_plc)
    c["debut_test"] = str(pd.Timestamp(t_plus["date"].min()).date())
    config = t_plus["config"].mode().iloc[0]
    m = mh._modele(config).fit(dplus[feats], dplus["y"])
    c["importance"] = sorted([{"feature": f, "importance": float(v)} for f, v in zip(feats, mh._importances(m, config))],
                             key=lambda x: -x["importance"])
    c["decision"] = "informee" if c["adopte"] else "actuelle"
    _inserer(ctx.cli, ctx.lot, nom, ex.verdict_informee(c), c, ic=c["gain"], t=c["t"], seuil=c["seuil"],
             n_essais=ex.N_CANDIDATS_INFORMEE)


def _examen_har_protege(ctx: Contexte, nom: str):
    """Essai du § 4.25 (17e de la famille « références »)."""
    d = ex.ajouter_risque_habituel(ctx.data, ctx.ret)
    tr = ex.proteger(ex.walk_forward_har_relatif(d))
    tp = ex.proteger(ex.walk_forward_har_relatif(d, placebo=True))
    c = ex.comparer_har_relatif(tr, tp, col="lvl_prot", n_essais=ex.N_ESSAIS_HAR_PROTEGE)
    c["debut_test"] = str(pd.Timestamp(tr["date"].min()).date())
    c["part_choc"] = float(tr["choc"].mean())
    t = ctx.t.merge(tr[["date", "symbol", "lvl_prot"]], on=["date", "symbol"], how="inner")
    t["lvl_hyb_prot"] = ex._rang_vers_niveau(t, "pred", "lvl_prot")
    c["hybride_protege"] = {"qlike": float(ex._pertes_par_date(t, "lvl_hyb_prot").mean()),
                            "qlike_hybride": float(ex._pertes_par_date(t, "lvl_hybride").mean()),
                            "rapport_variance": ex._rapport_variance(t, "lvl_hyb_prot")}
    c["decision"] = "har_protege" if c["adopte"] else "har"
    _inserer(ctx.cli, ctx.lot, nom, ex.verdict_har_protege(c), c, ic=c["dm"].get("ecart"), t=c["dm"].get("t"),
             n_essais=ex.N_ESSAIS_HAR_PROTEGE)


def _examen_ia_climat(ctx: Contexte, nom: str):
    """Essai du § 4.26 (7e de la famille « classement »)."""
    vix = _vix(DEBUT_EXAMEN)
    feats = mh.FEATURES + ex.FEATURES_CLIMAT
    dplus = ex.ajouter_climat(ctx.data, vix)
    dplc = ex.ajouter_climat(ctx.data, vix, decalage=ex.DECALAGE_PLACEBO_VIX)
    t_plus = ex.walk_forward(dplus, ctx.ret, feats=feats, references=False)
    t_plc = ex.walk_forward(dplc, ctx.ret, feats=feats, references=False)
    c = ex.comparer_informee(ctx.t, t_plus, t_plc, n_candidats=ex.N_CANDIDATS_CLIMAT)
    c["debut_test"] = str(pd.Timestamp(t_plus["date"].min()).date())
    config = t_plus["config"].mode().iloc[0]
    m = mh._modele(config).fit(dplus[feats], dplus["y"])
    c["importance"] = sorted([{"feature": f, "importance": float(v)} for f, v in zip(feats, mh._importances(m, config))],
                             key=lambda x: -x["importance"])
    c["decision"] = "climat" if c["adopte"] else "actuelle"
    _inserer(ctx.cli, ctx.lot, nom, ex.verdict_informee(c), c, ic=c["gain"], t=c["t"], seuil=c["seuil"],
             n_essais=ex.N_CANDIDATS_CLIMAT)


EXAMENS = {   # nom -> (fonction, besoin du walk-forward commun `t`)
    "examen_references": (_examen_references, True),
    "examen_calibration": (_examen_calibration, True),
    "examen_crises": (_examen_crises, True),
    "examen_placebo": (_examen_placebo, False),
    "examen_sensibilite": (_examen_sensibilite, False),
    "examen_midcap": (_examen_midcap, False),
    "examen_hybride": (_examen_hybride, True),
    "examen_ia_contre_har": (_examen_ia_contre_har, True),
    "examen_xgb_niveau": (_examen_xgb_niveau, False),
    "examen_echelle_har": (_examen_echelle_har, False),
    "examen_multi_horizon": (_examen_multi_horizon, False),
    "examen_harx": (_examen_harx, False),
    "examen_har_etendu": (_examen_har_etendu, False),
    "examen_harx_1m": (_examen_harx_1m, False),
    "examen_harx_1m_v2": (_examen_harx_1m_v2, False),
    "examen_asymetrie": (_examen_asymetrie, False),
    "examen_marge": (_examen_marge, False),
    "examen_marge_verif": (_examen_marge_verif, False),
    "examen_audit_biais": (_examen_audit_biais, True),
    "examen_har_relatif": (_examen_har_relatif, True),
    "examen_ia_informee": (_examen_ia_informee, True),
    "examen_har_protege": (_examen_har_protege, True),
    "examen_ia_climat": (_examen_ia_climat, True),
    "examen_backtest_reel": (_examen_backtest_reel, False),
}


def symboles_examen(actuels, composition: pd.DataFrame | None) -> list[str]:
    """Titres de l'univers actuel et tous ceux ayant appartenu au S&P 500 (METHODE § 4.22)."""
    hist = set(composition["symbol"]) if composition is not None else set()
    return sorted(set(actuels) | hist)


def lancer_examen(cli, lot: str, noms: list[str]) -> list[str]:
    """Examen approfondi de l'IA de volatilité. Règles de décision : docs/METHODE.md § 4.8.
    Chaque examen est une fonction `_examen_…(ctx, nom)` du registre EXAMENS. Retourne les examens en échec."""
    echecs = []
    snap = pd.DataFrame(cli.table("titres_snapshot").select("symbol,secteur").execute().data)
    secteurs = dict(zip(snap["symbol"], snap["secteur"]))
    compo = mh.charger_composition()
    # § 4.22 : titres actuels ET tous les anciens membres du S&P 500 (moins de biais du survivant)
    titres = symboles_examen(snap["symbol"], compo)
    raw, _ = charger_cours(sorted(set(titres) | {mh.INDICE}), debut=DEBUT_EXAMEN)
    data, ret = ex.preparer(raw, titres, compo, secteurs, couverture_min=ex.COUVERTURE_MIN)
    print(f"[LABO] Examen : {data['symbol'].nunique()} titres ({len(titres)} demandés dont {len(titres) - snap['symbol'].nunique()} "
          f"anciens membres), {data['date'].nunique()} dates depuis {pd.Timestamp(data['date'].min()).date()}")
    ctx = Contexte(cli=cli, lot=lot, snap=snap, secteurs=secteurs, raw=raw, compo=compo, data=data, ret=ret, symboles=titres)
    besoin_t = [n for n in noms if n in EXAMENS and EXAMENS[n][1]]
    if besoin_t:
        try:
            ctx.t = ex.walk_forward(data, ret)
            print(f"[LABO] Examen : test de {pd.Timestamp(ctx.t['date'].min()).date()} à {pd.Timestamp(ctx.t['date'].max()).date()}")
        except Exception as e:
            print(f"[LABO][ERREUR] walk-forward de l'examen : {type(e).__name__} : {e}")
            echecs += besoin_t
    for nom in noms:
        fonction, besoin = EXAMENS.get(nom, (None, False))
        if fonction is None or (besoin and ctx.t is None):
            continue
        try:
            fonction(ctx, nom)
        except Exception as e:
            print(f"[LABO][ERREUR] {nom} : {type(e).__name__} : {e}")
            echecs.append(nom)
    return echecs


def n_essais_rendement(tous) -> int:
    """Essais de la famille « rendement » : variantes de EXPERIENCES et CNN × horizons (règle B du § 4.27)."""
    return len({e for e in tous if e[0] in EXPERIENCES or e[0] in EXPERIENCES_CNN or e[0] in EXPERIENCES_CONFIRMATION})


def n_essais_rendement_ancien(tous) -> int:
    """Ancien comptage (avant le § 4.27) : tout sauf risque, régime et backtests, donc examens et audits compris."""
    return len({e for e in tous if e[0] not in EXPERIENCES_RISQUE and e[0] not in EXPERIENCES_REGIME
                and not e[0].startswith(("backtest", "audit_"))})


def _dernier(cli, nom: str, horizon: str | None = None) -> dict | None:
    q = cli.table("experiences").select("verdict,ic,t_stat,seuil_t_global,cree_le").eq("nom", nom)
    if horizon:
        q = q.eq("horizon", horizon)
    r = q.order("id", desc=True).limit(1).execute().data
    return r[0] if r else None


def lancer_audit(cli, lot: str, noms: list[str], deja: list[dict]) -> list[str]:
    """Audit du § 4.27 : rendement publié, ensemble, CNN (anciens membres, placebo, groupes) et régime (placebo, calibration)."""
    echecs = []
    tous = {(r["nom"], r["horizon"]) for r in deja}
    n_nouveau, n_ancien = n_essais_rendement(tous), n_essais_rendement_ancien(tous)
    print(f"[LABO] Audit : famille rendement {n_nouveau} essais (ancien comptage : {n_ancien})")

    if "audit_regime" in noms:
        n_regime = len({r["nom"] for r in deja if r["nom"] in EXPERIENCES_REGIME})
        try:
            d = mreg.telecharger()
            m = mreg.mensuel(mreg.caracteristiques(d), mreg.cible(d))
            for modele in ("logistique", "xgboost"):
                ev = mreg.evaluer(m, modele, garder_tests=True)
                evp = mreg.evaluer(am.decaler_regime(m), modele)
                b = am.bilan_regime(ev, evp, _dernier(cli, f"regime_{modele}"), n_regime)
                b["modele"] = modele
                _ecrire(cli, {"lot": lot, "nom": f"audit_regime_{modele}", "horizon": "6m",
                              "description": EXPERIENCES_AUDIT["audit_regime"], "ic": b["auc"], "t_stat": b["t"],
                              "seuil_t_global": b["seuil"], "n_essais": 0, "verdict": am.verdict_audit_regime(b),
                              "diagnostics": b})
                print(f"[LABO] audit régime {modele} : AUC {b['auc']:.3f}, t {b['t']:.2f} -> {am.verdict_audit_regime(b)}")
        except Exception as e:
            print(f"[LABO][ERREUR] audit_regime : {type(e).__name__} : {e}")
            echecs.append("audit_regime")

    rendement = [n for n in noms if n in ("audit_rendement", "audit_ensemble", "audit_cnn")]
    if not rendement:
        return echecs
    snap = pd.DataFrame(cli.table("titres_snapshot").select("symbol,secteur").execute().data)
    secteurs = dict(zip(snap["symbol"], snap["secteur"]))
    compo = mh.charger_composition()
    titres = symboles_examen(snap["symbol"], compo)              # § 4.22 : anciens membres compris
    raw, splits = charger_cours(sorted(set(titres) | {mh.INDICE}))
    cov = ex.COUVERTURE_MIN

    def ecrire(nom, h, b, verdict):
        _ecrire(cli, {"lot": lot, "nom": nom, "horizon": h, "description": EXPERIENCES_AUDIT[nom], "ic": b.get("ic"),
                      "t_stat": b.get("t"), "seuil_t_global": b.get("seuil"), "n_essais": 0, "verdict": verdict,
                      "diagnostics": b})
        print(f"[LABO] {nom} {h} : IC {b.get('ic') or 0:+.3f} t {b.get('t') or 0:.2f} (seuil {b.get('seuil') or 0:.2f}) -> {verdict}")

    if "audit_rendement" in rendement:
        for h in ("court", "6m", "1a"):
            try:
                ligne, _ = mh.entrainer_horizon(raw, titres, h, compo, secteurs, "relatif", garder_tests=True, couverture_min=cov)
                evp = None
                if h == "6m":
                    evp = mh.entrainer_horizon(raw, titres, h, compo, secteurs, "relatif", placebo=True, couverture_min=cov)[0]["diagnostics"]
                avant = _dernier(cli, "reference", h) if h != "court" else None
                b = am.bilan_rendement(ligne["diagnostics"], evp, avant, n_ancien, n_nouveau)
                b["source_publiee"] = ligne["diagnostics"].get("source")
                ecrire("audit_rendement", h, b, am.verdict_audit_rendement(b))
            except Exception as e:
                print(f"[LABO][ERREUR] audit_rendement {h} : {type(e).__name__} : {e}")
                echecs.append(f"audit_rendement {h}")

    if "audit_ensemble" in rendement:
        faits = None
        try:
            faits = fsec.telecharger([s for s in titres if s != mh.INDICE])
        except Exception as e:
            print(f"[LABO][WARN] SEC indisponible pour l'ensemble : {e}")
        for h in HORIZONS_TEST:
            try:
                args = dict(composition=compo, secteurs=secteurs, cible_mode="alpha_secteur", faits_sec=faits, splits=splits,
                            forcer_config="ensemble", couverture_min=cov)
                ligne, _ = mh.entrainer_horizon(raw, titres, h, garder_tests=True, **args)
                evp = mh.entrainer_horizon(raw, titres, h, placebo=True, **args)[0]["diagnostics"] if h == "6m" else None
                b = am.bilan_rendement(ligne["diagnostics"], evp, _dernier(cli, "ensemble", h), n_ancien, n_nouveau)
                ecrire("audit_ensemble", h, b, am.verdict_audit_rendement(b))
            except Exception as e:
                print(f"[LABO][ERREUR] audit_ensemble {h} : {type(e).__name__} : {e}")
                echecs.append(f"audit_ensemble {h}")

    if "audit_cnn" in rendement:
        try:
            ligne = mcnn.entrainer_cnn(raw, titres, "6m", compo, secteurs, garder_tests=True, couverture_min=cov)
            evp = mcnn.entrainer_cnn(raw, titres, "6m", compo, secteurs, placebo=True, couverture_min=cov)["diagnostics"]
            b = am.bilan_rendement(ligne["diagnostics"], evp, _dernier(cli, "cnn", "6m"), n_ancien, n_nouveau)
            ecrire("audit_cnn", "6m", b, am.verdict_audit_rendement(b))
        except Exception as e:
            print(f"[LABO][ERREUR] audit_cnn : {type(e).__name__} : {e}")
            echecs.append("audit_cnn")
    return echecs


def lancer_confirmation(cli, lot: str, deja: list[dict]) -> list[str]:
    """Confirmation de l'ensemble sur le S&P MidCap 400 (METHODE § 4.31). Un seul passage : refusé si l'essai existe déjà.
    Si une donnée manque (liste du S&P 400, comptes SEC), rien n'est écrit : l'essai n'a pas eu lieu."""
    nom, h = "confirmation_ensemble_midcap", HORIZON_CONFIRMATION
    if any(r["nom"] == nom for r in deja):
        print(f"[LABO] {nom} : déjà lancé une fois, relance refusée (§ 4.31)")
        return []
    try:
        compo = mh.charger_composition()
        m = universe.get_sp400_tickers()
        titres = am.titres_inedits(m["symbol"], compo)
        secteurs = dict(zip(m["symbol"], m["secteur"]))
        raw, splits = charger_cours(sorted(set(titres) | {mh.INDICE}))
        titres = sorted(set(titres) & set(raw["symbol"]))
        faits = fsec.telecharger(titres)
        print(f"[LABO] {nom} : {len(m)} midcaps, {len(titres)} jamais membres du S&P 500, "
              f"comptes SEC de {faits['symbol'].nunique()} entreprises")
        args = dict(composition=None, secteurs=secteurs, cible_mode="alpha_secteur", faits_sec=faits, splits=splits,
                    forcer_config="ensemble", couverture_min=ex.COUVERTURE_MIN)
        ligne, _ = mh.entrainer_horizon(raw, titres, h, garder_tests=True, **args)
        evp = mh.entrainer_horizon(raw, titres, h, placebo=True, **args)[0]["diagnostics"]
    except Exception as e:
        print(f"[LABO][ERREUR] {nom} : {type(e).__name__} : {e} (rien n'est écrit, l'essai n'a pas eu lieu)")
        return [nom]
    n = n_essais_rendement({(r["nom"], r["horizon"]) for r in deja} | {(nom, h)})
    diag = ligne["diagnostics"]
    b = am.bilan_rendement(diag, evp, None, n, n)
    v, cond = am.verdict_confirmation(b)
    b.update({"conditions": cond, "decision": v, "n_midcaps": int(len(m)), "n_titres_inedits": len(titres),
              "couverture_fondamentaux": diag.get("couverture_fondamentaux"),
              "reference_sp500": _dernier(cli, "audit_ensemble", h),
              "limite": "membres actuels du S&P 400 seulement (pas d'historique de composition) : biais du survivant"})
    _ecrire(cli, {"lot": lot, "nom": nom, "horizon": h, "description": EXPERIENCES_CONFIRMATION[nom], "ic": b["ic"],
                  "t_stat": b["t"], "seuil_t_global": b["seuil"], "n_essais": n, "verdict": v, "diagnostics": b})
    print(f"[LABO] {nom} : IC {b['ic'] or 0:+.3f}, t {b['t'] or 0:.2f} (seuil {b['seuil']:.2f}, {n} essais), "
          f"placebo t {(b.get('placebo') or {}).get('t')} -> {v} ; conditions {cond}")
    return []


def main(noms: list[str]):
    t0 = time.time()
    cli = db.get_client()
    lot = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M")
    deja = cli.table("experiences").select("nom,horizon").execute().data or []
    echecs = []

    # Régime de marché : séries de marché seules (S&P 500, VIX, FRED), pas besoin des 500 titres
    regime = [n for n in noms if n in EXPERIENCES_REGIME]
    if regime:
        n_regime = len({r["nom"] for r in deja if r["nom"] in EXPERIENCES_REGIME} | set(regime))
        try:
            d = mreg.telecharger()
            m = mreg.mensuel(mreg.caracteristiques(d), mreg.cible(d))
            print(f"[LABO] Régime : {len(m)} mois depuis {m.index.min().date()}, baisses > 10 % : {int(m['y'].sum())}")
        except Exception as e:
            print(f"[LABO][ERREUR] données régime : {type(e).__name__} : {e}")
            echecs += regime
            regime = []
        for nom in regime:
            modele, description = EXPERIENCES_REGIME[nom]
            try:
                ev = mreg.evaluer(m, modele)
                ev["explication"] = mreg.explication(m, modele)
                ev["aujourdhui"] = mreg.probabilite_du_jour(d, modele)
            except Exception as e:
                print(f"[LABO][ERREUR] {nom} : {type(e).__name__} : {e}")
                echecs.append(nom)
                continue
            seuil = mh.seuil_t(ev.get("n_effectif"), n_candidats=n_regime)
            v = ("probant" if ev.get("auc", 0) > 0.6 and ev.get("gain_logloss", 0) > 0
                 and ev.get("n_effectif", 0) >= mh.MIN_PERIODES_SIGNAL and ev.get("t_stat", 0) > seuil else "non probant")
            _ecrire(cli, {
                "lot": lot, "nom": nom, "horizon": "6m", "description": description,
                "ic": ev.get("auc"), "t_stat": ev.get("t_stat"), "seuil_t_global": seuil,
                "n_essais": n_regime, "verdict": v, "diagnostics": ev,
            })
            print(f"[LABO] {nom} : AUC {ev.get('auc', 0):.3f}, gain log-loss {ev.get('gain_logloss', 0):+.4f}, "
                  f"t {ev.get('t_stat', 0):.2f} (seuil {seuil:.2f}) -> {v} ; aujourd'hui {ev['aujourdhui']['proba']:.1%}")
    noms = [n for n in noms if n not in EXPERIENCES_REGIME]
    if any(n in EXPERIENCES_CONFIRMATION for n in noms):
        echecs += lancer_confirmation(cli, lot, deja)
        noms = [n for n in noms if n not in EXPERIENCES_CONFIRMATION]
    audits = [n for n in noms if n in EXPERIENCES_AUDIT]
    if audits:
        echecs += lancer_audit(cli, lot, audits, deja)
        noms = [n for n in noms if n not in EXPERIENCES_AUDIT]
    examen = [n for n in noms if n in EXPERIENCES_EXAMEN]
    if examen:
        echecs += lancer_examen(cli, lot, examen)
        noms = [n for n in noms if n not in EXPERIENCES_EXAMEN]
    if not noms:
        print(f"[LABO] Terminé en {time.time() - t0:.0f} s")
        if echecs:
            sys.exit(f"Variantes en échec : {', '.join(echecs)}")
        return

    snap = pd.DataFrame(cli.table("titres_snapshot").select("symbol,secteur").execute().data)
    symboles = sorted(set(snap["symbol"]) | {mh.INDICE})
    compo = mh.charger_composition()
    # § 4.29 : la famille « risque » (dont le re-test mensuel) inclut aussi les anciens membres, comme l'examen (§ 4.22)
    titres_risque = symboles_examen(snap["symbol"], compo) if any(n in EXPERIENCES_RISQUE for n in noms) else None
    a_charger = sorted(set(symboles) | set(titres_risque or []))
    print(f"[LABO] {len(a_charger)} titres, essais : {', '.join(noms)} × {', '.join(HORIZONS_TEST)}")
    raw, splits = charger_cours(a_charger)
    faits_sec = None
    if any((n in EXPERIENCES and len(EXPERIENCES[n]) > 3 and EXPERIENCES[n][3])
           or (n in EXPERIENCES_RISQUE and len(EXPERIENCES_RISQUE[n]) > 2 and EXPERIENCES_RISQUE[n][2]) for n in noms):
        t1 = time.time()
        faits_sec = fsec.telecharger([s for s in symboles if s != mh.INDICE])
        print(f"[LABO] SEC : {len(faits_sec)} chiffres publiés, {faits_sec['symbol'].nunique()} entreprises, "
              f"{time.time() - t1:.0f} s")
    secteurs = dict(zip(snap["symbol"], snap["secteur"]))

    tous = {(r["nom"], r["horizon"]) for r in deja} | {(n, h) for n in noms for h in HORIZONS_TEST}
    # Famille « rendement » : seuls ses propres essais (METHODE § 4.27 B ; avant, les examens de l'IA de risque étaient comptés aussi)
    n_essais = n_essais_rendement(tous)
    n_essais_risque = len({e for e in tous if e[0] in EXPERIENCES_RISQUE})
    for nom in [n for n in noms if n in EXPERIENCES_CNN]:
        for h in HORIZONS_TEST:
            try:
                ligne = mcnn.entrainer_cnn(raw, snap["symbol"].tolist(), h, compo, secteurs)
            except Exception as e:
                print(f"[LABO][ERREUR] {nom} {h} : {type(e).__name__} : {e}")
                echecs.append(f"{nom} {h}")
                continue
            if not ligne:
                continue
            d = ligne["diagnostics"]
            seuil = mh.seuil_t(d.get("n_effectif"), n_candidats=n_essais)
            v = verdict_labo(d.get("ic_moyen"), d.get("t_stat"), d.get("n_effectif"), seuil)
            _ecrire(cli, {
                "lot": lot, "nom": nom, "horizon": h, "description": EXPERIENCES_CNN[nom],
                "ic": d.get("ic_moyen"), "t_stat": d.get("t_stat"), "seuil_t_global": seuil,
                "n_essais": n_essais, "verdict": v, "diagnostics": {**d, "importance": ligne.get("importance")},
            })
            print(f"[LABO] cnn {h} : IC {d.get('ic_moyen', 0):+.3f} t {d.get('t_stat', 0):.2f} (seuil {seuil:.2f}) -> {v}")

    if "backtest_base_large" in noms:
        noms = [n for n in noms if n != "backtest_base_large"]
        try:
            res = bt.backtest(raw, snap["symbol"].tolist(), compo, base=bt.BASES, variantes=["hist_3a", "ia"],
                              secteurs=secteurs)
        except Exception as e:
            print(f"[LABO][ERREUR] backtest_base_large : {type(e).__name__} : {e}")
            echecs.append("backtest_base_large")
            res = None
        if res is not None:
            for nom_pf in ["sharpe_max", "variance_min"]:
                for variante in ["hist_3a", "ia"]:
                    c = bt.comparer_bases(res, nom_pf, variante)
                    ec = c["ecart"]
                    seuil = mh.seuil_t(c["sp500"]["n_mois"], n_candidats=4)   # 2 portefeuilles x 2 volatilités
                    # Règle de décision (docs/METHODE.md) : la base large est adoptée car elle retire un pari
                    # non prouvé, SAUF si elle est nettement moins bonne (t < −seuil).
                    v = ("probant" if ec["t"] > seuil else "moins bonne" if ec["t"] < -seuil else "équivalente")
                    _ecrire(cli, {
                        "lot": lot, "nom": f"backtest_base_large_{nom_pf}_{variante}", "horizon": "1m",
                        "description": EXPERIENCES_PORTEFEUILLE["backtest_base_large"],
                        "ic": ec["rendement_mensuel"], "t_stat": ec["t"], "seuil_t_global": seuil,
                        "n_essais": 4, "verdict": v, "diagnostics": c,
                    })
                    print(f"[LABO] base large {nom_pf} {variante} : S&P 500 {c['sp500']} | momentum {c['momentum40']} "
                          f"| indice {c.get('indice')} | écart {ec} -> {v}")

    for nom in [n for n in noms if n in EXPERIENCES_PORTEFEUILLE]:
        try:
            res = bt.backtest(raw, snap["symbol"].tolist(), compo)
            r = bt.resume(res)
        except Exception as e:
            print(f"[LABO][ERREUR] {nom} : {type(e).__name__} : {e}")
            echecs.append(nom)
            continue
        for nom_pf, bloc in r.items():
            comp = bloc.get("ia_vs_hist_3a", {})
            t_moins_risque = -comp.get("t", 0.0)          # > 0 : l'IA a donné un portefeuille moins risqué
            # 2 portefeuilles × 2 comparaisons : seuil corrigé de 4 essais
            seuil = mh.seuil_t(bloc["n_mois"], n_candidats=4)
            v = "probant" if comp.get("ecart_vol", 0) < 0 and t_moins_risque > seuil else "non probant"
            _ecrire(cli, {
                "lot": lot, "nom": f"{nom}_{nom_pf}", "horizon": "1m", "description": EXPERIENCES_PORTEFEUILLE[nom],
                "ic": comp.get("ecart_vol"), "t_stat": t_moins_risque, "seuil_t_global": seuil,
                "n_essais": 4, "verdict": v, "diagnostics": bloc,
            })
            vs = {k: round(x["vol_reelle"], 4) for k, x in bloc["variantes"].items()}
            print(f"[LABO] {nom}_{nom_pf} : vol réelle {vs} ; IA vs 3 ans {comp} -> {v}")

    for nom in [n for n in noms if n in EXPERIENCES_RISQUE]:
        genre, description, *opt_r = EXPERIENCES_RISQUE[nom]
        sec_r = bool(opt_r and opt_r[0])
        for h in HORIZONS_TEST:
            try:
                d = mr.entrainer_risque(raw, titres_risque, h, genre, compo,
                                        faits_sec if sec_r else None, splits if sec_r else None,
                                        couverture_min=ex.COUVERTURE_MIN)
                d["anciens_membres"] = True
            except Exception as e:
                print(f"[LABO][ERREUR] {nom} {h} : {type(e).__name__} : {e}")
                echecs.append(f"{nom} {h}")
                continue
            if not d:
                continue
            seuil = mh.seuil_t(d.get("n_effectif"), n_candidats=n_essais_risque)
            v = ("probant" if d["gain"] > mr.GAIN_MIN and d["n_effectif"] >= mh.MIN_PERIODES_SIGNAL
                 and d["t_stat"] > seuil else "non probant")
            _ecrire(cli, {
                "lot": lot, "nom": nom, "horizon": h, "description": description,
                "ic": d["ic_moyen"], "t_stat": d["t_stat"], "seuil_t_global": seuil,
                "n_essais": n_essais_risque, "verdict": v, "diagnostics": d,
            })
            print(f"[LABO] {nom:18s} {h:3s} IC {d['ic_moyen']:.3f} vs référence {d['ic_base']:.3f} "
                  f"(gain {d['gain']:+.3f}, t {d['t_stat']:.2f}, seuil {seuil:.2f}) -> {v}")

    for nom in [n for n in noms if n in EXPERIENCES]:
        mode, exclus, description, *opt = EXPERIENCES[nom]
        avec_sec = bool(opt and opt[0])
        forcer = opt[1] if len(opt) > 1 else None
        for h in HORIZONS_TEST:
            try:
                ligne, _ = mh.entrainer_horizon(raw, snap["symbol"].tolist(), h, compo, secteurs, mode, exclus,
                                                faits_sec if avec_sec else None, splits if avec_sec else None, forcer)
            except Exception as e:   # une variante en échec ne doit pas empêcher les autres
                print(f"[LABO][ERREUR] {nom} {h} : {type(e).__name__} : {e}")
                echecs.append(f"{nom} {h}")
                continue
            if not ligne:
                print(f"[LABO][WARN] {nom} {h} : pas assez de données")
                continue
            d = ligne["diagnostics"]
            seuil = mh.seuil_t(d.get("n_effectif"), n_candidats=n_essais)
            v = verdict_labo(d.get("ic_moyen"), d.get("t_stat"), d.get("n_effectif"), seuil)
            _ecrire(cli, {
                "lot": lot, "nom": nom, "horizon": h, "description": description,
                "ic": d.get("ic_moyen"), "t_stat": d.get("t_stat"), "seuil_t_global": seuil,
                "n_essais": n_essais, "verdict": v,
                "diagnostics": {**d, "importance": ligne.get("importance")},
            })
            reg = d.get("regimes", {})
            print(f"[LABO] {nom:14s} {h:3s} IC {d.get('ic_moyen', 0):+.3f} t {d.get('t_stat', 0):.2f} "
                  f"(seuil {seuil:.2f}, {n_essais} essais) hausse {reg.get('hausse', {}).get('ic')} "
                  f"baisse {reg.get('baisse', {}).get('ic')} -> {v}")
    print(f"[LABO] Terminé en {time.time() - t0:.0f} s")
    if echecs:
        sys.exit(f"Variantes en échec : {', '.join(echecs)}")


EN_SOMMEIL = set(EXPERIENCES_CNN) | set(EXPERIENCES_REGIME) | {"audit_cnn", "audit_regime"}   # METHODE § 4.29


def choisir_experiences(choix: str) -> list[str]:
    """Essais à lancer : liste explicite, ou tous les essais connus hors modèles en sommeil (CNN, régime)."""
    connues = (list(EXPERIENCES) + list(EXPERIENCES_RISQUE) + list(EXPERIENCES_PORTEFEUILLE)
               + list(EXPERIENCES_REGIME) + list(EXPERIENCES_CNN) + list(EXPERIENCES_EXAMEN) + list(EXPERIENCES_AUDIT)
               + list(EXPERIENCES_CONFIRMATION))
    choix = (choix or "").strip()
    hors_defaut = EN_SOMMEIL | set(EXPERIENCES_CONFIRMATION)      # § 4.31 : la confirmation se lance en la nommant
    noms = [n for n in connues if n not in hors_defaut] if choix in ("", "toutes") else [n.strip() for n in choix.split(",")]
    inconnues = [n for n in noms if n not in connues]
    if inconnues:
        raise ValueError(f"Expériences inconnues : {inconnues} (connues : {connues})")
    return noms


if __name__ == "__main__":
    try:
        choisis = choisir_experiences(os.environ.get("EXPERIENCES", ""))
    except ValueError as e:
        sys.exit(str(e))
    main(choisis)
