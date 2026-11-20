# inference.py
# ==============================================================================
# INFÉRENCE POUR LES ESSAIS DE LABORATOIRE (règles v2 : docs/METHODE.md § 4.12)
# Écart de perte d_t entre deux méthodes, une valeur par date (déjà moyennée sur les titres :
# c'est l'estimateur de type Driscoll-Kraay, la dépendance transversale est absorbée).
#   - variance de long terme par EWC (Lazarus, Lewis, Stock & Watson 2018), loi t à ν degrés de liberté
#   - n effectif, écart minimal détectable (MDE), intervalle de confiance
#   - Holm (1979) ; maximum attendu de t sous la nulle pour N essais (Bailey & López de Prado 2014)
# ==============================================================================
import numpy as np
from scipy import stats

PUISSANCE = 0.80
ALPHA = 0.05


def nu_ewc(T: int, h_dates: float) -> int:
    """Degrés de liberté EWC : 0,4·T^(2/3) (Lazarus et al.), plafonné à T/(2h) (chevauchement, règle heuristique § 3.1)."""
    return int(max(2, min(np.floor(0.4 * T ** (2 / 3)), np.floor(T / (2 * max(h_dates, 1.0))))))


def variance_long_terme_ewc(d: np.ndarray, nu: int) -> float:
    """Ω̂ = (1/ν) Σ_j Λ_j², Λ_j = T^(-1/2) Σ_t √2 cos(π j (t−½)/T) (d_t − d̄)."""
    d = np.asarray(d, float)
    T = len(d)
    e = d - d.mean()
    t = np.arange(1, T + 1)
    lam = np.array([np.sqrt(2.0) * np.sum(np.cos(np.pi * j * (t - 0.5) / T) * e) / np.sqrt(T) for j in range(1, nu + 1)])
    return float(np.mean(lam ** 2))


def rapport_dm(d, h_dates: float, alpha: float = ALPHA) -> dict:
    """Rapport complet d'un écart de perte moyen (d < 0 : la méthode A est meilleure que B si d = perte_A − perte_B)."""
    d = np.asarray(d, float)
    d = d[np.isfinite(d)]
    T = len(d)
    if T < 30:
        return {"n_dates": T}
    nu = nu_ewc(T, h_dates)
    om = variance_long_terme_ewc(d, nu)
    se = float(np.sqrt(max(om, 1e-18) / T))
    m = float(d.mean())
    t_obs = m / se
    tcrit = float(stats.t.ppf(1 - alpha / 2, nu))
    mde = float((tcrit + stats.t.ppf(PUISSANCE, nu)) * se)
    return {
        "n_dates": T, "ecart": m, "erreur_type": se, "t": float(t_obs), "nu": nu,
        "p_bilatere": float(2 * (1 - stats.t.cdf(abs(t_obs), nu))), "p_unilateral_A_meilleur": float(stats.t.cdf(t_obs, nu)),
        "ic95": [m - tcrit * se, m + tcrit * se],
        "n_effectif": float(T * d.var(ddof=1) / max(om, 1e-18)),
        "mde_80": mde, "ecart_sur_mde": float(abs(m) / mde) if mde > 0 else None,
    }


def holm(p: dict[str, float], alpha: float = ALPHA) -> dict[str, dict]:
    """Holm (1979) : rejets pas-à-pas, même contrôle du FWER que Bonferroni, jamais moins puissant."""
    ordre = sorted(p, key=p.get)
    m, rejet, bloque = len(ordre), {}, False
    for i, k in enumerate(ordre):
        seuil = alpha / (m - i)
        ok = (not bloque) and p[k] <= seuil
        bloque = bloque or not ok
        rejet[k] = {"p": p[k], "seuil_holm": seuil, "rejete": bool(ok)}
    return rejet


def t_max_attendu(n_essais: int) -> float:
    """E[max] de N statistiques normales indépendantes sous la nulle (Bailey & López de Prado 2014)."""
    if n_essais <= 1:
        return 0.0
    g = 0.5772156649
    return float((1 - g) * stats.norm.ppf(1 - 1 / n_essais) + g * stats.norm.ppf(1 - 1 / (n_essais * np.e)))
