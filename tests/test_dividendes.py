"""Rentabilités dividendes compris (docs/METHODE.md § 4.28)."""
import numpy as np
import pandas as pd
import pytest

import modele_horizon as mh
import portefeuille as pf


def _brut(jours=400):
    """DIV : cours coté plat, mais 4 % de dividende par an (cours ajusté qui monte) ; SANS : ni l'un ni l'autre."""
    dates = pd.bdate_range("2020-01-01", periods=jours)
    ajuste = 100 * (1.04 ** (np.arange(jours) / 252))
    lignes = []
    for i, d in enumerate(dates):
        lignes.append({"symbol": "DIV", "date": d, "close": 100.0, "adj_close": ajuste[i] / ajuste[-1] * 100, "volume": 1})
        lignes.append({"symbol": "SANS", "date": d, "close": 50.0, "adj_close": 50.0, "volume": 1})
    return pd.DataFrame(lignes)


def test_cours_ajustes_et_replis():
    raw = _brut()
    px = mh.cours_ajustes(raw)
    assert px["DIV"].iloc[-1] / px["DIV"].iloc[0] - 1 == pytest.approx(1.04 ** (399 / 252) - 1, rel=1e-6)
    sans_col = mh.cours_ajustes(raw.drop(columns="adj_close"))
    assert (sans_col["DIV"] == 100.0).all()                                   # pas de colonne : cours de clôture
    raw.loc[raw["symbol"] == "SANS", "adj_close"] = np.nan
    assert (mh.cours_ajustes(raw)["SANS"] == 50.0).all()                      # titre sans cours ajusté : clôture


def test_cible_compte_les_dividendes():
    raw = _brut()
    px = mh.cours_ajustes(raw)
    dates = px.index[:100]
    y = mh.cible(px, dates, 126)
    div = y[y["symbol"] == "DIV"]["brut"].dropna()
    assert div.mean() == pytest.approx(1.04 ** (126 / 252) - 1, rel=1e-3)   # ≈ +2 % en 6 mois, le cours coté est plat
    assert (y[y["symbol"] == "DIV"]["rel"].dropna() > 0).all()               # il ne « sous-performe » plus SANS


def test_rendements_du_portefeuille_dividendes_compris():
    R = pf._matrice_rendements(_brut(), ["DIV", "SANS"], jours=252)
    assert R["DIV"].mean() * 252 == pytest.approx(np.log(1.04), rel=0.05)
    assert R["SANS"].abs().max() == 0


# --- § 4.29 : re-test aligné, rendement hebdomadaire, CNN et régime en sommeil ------------------------------
def test_cnn_et_regime_en_sommeil_par_defaut():
    import experiences
    tous = experiences.choisir_experiences("toutes")
    assert "cnn" not in tous and "regime_logistique" not in tous and "audit_cnn" not in tous
    assert "risque_volatilite" in tous and "reference" in tous
    assert experiences.choisir_experiences("cnn,regime_xgboost") == ["cnn", "regime_xgboost"]   # nommés : lancés
    with pytest.raises(ValueError):
        experiences.choisir_experiences("inconnu")


def test_modeles_de_rendement_hebdomadaires(monkeypatch):
    import publish

    class Requete:
        def __init__(self, data): self.data = data
        def select(self, *a): return self
        def eq(self, *a): return self
        def limit(self, *a): return self
        def execute(self): return self

    class Client:
        def __init__(self, il_y_a): self.d = [{"trained_at": (pd.Timestamp.now(tz="UTC") - il_y_a).isoformat()}]
        def table(self, nom): return Requete(self.d)

    monkeypatch.delenv("SEC_FORCER", raising=False)
    monkeypatch.setattr(publish.db, "get_client", lambda: Client(pd.Timedelta(days=2)))
    assert publish.modeles_rendement_a_jour()
    monkeypatch.setattr(publish.db, "get_client", lambda: Client(pd.Timedelta(days=8)))
    assert not publish.modeles_rendement_a_jour()
    monkeypatch.setattr(publish.db, "get_client", lambda: Client(pd.Timedelta(days=2)))
    monkeypatch.setenv("SEC_FORCER", "1")
    assert not publish.modeles_rendement_a_jour()                            # lancement forcé : réentraînement
