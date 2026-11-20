"""Inférence des essais : EWC, Holm, maximum attendu, puissance."""
import numpy as np
import inference as inf


def test_ewc_dimensionne_sous_chevauchement():
    """Sous la nulle avec chevauchement de 25 dates, le rejet à 5 % doit rester proche de 5 % (et bien moins sur-rejeter que l'iid)."""
    from scipy import stats
    rng = np.random.default_rng(0)
    T, h, n, rej_ewc, rej_iid = 600, 25, 300, 0, 0
    nu = inf.nu_ewc(T, h)
    for _ in range(n):
        d = np.convolve(rng.normal(size=T + h), np.ones(h) / np.sqrt(h), "valid")[:T]
        om = inf.variance_long_terme_ewc(d, nu)
        rej_ewc += abs(d.mean() / np.sqrt(om / T)) > stats.t.ppf(0.975, nu)
        rej_iid += abs(d.mean() / (d.std(ddof=1) / np.sqrt(T))) > 1.96
    assert rej_ewc / n < 0.10 and rej_iid / n > 0.40


def test_rapport_detecte_un_vrai_ecart_et_donne_un_mde():
    rng = np.random.default_rng(1)
    d = rng.normal(-0.5, 1.0, 400)
    r = inf.rapport_dm(d, 5)
    assert r["t"] < -3 and r["p_unilateral_A_meilleur"] < 0.01 and r["mde_80"] > 0 and r["ic95"][1] < 0


def test_holm_au_moins_aussi_puissant_que_bonferroni():
    p = {"a": 0.004, "b": 0.011, "c": 0.02, "d": 0.4}
    h = inf.holm(p)
    bonf = {k for k, v in p.items() if v <= 0.05 / len(p)}
    assert bonf <= {k for k, v in h.items() if v["rejete"]}


def test_t_max_attendu_croit_avec_le_nombre_d_essais():
    assert inf.t_max_attendu(1) == 0 < inf.t_max_attendu(5) < inf.t_max_attendu(50)
