"""CNN sur les courbes : il trouve une tendance plantée dans la forme des courbes, rien dans du bruit."""
import sys

import pytest

sys.path.insert(0, "tests")
torch = pytest.importorskip("torch", reason="PyTorch est installé par le workflow du laboratoire et des tests")

import modele_cnn as mc  # noqa: E402
from test_modele_horizon import _marche  # noqa: E402


def test_cnn_trouve_une_tendance():
    raw, syms = _marche(n=120, jours=1600, persistance=True, seed=2)
    ligne = mc.entrainer_cnn(raw, syms, "6m", cible_mode="relatif")
    d = ligne["diagnostics"]
    assert d["config"] == "cnn" and d["ic_moyen"] > 0.05
    assert "mom_12_1" in d["controles"]["facteurs"]          # ce que le CNN a appris est mesuré


def test_cnn_rien_dans_le_bruit():
    raw, syms = _marche(n=120, jours=1600, persistance=False, seed=3)
    ligne = mc.entrainer_cnn(raw, syms, "6m", cible_mode="relatif")
    assert abs(ligne["diagnostics"]["ic_moyen"]) < 0.06
