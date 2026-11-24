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

import _st_shim
sys.modules["streamlit"] = _st_shim

import pandas as pd  # noqa: E402
import yfinance as yf  # noqa: E402

import data_pipeline as dp   # noqa: E402
import db                    # noqa: E402
import fondamentaux_sec as fsec  # noqa: E402
import modele_horizon as mh  # noqa: E402
import modele_risque as mr   # noqa: E402
import backtest_risque as bt  # noqa: E402
import modele_regime as mreg  # noqa: E402
import modele_cnn as mcnn     # noqa: E402
import examen_risque as ex    # noqa: E402
import universe              # noqa: E402
from publish import _clean   # noqa: E402

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
            frames.append(d.dropna(subset=["close"])[["symbol", "date", "open", "high", "low", "close", "volume"]])
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


def lancer_examen(cli, lot: str, noms: list[str]) -> list[str]:
    """Examen approfondi de l'IA de volatilité. Règles de décision : docs/METHODE.md § 4.8."""
    echecs = []
    snap = pd.DataFrame(cli.table("titres_snapshot").select("symbol,secteur").execute().data)
    secteurs = dict(zip(snap["symbol"], snap["secteur"]))
    symboles = sorted(set(snap["symbol"]) | {mh.INDICE})
    raw, _ = charger_cours(symboles, debut=DEBUT_EXAMEN)
    compo = mh.charger_composition()
    data, ret = ex.preparer(raw, snap["symbol"].tolist(), compo, secteurs)
    print(f"[LABO] Examen : {data['symbol'].nunique()} titres, {data['date'].nunique()} dates depuis "
          f"{pd.Timestamp(data['date'].min()).date()}")
    t = None
    if {"examen_references", "examen_calibration", "examen_crises", "examen_hybride", "examen_ia_contre_har"} & set(noms):
        try:
            t = ex.walk_forward(data, ret)
            print(f"[LABO] Examen : test de {pd.Timestamp(t['date'].min()).date()} à {pd.Timestamp(t['date'].max()).date()}")
        except Exception as e:
            print(f"[LABO][ERREUR] walk-forward de l'examen : {type(e).__name__} : {e}")
            echecs += [n for n in noms if n in ("examen_references", "examen_calibration", "examen_crises", "examen_hybride",
                                                "examen_ia_contre_har")]
    for nom in noms:
        try:
            if nom == "examen_references" and t is not None:
                c = ex.comparer_references(t)
                b = c["meilleure_reference"]
                v = "l'IA reste" if c["ia_reste"] else f"bascule sur {b.upper()}"
                c["debut_test"] = str(pd.Timestamp(t["date"].min()).date())
                c["garch_ab"] = sorted(t["garch_ab"].unique().tolist())
                _inserer(cli, lot, nom, v, c, ic=c["ic"]["ia"], t=-c["dm"][b]["t"], seuil=c["seuil"], n_essais=3)
            elif nom == "examen_calibration" and t is not None:
                c = {k: ex.calibration(t, col) for k, col in
                     [("ia", "lvl_ia"), ("vol_3m", "lvl_vol_3m"), ("ewma", "lvl_ewma"), ("garch", "lvl_garch"), ("har", "lvl_har")]
                     if t[col].notna().any()}
                b = c["ia"]["biais_median"]
                v = "calibrée" if abs(b) <= 0.10 else ("surestime" if b > 0 else "sous-estime") + f" de {abs(b):.0%}"
                _inserer(cli, lot, nom, v, c, ic=b)
            elif nom == "examen_crises" and t is not None:
                vix = None
                try:
                    vix = mreg.telecharger(DEBUT_EXAMEN)["vix"]
                except Exception as e:
                    print(f"[LABO][WARN] VIX indisponible : {e}")
                c = ex.par_periode(t, vix)
                gagnees = sum(1 for r in c["crises"].values() if r["gain_qlike"] > 0)
                v = f"IA meilleure dans {gagnees}/{len(c['crises'])} crises"
                _inserer(cli, lot, nom, v, c, ic=gagnees / max(1, len(c["crises"])))
            elif nom == "examen_placebo":
                c = ex.placebo(data, ret)        # 10 tirages : règle 4 de la PR #27, |moyenne| < 2 %
                ok = abs(c["ic_cible_melangee"] or 0) < 0.02 and (c["ic_fuite_volontaire"] or 0) > 0.5
                _inserer(cli, lot, nom, "réussi" if ok else "ÉCHEC : chercher une fuite", c, ic=c["ic_cible_melangee"])
            elif nom == "examen_sensibilite":
                c = ex.sensibilite(data, ret)
                ok = all(r["gain"] > 0 for r in c.values())
                _inserer(cli, lot, nom, "réussi (gain positif partout)" if ok else "fragile", c,
                         ic=min(r["gain"] for r in c.values()) if c else None)
            elif nom == "examen_midcap":
                m = universe.get_sp400_tickers()
                raw_m, _ = charger_cours(sorted(set(m["symbol"]) | {mh.INDICE}), debut=DEBUT_EXAMEN)
                data_m, _ = ex.preparer(raw_m, m["symbol"].tolist(), None)
                c = ex.autre_marche(data, data_m)
                _inserer(cli, lot, nom, "même résultat" if c["gain"] > 0 else "ne se généralise pas", c,
                         ic=c["gain"], t=c["t"])
            elif nom == "examen_hybride" and t is not None:
                c = ex.comparer_hybride(t)
                c["debut_test"] = str(pd.Timestamp(t["date"].min()).date())
                v = "publié" if c["publie"] else "HAR seul"
                _inserer(cli, lot, nom, v, c, ic=c["ic"]["hybride"], t=c["t_ic"], seuil=c["seuil"], n_essais=4)
            elif nom == "examen_ia_contre_har" and t is not None:
                c = ex.ia_contre_har(t)
                tous = {"sharpe_max": None, "risque_15": 0.15}
                res = bt.backtest(raw, snap["symbol"].tolist(), compo, debut="2006-01-01", base="sp500",
                                  variantes=["hybride", "har"], secteurs=secteurs, portefeuilles=tous, garder_poids=True)
                px = raw.pivot_table(index="date", columns="symbol", values="close").sort_index()
                c["backtest"] = {f"{pf_}_{v}": bt.backtest_reel(res, px, pf_, v, revision_mois=6)
                                 for pf_ in tous for v in ["hybride", "har"]}
                v = "l'IA reste (hybride)" if c["ia_reste"] else "HAR seul"
                _inserer(cli, lot, nom, v, c, ic=c["gain"], t=c["t"], seuil=c["seuil"], n_essais=5)
            elif nom == "examen_xgb_niveau":
                tb = ex.walk_forward_niveau(data, "B")
                ta = ex.walk_forward_niveau(data, "A")
                tp = ex.walk_forward_niveau(data, "B", melange=True)
                c = ex.comparer_niveau(tb, ta, tp)
                c["debut_test"] = str(pd.Timestamp(tb["date"].min()).date())
                v = ("candidate (règles 1, 2 et 3 réunies)" if c["candidate"]
                     else "non candidate : " + ", ".join(k for k, ok in c["regles"].items() if not ok))
                _inserer(cli, lot, nom, v, c, ic=c["ic"]["xgb"], t=c["B"]["t"], seuil=c["B"]["seuil"], n_essais=7)
            elif nom == "examen_echelle_har":
                te = ex.walk_forward_echelle(data)
                c = ex.comparer_echelle(te)
                c["debut_test"] = str(pd.Timestamp(te["date"].min()).date())
                v = ("candidat (règles 1, 2 et 3 réunies)" if c["candidate"]
                     else "non candidat : " + ", ".join(k for k, ok in c["regles"].items() if not ok))
                _inserer(cli, lot, nom, v, c, ic=c["ecart"], t=c["t"], seuil=c["seuil"], n_essais=8)
            elif nom == "examen_multi_horizon":
                par_h, plc = {}, {}
                for hh in ex.HORIZONS_MULTI:
                    d_h = data if hh == ex.H else ex.preparer(raw, snap["symbol"].tolist(), compo, secteurs, h=hh)[0]
                    par_h[hh] = ex.walk_forward_niveau(d_h, "B", h=hh)
                    plc[hh] = ex.walk_forward_niveau(d_h, "B", h=hh, melange=True)
                    print(f"[LABO] multi-horizon : h = {hh} j terminé")
                c = ex.comparer_multi(par_h, plc)
                r = c["regles"]
                v = ("piste" if r["1_piste"] else "fuite probable" if r["2_fuite_probable"] else "B pire que HAR" if r["3_B_pire"]
                     else "équivalence démontrée" if (r["4_equivalence"] and c["peut_conclure_equivalence"]) else "sans pouvoir de conclure")
                _inserer(cli, lot, nom, v, c, ic=c["aspa"]["ecart"], t=c["aspa"]["t"], seuil=2.0, n_essais=1)
            elif nom == "examen_harx":
                vix = _vix(DEBUT_EXAMEN)
                beta = ex.beta_depuis_cours(raw, snap["symbol"].tolist())
                par_h, plc = {}, {}
                for hh in ex.HORIZONS_HARX:
                    d_h = data if hh == ex.H else ex.preparer(raw, snap["symbol"].tolist(), compo, secteurs, h=hh)[0]
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
            elif nom == "examen_har_etendu":
                import fred
                vix = _vix(DEBUT_EXAMEN)
                macro = pd.DataFrame({k: fred._fetch_fred_serie(sid, start_date=DEBUT_EXAMEN).set_index("date")["valeur"]
                                      for k, sid in mreg.SERIES_FRED.items()})
                macro.index = pd.to_datetime(macro.index)
                tables = ex.variables_cours(raw, snap["symbol"].tolist())
                d, modeles = ex.modeles_etendus(ex.ajouter_etendu(data, tables, vix, macro))
                dp, _ = ex.modeles_etendus(ex.ajouter_etendu(data, tables, vix, macro, decalage=ex.DECALAGE_PLACEBO_VIX))
                te, tp = ex.walk_forward_lineaire(d, modeles), ex.walk_forward_lineaire(dp, modeles)
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
            elif nom == "examen_harx_1m":
                vix = _vix(DEBUT_EXAMEN)
                m = universe.get_sp400_tickers()
                raw_m, _ = charger_cours(sorted(set(m["symbol"]) | {mh.INDICE}), debut=DEBUT_EXAMEN)
                c_mid = ex.essai_harx_1m(raw_m, m["symbol"].tolist(), vix)
                c_sp = ex.essai_harx_1m(raw, snap["symbol"].tolist(), vix, compo, secteurs)
                v, cond = ex.verdict_harx_1m(c_mid)
                diag = {"midcaps": c_mid, "sp500_reproduction": c_sp, "conditions": cond,
                        "decision": "confirme" if v == "confirmé" else "non_confirme",
                        "avertissement_couverture": c_mid["couverture"]["harx"]["avertissement"]}
                r = c_mid["horizons"][ex.H_MOIS]["dm"]
                _inserer(cli, lot, nom, v, diag, ic=r.get("ecart"), t=r.get("t"), seuil=2.0, n_essais=ex.N_ESSAIS_HARX_1M)
            elif nom == "examen_harx_1m_v2":
                vix = _vix(DEBUT_EXAMEN)
                m = universe.get_sp400_tickers()
                raw_m, _ = charger_cours(sorted(set(m["symbol"]) | {mh.INDICE}), debut=DEBUT_EXAMEN)
                c_mid = ex.essai_harx_1m(raw_m, m["symbol"].tolist(), vix, nettoyage=True)
                c_sp = ex.essai_harx_1m(raw, snap["symbol"].tolist(), vix, compo, secteurs, nettoyage=True,
                                        winsor=c_mid["etape"] == 2)      # même étape que les midcaps (§ 4.17)
                v, cond = ex.verdict_harx_1m(c_mid)
                diag = {"midcaps": c_mid, "sp500_reproduction": c_sp, "conditions": cond, "etape": c_mid["etape"],
                        "decision": "confirme" if v == "confirmé" else "non_confirme",
                        "avertissement_couverture": c_mid["couverture"]["harx"]["avertissement"]}
                r = c_mid["horizons"][ex.H_MOIS]["dm"]
                _inserer(cli, lot, nom, v, diag, ic=r.get("ecart"), t=r.get("t"), seuil=2.0, n_essais=ex.N_ESSAIS_HARX_1M_V2)
            elif nom == "examen_asymetrie":
                c = ex.essai_asymetrie(data, raw)
                pl = ex.essai_asymetrie(data, raw, melange=True)
                v, propre = ex.verdict_asymetrie(c, pl)
                c["placebo"] = {k: {"ic": x.get("ecart"), "t": x.get("t")} for k, x in pl["tests"].items()}
                c["placebo_propre"] = propre
                a = c["tests"]["A_persistance_126"]
                _inserer(cli, lot, nom, v, c, ic=a.get("ecart"), t=a.get("t"), seuil=2.0, n_essais=ex.N_ESSAIS_ASYM)
            elif nom == "examen_marge":
                tous = {**bt.PORTEFEUILLES, **bt.PORTEFEUILLES_RISQUE}
                res = bt.backtest(raw, snap["symbol"].tolist(), compo, debut="2006-01-01", base="sp500",
                                  variantes=["hist_3a", "hybride"], secteurs=secteurs, portefeuilles=tous,
                                  garder_poids=True, garder_frontieres=True)
                px = raw.pivot_table(index="date", columns="symbol", values="close").sort_index()
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
                ok = bool(parts) and min(parts) >= 0.70                 # règle 3 : au moins 70 % des semestres
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
            elif nom == "examen_backtest_reel":
                tous = {**bt.PORTEFEUILLES, **bt.PORTEFEUILLES_RISQUE}
                res = bt.backtest(raw, snap["symbol"].tolist(), compo, debut="2006-01-01", base=bt.BASES,
                                  variantes=["hist_3a", "ia"], secteurs=secteurs, portefeuilles=tous, garder_poids=True)
                px = raw.pivot_table(index="date", columns="symbol", values="close").sort_index()
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
        except Exception as e:
            print(f"[LABO][ERREUR] {nom} : {type(e).__name__} : {e}")
            echecs.append(nom)
    return echecs


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
    print(f"[LABO] {len(symboles)} titres, essais : {', '.join(noms)} × {', '.join(HORIZONS_TEST)}")
    raw, splits = charger_cours(symboles)
    faits_sec = None
    if any((n in EXPERIENCES and len(EXPERIENCES[n]) > 3 and EXPERIENCES[n][3])
           or (n in EXPERIENCES_RISQUE and len(EXPERIENCES_RISQUE[n]) > 2 and EXPERIENCES_RISQUE[n][2]) for n in noms):
        t1 = time.time()
        faits_sec = fsec.telecharger([s for s in symboles if s != mh.INDICE])
        print(f"[LABO] SEC : {len(faits_sec)} chiffres publiés, {faits_sec['symbol'].nunique()} entreprises, "
              f"{time.time() - t1:.0f} s")
    compo = mh.charger_composition()
    secteurs = dict(zip(snap["symbol"], snap["secteur"]))

    tous = {(r["nom"], r["horizon"]) for r in deja} | {(n, h) for n in noms for h in HORIZONS_TEST}
    n_essais = len({e for e in tous if e[0] not in EXPERIENCES_RISQUE and e[0] not in EXPERIENCES_REGIME
                    and not e[0].startswith("backtest")})
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
                d = mr.entrainer_risque(raw, snap["symbol"].tolist(), h, genre, compo,
                                        faits_sec if sec_r else None, splits if sec_r else None)
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


if __name__ == "__main__":
    choix = os.environ.get("EXPERIENCES", "").strip()
    connues = (list(EXPERIENCES) + list(EXPERIENCES_RISQUE) + list(EXPERIENCES_PORTEFEUILLE)
               + list(EXPERIENCES_REGIME) + list(EXPERIENCES_CNN) + list(EXPERIENCES_EXAMEN))
    noms = connues if choix in ("", "toutes") else [n.strip() for n in choix.split(",")]
    inconnues = [n for n in noms if n not in connues]
    if inconnues:
        sys.exit(f"Expériences inconnues : {inconnues} (connues : {connues})")
    main(noms)
