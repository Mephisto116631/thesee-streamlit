"""Garde-fous ajoutés après la revue de code de novembre 2026 (docs/REVUE_2026-11.md) :
échecs non bloquants remontés, suppression massive de titres refusée, versions des bibliothèques
enregistrées avec chaque essai, même optimiseur que l'appli (fixture partagée)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import _st_shim
sys.modules.setdefault("streamlit", _st_shim)

import cron_sync                  # noqa: E402
import experiences                # noqa: E402
import modele_horizon as mh       # noqa: E402
import portefeuille as pf         # noqa: E402
import publish                    # noqa: E402

FIXTURE = Path(__file__).resolve().parent.parent / "mobile" / "src" / "fixtures" / "univers-test.json"


# --- 1. Échecs non bloquants : le passage est « partiel », pas « success » -----------------------------
def test_avertir_collecte_et_statut_partiel(capsys):
    publish.AVERTISSEMENTS.clear()
    publish.avertir("Volatilité IA non calculée : boom")
    assert publish.AVERTISSEMENTS == ["Volatilité IA non calculée : boom"]
    assert "[PUBLISH][WARN]" in capsys.readouterr().out

    statut, msg = cron_sync.statut_passage(500, {"signaux": 0, "avertissements": list(publish.AVERTISSEMENTS)}, 120)
    assert statut == "partiel"
    assert "1 avertissement(s)" in msg and "boom" in msg
    publish.AVERTISSEMENTS.clear()


def test_statut_success_sans_avertissement():
    assert cron_sync.statut_passage(500, {"signaux": 0, "avertissements": []}, 120) == ("success", "500 tickers, 0 signaux, 120s")
    assert cron_sync.statut_passage(500, {"signaux": 3}, 1)[0] == "success"   # ancien résumé sans la clé


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
