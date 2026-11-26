# audit_modeles.py
# ==============================================================================
# AUDIT DES QUATRE AUTRES MODÈLES (docs/METHODE.md § 4.27) : rendement publié, ensemble, CNN, régime de marché.
# Constats et règles fixés avant l'audit ; aucun nouvel essai compté.
# ==============================================================================
import numpy as np
import pandas as pd

import modele_horizon as mh

SEUIL_PLACEBO = 2.0             # |t| du placebo au-delà duquel une fuite est suspectée
FACTEUR_CONCENTRATION = 2.0     # IC des plus petites > 2 × IC global, alors que celui des plus grandes ≤ 0
AUC_MIN_SANS_2008 = 0.55
MOIS_PLACEBO_REGIME = 12


# ------------------------------------------------------------------------------
# Modèles de rendement (publié, ensemble, CNN)
# ------------------------------------------------------------------------------
def ic_par_groupes(t: pd.DataFrame) -> dict:
    """IC moyen (prévision contre rendement relatif réalisé) par secteur, quintile de taille, de bêta, de volatilité, année."""
    groupes = {}
    if "secteur" in t:
        groupes["secteur"] = t["secteur"]
    for nom, col in [("taille", "liquidite"), ("beta", "beta_1a"), ("volatilite_passee", "vol_3m")]:
        if col in t:
            groupes[nom] = pd.qcut(t[col], 5, labels=["1 (bas)", "2", "3", "4", "5 (haut)"], duplicates="drop")
    groupes["annee"] = pd.DatetimeIndex(t["date"]).year
    out = {}
    for nom, cle in groupes.items():
        out[nom] = {}
        for val, g in t.groupby(cle, observed=True):
            ic = mh._ic_par_date(g, "pred")
            if len(ic) >= 3:
                out[nom][str(val)] = {"ic": float(ic.mean()), "n_dates": int(len(ic))}
    return out


def alerte_concentration(groupes: dict, ic_global: float | None) -> bool:
    """Règle D : le signal ne vient que des plus petites capitalisations (les plus touchées par le biais du survivant)."""
    taille = groupes.get("taille", {})
    petites, grandes = taille.get("1 (bas)", {}).get("ic"), taille.get("5 (haut)", {}).get("ic")
    if ic_global is None or petites is None or grandes is None or ic_global <= 0:
        return False
    return bool(petites > FACTEUR_CONCENTRATION * ic_global and grandes <= 0)


def verdict_rendement(ic, t, n_eff, n_essais: int) -> tuple[str, float]:
    """Mêmes règles que `experiences.verdict_labo` : IC > 3 %, ≥ 8 périodes, t > seuil corrigé pour `n_essais`."""
    seuil = mh.seuil_t(n_eff, n_candidats=max(1, n_essais))
    ok = ic is not None and ic > 0.03 and (n_eff or 0) >= mh.MIN_PERIODES_SIGNAL and (t or 0) > seuil
    return ("probant" if ok else "non probant"), seuil


def bilan_rendement(ev: dict, ev_placebo: dict | None, avant: dict | None,
                    n_essais_ancien: int, n_essais_nouveau: int) -> dict:
    """Constats A à D pour un modèle de rendement à un horizon. `ev` doit contenir `_tests` (evaluer(..., garder_tests=True))."""
    t = ev.pop("_tests", None)
    ic, ts, n_eff = ev.get("ic_moyen"), ev.get("t_stat"), ev.get("n_effectif")
    v_ancien, s_ancien = verdict_rendement(ic, ts, n_eff, n_essais_ancien)
    v_nouveau, s_nouveau = verdict_rendement(ic, ts, n_eff, n_essais_nouveau)
    groupes = ic_par_groupes(t) if t is not None and not t.empty else {}
    out = {
        "ic": ic, "t": ts, "n_effectif": n_eff, "ic_momentum": ev.get("ic_momentum"),
        "spread_quintiles": ev.get("spread_quintiles"), "titres_par_date": ev.get("titres_par_date"),
        "verdict_comptage_ancien": v_ancien, "seuil_comptage_ancien": s_ancien, "n_essais_ancien": n_essais_ancien,
        "verdict": v_nouveau, "seuil": s_nouveau, "n_essais": n_essais_nouveau,
        "groupes": groupes, "signal_concentre": alerte_concentration(groupes, ic),
        "controles": ev.get("controles"), "fenetres": ev.get("fenetres"),
        "avant": avant,
    }
    if ev_placebo:
        ev_placebo.pop("_tests", None)
        tp = ev_placebo.get("t_stat")
        out["placebo"] = {"ic": ev_placebo.get("ic_moyen"), "t": tp,
                          "fuite_suspectee": bool(tp is not None and abs(tp) >= SEUIL_PLACEBO)}
    if avant:
        out["verdict_change"] = bool(avant.get("verdict") and avant["verdict"] != v_nouveau)
    return out


