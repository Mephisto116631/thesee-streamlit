# modele_cnn.py
# ==============================================================================
# ALGORITHME 4 — CNN 1D SUR LES COURBES DE COURS
# Un petit réseau convolutif (CNN, « Convolutional Neural Network ») lit la forme
# de la dernière année de chaque titre et classe les titres comme les autres essais
# (cible : rang de l'alpha sectoriel). Protocole identique : walk-forward avec
# embargo, membres du S&P 500 à chaque date, seuil corrigé du nombre d'essais.
#
# Entrée par (date, titre), 252 jours sur 2 canaux :
#   1. rendement quotidien en excès du S&P 500, divisé par la volatilité 1 an du titre ;
#   2. log du volume par rapport à sa moyenne 1 an.
# Un CNN n'est pas explicatif en soi : on corrèle son score avec les facteurs connus
# (momentum, volatilité…) pour dire ce qu'il a appris (mh.sens_facteurs).
# ==============================================================================
import numpy as np
import pandas as pd

import modele_horizon as mh

SEQ = 252                # jours de bourse lus par le réseau
PAS_DATES = 4            # une date d'échantillon sur 4 (toutes les 4 semaines) : mémoire raisonnable
EPOQUES = 3
REGISTRE: dict[str, np.ndarray] = {}   # courbes, indexées par la colonne « cle » des données


class CNN:
    """Interface fit/predict compatible avec mh.evaluer ; X ne contient que la colonne « cle »."""
    feature_importances_ = np.array([1.0])

    def __init__(self, epoques: int = EPOQUES, graine: int = 42):
        import torch
        from torch import nn
        torch.manual_seed(graine)
        torch.set_num_threads(4)
        self.torch = torch
        self.epoques = epoques
        self.reseau = nn.Sequential(
            nn.Conv1d(2, 16, 5), nn.ReLU(), nn.MaxPool1d(2),
            nn.Conv1d(16, 32, 5), nn.ReLU(), nn.AdaptiveAvgPool1d(1), nn.Flatten(), nn.Linear(32, 1))

    def _courbes(self, X: pd.DataFrame):
        return self.torch.from_numpy(REGISTRE["courbes"][X["cle"].to_numpy().astype(int)])

    def fit(self, X: pd.DataFrame, y):
        torch = self.torch
        xs = self._courbes(X)
        ys = torch.tensor(np.asarray(y, dtype=np.float32) - 0.5).unsqueeze(1)
        opt = torch.optim.Adam(self.reseau.parameters(), lr=1e-3, weight_decay=1e-4)
        perte = torch.nn.MSELoss()
        gen = torch.Generator().manual_seed(0)
        self.reseau.train()
        for _ in range(self.epoques):
            ordre = torch.randperm(len(xs), generator=gen)
            for i in range(0, len(xs), 512):
                lot = ordre[i:i + 512]
                opt.zero_grad()
                perte(self.reseau(xs[lot]), ys[lot]).backward()
                opt.step()
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        xs = self._courbes(X)
        self.reseau.eval()
        with self.torch.no_grad():
            return np.concatenate([self.reseau(xs[i:i + 2048]).squeeze(1).numpy() for i in range(0, len(xs), 2048)])


def construire_courbes(market_raw: pd.DataFrame, symboles: list[str], data: pd.DataFrame) -> np.ndarray:
    """Tableau (lignes de data, 2 canaux, SEQ jours), sans information future (fenêtre finissant à la date)."""
    m = market_raw[market_raw["symbol"].isin(set(symboles) | {mh.INDICE})]
    px = m.pivot_table(index="date", columns="symbol", values="close").sort_index().ffill(limit=5)
    vol = m.pivot_table(index="date", columns="symbol", values="volume").sort_index().reindex(px.index)
    ret = px.pct_change()
    exc = ret.sub(ret[mh.INDICE], axis=0) if mh.INDICE in ret else ret
    sigma = ret.rolling(SEQ).std()
    lvol = np.log((vol / vol.rolling(SEQ).mean()).replace(0, np.nan))
    pos = {d: i for i, d in enumerate(px.index)}
    out = np.zeros((len(data), 2, SEQ), dtype=np.float32)
    for d, g in data.groupby("date"):
        i = pos.get(d)
        if i is None or i < SEQ:
            continue
        cols = [s for s in g["symbol"] if s in exc.columns]
        fen = exc.iloc[i - SEQ + 1:i + 1][cols] / sigma.iloc[i][cols]
        fv = lvol.iloc[i - SEQ + 1:i + 1][cols]
        rang = {s: k for k, s in enumerate(cols)}
        for ligne, s in zip(g.index, g["symbol"]):
            k = rang.get(s)
            if k is None:
                continue
            out[ligne, 0] = np.nan_to_num(fen.iloc[:, k].to_numpy(), nan=0.0).clip(-5, 5)
            out[ligne, 1] = np.nan_to_num(fv.iloc[:, k].to_numpy(), nan=0.0).clip(-3, 3)
    return out


def entrainer_cnn(market_raw: pd.DataFrame, symboles: list[str], nom: str,
                  composition: pd.DataFrame | None = None, secteurs: dict[str, str] | None = None,
                  cible_mode: str = "alpha_secteur", placebo: bool = False, garder_tests: bool = False,
                  couverture_min: float | None = None) -> dict:
    """Évalue le CNN avec le même protocole que les autres essais ; renvoie une ligne façon model_runs.
    Audits (METHODE § 4.27) : `placebo` mélange la cible entre titres ; `garder_tests` garde les prévisions de test."""
    h = mh.HORIZONS[nom]
    px, X = mh.caracteristiques(market_raw, symboles, secteurs)
    if X.empty:
        return {}
    if couverture_min is not None:
        X = mh.filtrer_couverture(X, market_raw, symboles, couverture_min)
    dates = np.sort(X["date"].unique())[::PAS_DATES]
    X = X[X["date"].isin(dates)]
    serie_m = market_raw[market_raw["symbol"] == mh.INDICE].set_index("date")["close"].sort_index()
    Y = mh.cible(px, pd.DatetimeIndex(dates), h, cible_mode, serie_m if not serie_m.empty else None, secteurs)
    data = X.merge(Y, on=["date", "symbol"]).dropna(subset=mh.FEATURES + ["y"])
    if composition is not None:
        filtre = mh.membres_a_date(data, composition, cible_mode == "alpha_secteur")
        if not filtre.empty:
            data = filtre
    data = data.reset_index(drop=True)
    if placebo:
        data = mh.melanger_cible(data)
    REGISTRE["courbes"] = construire_courbes(market_raw, symboles, data)
    data["cle"] = np.arange(len(data))
    ev = mh.evaluer(data, h, ["cle"], forcer_config="cnn", pas_jours=mh.PAS_ECHANTILLON * PAS_DATES, garder_tests=garder_tests)
    if not ev:
        return {}
    ev["cible"] = cible_mode
    ev["config"] = "cnn"
    ev["n_courbes"] = int(len(data))
    return {"kind": f"cnn_{nom}", "verdict": mh.verdict(ev.get("ic_moyen"), ev.get("t_stat"), ev.get("n_effectif")),
            "diagnostics": ev, "importance": [{"feature": "cle", "label": "Forme de la courbe (CNN)", "importance": 1.0}]}
