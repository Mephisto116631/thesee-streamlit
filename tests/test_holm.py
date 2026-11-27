"""Correction de Holm dans les familles « rendement » et « risque » (docs/METHODE.md § 4.32)."""
import pytest

import experiences
import modele_horizon as mh

# Derniers résultats réels de la famille « risque » (§ 27) : (t, périodes indépendantes)
RISQUE = {("vol", "6m"): (7.34, 27.2), ("vol_comptes", "6m"): (6.48, 27.1), ("vol", "1a"): (3.65, 13.3),
          ("vol_comptes", "1a"): (3.06, 13.3), ("pmax_comptes", "6m"): (2.40, 27.1), ("pmax", "6m"): (2.26, 27.1),
          ("pmax_comptes", "1a"): (0.75, 13.3), ("pmax", "1a"): (0.10, 13.3)}


def test_holm_reproduit_le_constat_du_paragraphe_27():
    h = mh.seuils_holm(RISQUE, 8)
    signif = {c for c, r in h.items() if r["significatif"]}
    assert signif == {("vol", "6m"), ("vol_comptes", "6m"), ("vol", "1a"), ("vol_comptes", "1a")}
    # Bonferroni n'acceptait pas la 4e : t = 3,06 < 3,29 ; Holm : seuil 3,04
    r = h[("vol_comptes", "1a")]
    assert r["rang"] == 4 and r["seuil"] == pytest.approx(3.04, abs=0.01) and r["seuil_bonferroni"] == pytest.approx(3.29, abs=0.01)


def test_holm_jamais_plus_severe_que_bonferroni_et_premier_rang_identique():
    h = mh.seuils_holm(RISQUE, 8)
    assert all(r["seuil"] <= r["seuil_bonferroni"] + 1e-12 for r in h.values())
    premier = min(h.values(), key=lambda r: r["rang"])
    assert premier["seuil"] == pytest.approx(premier["seuil_bonferroni"])


def test_holm_s_arrete_au_premier_echec():
    # Le 2e échoue ; le 3e dépasse son propre seuil (n − 2) mais reste non significatif
    e = {"a": (8.0, 27), "b": (2.0, 27), "c": (2.05, 200)}
    h = mh.seuils_holm(e, 3)
    assert h["a"]["significatif"] and not h["b"]["significatif"]
    ordre = sorted(h, key=lambda c: h[c]["rang"])
    dernier = ordre[-1]
    assert not h[dernier]["significatif"]


def test_holm_contamine_et_sans_t_comptent_mais_ne_passent_jamais():
    e = {"contamine": (7.65, 27.2), "bon": (3.4, 27.2), "vide": (None, None)}
    h = mh.seuils_holm(e, 17, exclus={"contamine"})
    assert not h["contamine"]["significatif"] and not h["vide"]["significatif"]
    # Le contaminé ne fait pas baisser le seuil : le meilleur vrai essai est jugé au premier rang (17 essais)
    assert h["bon"]["rang"] == 1 and h["bon"]["seuil"] == pytest.approx(mh.seuil_t(27.2, 17))
    assert h["bon"]["significatif"]                      # 3,4 > 3,28
    assert all(r["n_essais"] == 17 for r in h.values())


def test_l_ordre_de_passage_ne_compte_pas():
    a = mh.seuils_holm(dict(RISQUE), 8)
    b = mh.seuils_holm(dict(reversed(list(RISQUE.items()))), 8)
    assert a == b


# --- Rejugement d'une famille au laboratoire ------------------------------------------------------------------
class _Requete:
    def __init__(self, base, journal):
        self.base, self.journal = base, journal

    def select(self, *_):
        return self

    def in_(self, _col, noms):
        self.noms = set(noms)
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    def insert(self, ligne):
        self.journal.append(ligne)
        return self

    def execute(self):
        class R:
            pass
        r = R()
        r.data = [x for x in self.base if x["nom"] in getattr(self, "noms", set())]
        return r


class _Client:
    def __init__(self, base):
        self.base, self.ecrits = base, []

    def table(self, nom):
        assert nom == "experiences"
        return _Requete(self.base, self.ecrits)


def test_juger_famille_utilise_les_essais_non_relances():
    # En base : un vieil essai très fort (non relancé) ; ce passage : un essai à t = 3,1 (n_eff 27)
    base = [{"id": 2, "nom": "risque_perte_max", "horizon": "6m", "t_stat": 9.0, "n_effectif": 27.0},
            {"id": 1, "nom": "risque_perte_max", "horizon": "6m", "t_stat": 0.1, "n_effectif": 27.0}]   # plus ancien : ignoré
    cli = _Client(base)
    d = {"gain": 0.04, "n_effectif": 27.0, "t_stat": 3.1, "ic_moyen": 0.8}
    attente = [{"cle": ("risque_volatilite", "6m"), "t": 3.1, "n_eff": 27.0,
                "ligne": {"lot": "x", "nom": "risque_volatilite", "horizon": "6m", "diagnostics": d},
                "juger": lambda hm: experiences.verdict_risque(d["gain"], d["n_effectif"], hm["significatif"])}]
    experiences.juger_famille(cli, attente, experiences.EXPERIENCES_RISQUE, 2)
    (ligne,) = cli.ecrits
    # Rang 2 sur 2 : seuil de Holm = seuil à 1 essai (2,06) < Bonferroni à 2 essais (2,37) -> probant
    assert ligne["diagnostics"]["holm"]["rang"] == 2
    assert ligne["seuil_t_global"] == pytest.approx(mh.seuil_t(27.0, 1))
    assert ligne["verdict"] == "probant" and ligne["n_essais"] == 2


def test_confirmation_midcap_declaree_contaminee():
    assert ("confirmation_ensemble_midcap", "6m") in experiences.CONTAMINES
    assert "confirmation_ensemble_midcap" in experiences.FAMILLE_RENDEMENT
    assert set(experiences.EXPERIENCES) <= experiences.FAMILLE_RENDEMENT