def verdict_audit_rendement(b: dict) -> str:
    morceaux = [b["verdict"]]
    if b.get("placebo", {}).get("fuite_suspectee"):
        morceaux.append("FUITE SUSPECTÉE (placebo)")
    if b.get("signal_concentre"):
        morceaux.append("signal concentré sur les petites")
    if b.get("verdict_change"):
        morceaux.append(f"verdict changé (avant : {b['avant']['verdict']})")
    return " ; ".join(morceaux)


# ------------------------------------------------------------------------------
# Régime de marché
# ------------------------------------------------------------------------------
def decaler_regime(m: pd.DataFrame, mois: int = MOIS_PLACEBO_REGIME) -> pd.DataFrame:
    """Placebo (règle C) : les indicateurs d'il y a `mois` mois, la cible du mois réel."""
    import modele_regime as mreg
    out = m.copy()
    out[mreg.FEATURES] = out[mreg.FEATURES].shift(mois)
    return out.dropna(subset=mreg.FEATURES)


def calibration_regime(t: pd.DataFrame) -> dict:
    """Constats E : Brier contre le taux de base, fréquence observée par quintile de probabilité, AUC sans 2008-2009."""
    import modele_regime as mreg
    y, p, base = t["y"].values.astype(int), t["p"].values, t["base"].values
    brier, brier_base = float(np.mean((p - y) ** 2)), float(np.mean((base - y) ** 2))
    q = pd.qcut(pd.Series(p, index=t.index).rank(method="first"), 5, labels=False)
    fiabilite = [{"quintile": int(k) + 1, "p_moyenne": float(g["p"].mean()), "frequence": float(g["y"].mean()), "n": int(len(g))}
                 for k, g in t.groupby(q)]
    hors = t[(t.index < "2008-01-01") | (t.index > "2009-12-31")]
    auc_sans = mreg._auc(hors["y"].values.astype(int), hors["p"].values) if len(hors) else float("nan")
    return {"brier": brier, "brier_taux_base": brier_base, "gain_brier": brier_base - brier,
            "fiabilite": fiabilite, "auc_sans_2008": auc_sans,
            "alerte_une_seule_crise": bool(np.isfinite(auc_sans) and auc_sans < AUC_MIN_SANS_2008)}


def bilan_regime(ev: dict, ev_placebo: dict, avant: dict | None, n_essais: int) -> dict:
    t = ev.pop("_tests")
    ev_placebo.pop("_tests", None)
    seuil = mh.seuil_t(ev.get("n_effectif"), n_candidats=max(1, n_essais))
    ok = (ev.get("auc", 0) > 0.6 and ev.get("gain_logloss", 0) > 0
          and ev.get("n_effectif", 0) >= mh.MIN_PERIODES_SIGNAL and ev.get("t_stat", 0) > seuil)
    tp = ev_placebo.get("t_stat")
    out = {"auc": ev.get("auc"), "gain_logloss": ev.get("gain_logloss"), "t": ev.get("t_stat"), "seuil": seuil,
           "n_effectif": ev.get("n_effectif"), "taux_base": ev.get("taux_base"), "decennies": ev.get("decennies"),
           "verdict": "probant" if ok else "non probant",
           "placebo": {"auc": ev_placebo.get("auc"), "gain_logloss": ev_placebo.get("gain_logloss"), "t": tp,
                       "fuite_suspectee": bool(tp is not None and tp >= SEUIL_PLACEBO)},
           "calibration": calibration_regime(t), "avant": avant}
    if avant:
        out["verdict_change"] = bool(avant.get("verdict") and avant["verdict"] != out["verdict"])
    return out


def verdict_audit_regime(b: dict) -> str:
    morceaux = [b["verdict"]]
    if b["placebo"]["fuite_suspectee"]:
        morceaux.append("FUITE SUSPECTÉE (placebo)")
    if b["calibration"]["alerte_une_seule_crise"]:
        morceaux.append("repose sur 2008")
    if b.get("verdict_change"):
        morceaux.append(f"verdict changé (avant : {b['avant']['verdict']})")
    return " ; ".join(morceaux)
