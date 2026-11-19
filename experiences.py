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
}
# Famille « régime de marché » : probabilité d'une baisse du S&P 500 de plus de 10 % en 6 mois
EXPERIENCES_REGIME = {
    "regime_logistique": ("logistique", "Régime de marché : régression logistique (coefficients lisibles)"),
    "regime_xgboost": ("xgboost", "Régime de marché : XGBoost prudent"),
}
# Algorithme 4 : CNN 1D sur les courbes (famille « rendement », même seuil corrigé)
EXPERIENCES_CNN = {"cnn": "CNN sur les courbes de cours (forme de la dernière année), alpha sectoriel"}
HORIZONS_TEST = ["6m", "1a"]


def charger_cours(symboles: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Cours (ajustés des divisions, comme toujours chez Yahoo) + historique des divisions d'actions."""
    frames, divisions = [], []
    for i in range(0, len(symboles), 100):
        lot = symboles[i:i + 100]
        try:
            d = yf.download(lot, start=dp.HISTORIQUE_LONG_DEBUT, progress=False, auto_adjust=False,
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
            cli.table("experiences").insert(_clean({
                "lot": lot, "nom": nom, "horizon": "6m", "description": description,
                "ic": ev.get("auc"), "t_stat": ev.get("t_stat"), "seuil_t_global": seuil,
                "n_essais": n_regime, "verdict": v, "diagnostics": ev,
            })).execute()
            print(f"[LABO] {nom} : AUC {ev.get('auc', 0):.3f}, gain log-loss {ev.get('gain_logloss', 0):+.4f}, "
                  f"t {ev.get('t_stat', 0):.2f} (seuil {seuil:.2f}) -> {v} ; aujourd'hui {ev['aujourdhui']['proba']:.1%}")
    noms = [n for n in noms if n not in EXPERIENCES_REGIME]
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
            cli.table("experiences").insert(_clean({
                "lot": lot, "nom": nom, "horizon": h, "description": EXPERIENCES_CNN[nom],
                "ic": d.get("ic_moyen"), "t_stat": d.get("t_stat"), "seuil_t_global": seuil,
                "n_essais": n_essais, "verdict": v, "diagnostics": {**d, "importance": ligne.get("importance")},
            })).execute()
            print(f"[LABO] cnn {h} : IC {d.get('ic_moyen', 0):+.3f} t {d.get('t_stat', 0):.2f} (seuil {seuil:.2f}) -> {v}")

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
            cli.table("experiences").insert(_clean({
                "lot": lot, "nom": f"{nom}_{nom_pf}", "horizon": "1m", "description": EXPERIENCES_PORTEFEUILLE[nom],
                "ic": comp.get("ecart_vol"), "t_stat": t_moins_risque, "seuil_t_global": seuil,
                "n_essais": 4, "verdict": v, "diagnostics": bloc,
            })).execute()
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
            cli.table("experiences").insert(_clean({
                "lot": lot, "nom": nom, "horizon": h, "description": description,
                "ic": d["ic_moyen"], "t_stat": d["t_stat"], "seuil_t_global": seuil,
                "n_essais": n_essais_risque, "verdict": v, "diagnostics": d,
            })).execute()
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
            cli.table("experiences").insert(_clean({
                "lot": lot, "nom": nom, "horizon": h, "description": description,
                "ic": d.get("ic_moyen"), "t_stat": d.get("t_stat"), "seuil_t_global": seuil,
                "n_essais": n_essais, "verdict": v,
                "diagnostics": {**d, "importance": ligne.get("importance")},
            })).execute()
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
               + list(EXPERIENCES_REGIME) + list(EXPERIENCES_CNN))
    noms = connues if choix in ("", "toutes") else [n.strip() for n in choix.split(",")]
    inconnues = [n for n in noms if n not in connues]
    if inconnues:
        sys.exit(f"Expériences inconnues : {inconnues} (connues : {connues})")
    main(noms)
