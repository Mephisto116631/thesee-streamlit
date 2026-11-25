"""Garde-fous ajoutés après la revue de code de novembre 2026 (docs/REVUE_2026-11.md) :
échecs non bloquants remontés, suppression massive de titres refusée, versions des bibliothèques
enregistrées avec chaque essai, même optimiseur que l'appli (fixture partagée)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import cron_sync
import experiences
import fred
import modele_horizon as mh
import portefeuille as pf
import publish

FIXTURE = Path(__file__).resolve().parent.parent / "mobile" / "src" / "fixtures" / "univers-test.json"


# --- 1. Échecs non bloquants : le passage est « partiel », pas « success » -----------------------------
def test_avertir_collecte_et_statut_partiel(capsys):
    publish.AVERTISSEMENTS.clear()
    publish.avertir("Volatilité IA non calculée : boom")
    assert publish.AVERTISSEMENTS == ["Volatilité IA non calculée : boom"]
    assert "[PUBLISH][WARN]" in capsys.readouterr().out

    statut, msg = cron_sync.statut_passage(500, {"avertissements": list(publish.AVERTISSEMENTS)}, 120)
    assert statut == "partiel"
    assert "1 avertissement(s)" in msg and "boom" in msg
    publish.AVERTISSEMENTS.clear()


def test_statut_success_sans_avertissement():
    assert cron_sync.statut_passage(500, {"portefeuille": 9, "avertissements": []}, 120) == \
        ("success", "500 tickers, 9 lignes de portefeuille, 120s")
    assert cron_sync.statut_passage(500, {}, 1)[0] == "success"   # résumé sans la clé


# --- 2. Suppression des titres sortis de l'univers ------------------------------------------------------
def test_retire_les_quelques_titres_sortis():
    existants = [f"T{i:03d}" for i in range(500)]
    garder = existants[:-3] + ["NEW"]
    assert publish.titres_a_retirer(existants, garder) == ["T497", "T498", "T499"]


def test_refuse_une_suppression_massive():
    existants = [f"T{i:03d}" for i in range(500)]
    with pytest.raises(ValueError):
        publish.titres_a_retirer(existants, existants[:300])      # un lot Yahoo perdu : 200 titres manquants
    with pytest.raises(ValueError):
        publish.titres_a_retirer(existants, [])                   # snapshot vide


def test_petite_base_tolere_dix_retraits():
    existants = [f"T{i}" for i in range(20)]
    assert len(publish.titres_a_retirer(existants, existants[:10])) == 10


# --- 3. Versions des bibliothèques enregistrées avec chaque essai -----------------------------------------
class _Table:
    def __init__(self, journal):
        self.journal = journal

    def insert(self, ligne):
        self.journal.append(ligne)
        return self

    def execute(self):
        return self


class _Client:
    def __init__(self):
        self.lignes = []

    def table(self, nom):
        assert nom == "experiences"
        return _Table(self.lignes)


def test_versions_enregistrees_dans_les_diagnostics():
    cli = _Client()
    experiences._ecrire(cli, {"nom": "essai", "verdict": "x", "diagnostics": {"ic": np.float64(0.1)}})
    diag = cli.lignes[0]["diagnostics"]
    assert diag["ic"] == pytest.approx(0.1)
    assert diag["versions"]["numpy"] == np.__version__
    assert diag["versions"]["pandas"] == pd.__version__
    assert diag["versions"]["python"].count(".") == 2
    experiences._ecrire(cli, {"nom": "sans_diag", "verdict": "x"})
    assert "versions" in cli.lignes[1]["diagnostics"]


# --- 7. Même optimiseur que l'appli : la fixture partagée est relue côté Python -------------------------
def test_frontiere_identique_a_la_fixture_de_l_appli():
    fx = json.loads(FIXTURE.read_text())
    u, h, srv = fx["univers"], fx["hypotheses"], fx["serveur"]
    assert h["tauxSansRisque"] == pf.RF and h["primeRisque"] == pf.PRIME_RISQUE
    assert h["poidsHistorique"] == pf.POIDS_HISTORIQUE and h["poidsMax"] == pf.POIDS_MAX
    assert h["nMaxLignes"] == pf.N_MAX_LIGNES and h["poidsMin"] == pf.POIDS_MIN
    B, D = np.array(u["facteurs"]), np.array(u["idio"])
    mu = (1 - pf.POIDS_HISTORIQUE) * (pf.RF + np.array(u["beta"]) * pf.PRIME_RISQUE) + pf.POIDS_HISTORIQUE * np.array(u["mu_hist"])
    pts = pf.frontiere_lambdas(B, D, mu)
    assert len(pts) == len(srv)
    for p, s in zip(pts, srv):
        assert p["rendement"] == pytest.approx(s["rendement"], abs=1e-6)
        assert p["volatilite"] == pytest.approx(s["volatilite"], abs=1e-6)


# --- 8. Corrélation de rang sans avertissement de NumPy ---------------------------------------------------
def test_spearman_constante_donne_nan_sans_avertissement():
    import warnings
    x = pd.Series(np.arange(20, dtype=float))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert np.isnan(mh._spearman(x, pd.Series([1.0] * 20)))
    assert mh._spearman(x, x * 2) == pytest.approx(1.0)
    assert mh._spearman(x, -x) == pytest.approx(-1.0)


# --- Registre des examens du laboratoire ------------------------------------------------------------------
def test_chaque_examen_a_sa_fonction():
    assert set(experiences.EXAMENS) == set(experiences.EXPERIENCES_EXAMEN)
    besoin_t = {n for n, (_, b) in experiences.EXAMENS.items() if b}
    assert besoin_t == {"examen_references", "examen_calibration", "examen_crises", "examen_hybride", "examen_ia_contre_har",
                        "examen_audit_biais", "examen_har_relatif", "examen_ia_informee",
                        "examen_har_protege", "examen_ia_climat"}
    assert all(callable(f) for f, _ in experiences.EXAMENS.values())


# --- Taux sans risque lu sur le marché (docs/METHODE.md § 2.1) -------------------------------------------
def _serie(valeurs, fin="2026-11-20"):
    dates = pd.bdate_range(end=fin, periods=len(valeurs))
    return pd.DataFrame({"date": dates, "valeur": valeurs})


def test_choisir_taux_derniere_valeur_plausible_et_recente():
    assert fred.choisir_taux(_serie([3.9, 3.8, 3.72]), "2026-11-24") == (pytest.approx(0.0372), "2026-11-20")
    assert fred.choisir_taux(_serie([3.9, np.nan]).dropna(), "2026-11-24")[0] == pytest.approx(0.039)
    assert fred.choisir_taux(_serie([3.7], fin="2026-10-01"), "2026-11-24") is None      # trop ancienne
    assert fred.choisir_taux(_serie([45.0]), "2026-11-24") is None                       # invraisemblable
    assert fred.choisir_taux(pd.DataFrame(columns=["date", "valeur"]), "2026-11-24") is None


def test_taux_du_jour_repli_et_avertissement(monkeypatch):
    publish.AVERTISSEMENTS.clear()
    monkeypatch.setattr(fred, "taux_sans_risque", lambda: (0.0372, "2026-11-20"))
    assert publish.taux_du_jour() == (0.0372, "2026-11-20") and not publish.AVERTISSEMENTS

    def panne():
        raise RuntimeError("FRED_API_KEY manquante")
    monkeypatch.setattr(fred, "taux_sans_risque", panne)
    assert publish.taux_du_jour() == (pf.RF, None)
    assert len(publish.AVERTISSEMENTS) == 1 and "repli" in publish.AVERTISSEMENTS[0]
    publish.AVERTISSEMENTS.clear()


def test_le_taux_decale_les_rendements_sans_changer_les_poids_a_lambda_donne():
    fx = json.loads(FIXTURE.read_text())
    u = fx["univers"]
    B, D = np.array(u["facteurs"]), np.array(u["idio"])
    beta, mh_ = np.array(u["beta"]), np.array(u["mu_hist"])
    mu = lambda rf: (1 - pf.POIDS_HISTORIQUE) * (rf + beta * pf.PRIME_RISQUE) + pf.POIDS_HISTORIQUE * mh_  # noqa: E731
    w_a = pf.resoudre(B, D, mu(0.0435), 0.05, pf.POIDS_MAX)
    w_b = pf.resoudre(B, D, mu(0.02), 0.05, pf.POIDS_MAX)
    np.testing.assert_allclose(w_a, w_b, atol=1e-9)
    hauts = pf.frontiere_lambdas(B, D, mu(0.0435), rf=0.0435)
    bas = pf.frontiere_lambdas(B, D, mu(0.02), rf=0.02)
    assert bas[-1]["rendement"] == pytest.approx(hauts[-1]["rendement"] - 0.9 * 0.0235, abs=1e-6)
