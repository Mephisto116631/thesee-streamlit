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
}
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
    snap = pd.DataFrame(cli.table("titres_snapshot").select("symbol,secteur").execute().data)
    symboles = sorted(set(snap["symbol"]) | {mh.INDICE})
    print(f"[LABO] {len(symboles)} titres, essais : {', '.join(noms)} × {', '.join(HORIZONS_TEST)}")
    raw, splits = charger_cours(symboles)
    faits_sec = None
    if any(len(EXPERIENCES[n]) > 3 and EXPERIENCES[n][3] for n in noms):
        t1 = time.time()
        faits_sec = fsec.telecharger([s for s in symboles if s != mh.INDICE])
        print(f"[LABO] SEC : {len(faits_sec)} chiffres publiés, {faits_sec['symbol'].nunique()} entreprises, "
              f"{time.time() - t1:.0f} s")
    compo = mh.charger_composition()
    secteurs = dict(zip(snap["symbol"], snap["secteur"]))

    deja = cli.table("experiences").select("nom,horizon").execute().data or []
    essais = {(r["nom"], r["horizon"]) for r in deja} | {(n, h) for n in noms for h in HORIZONS_TEST}
    n_essais = len(essais)
    lot = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d %H:%M")

    for nom in noms:
        mode, exclus, description, *opt = EXPERIENCES[nom]
        avec_sec = bool(opt and opt[0])
        for h in HORIZONS_TEST:
            ligne, _ = mh.entrainer_horizon(raw, snap["symbol"].tolist(), h, compo, secteurs, mode, exclus,
                                            faits_sec if avec_sec else None, splits if avec_sec else None)
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


if __name__ == "__main__":
    choix = os.environ.get("EXPERIENCES", "").strip()
    noms = list(EXPERIENCES) if choix in ("", "toutes") else [n.strip() for n in choix.split(",")]
    inconnues = [n for n in noms if n not in EXPERIENCES]
    if inconnues:
        sys.exit(f"Expériences inconnues : {inconnues} (connues : {list(EXPERIENCES)})")
    main(noms)
