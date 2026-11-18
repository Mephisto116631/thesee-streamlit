"""Construit data/sp500_historique.csv : périodes d'appartenance de chaque titre au S&P 500.

Source : https://github.com/fja05680/sp500 (licence MIT), fichier
« S&P 500 Historical Components & Changes (Updated).csv » : une ligne par date
de changement avec la liste complète des membres. On le résume en intervalles
(symbole, debut, fin), fin vide = toujours membre à la dernière date du fichier.
Symboles au format Yahoo (BRK.B -> BRK-B). À relancer de temps en temps :
    python outils/composition_sp500.py
"""
import sys
from pathlib import Path

import pandas as pd

SOURCE = ("https://raw.githubusercontent.com/fja05680/sp500/master/"
          "S%26P%20500%20Historical%20Components%20%26%20Changes%20(Updated).csv")
SORTIE = Path(__file__).resolve().parent.parent / "data" / "sp500_historique.csv"


def intervalles(comp: pd.DataFrame) -> pd.DataFrame:
    comp = comp.assign(date=pd.to_datetime(comp["date"])).sort_values("date").reset_index(drop=True)
    ouverts: dict[str, pd.Timestamp] = {}
    lignes = []
    for d, tickers in zip(comp["date"], comp["tickers"]):
        membres = {t.strip().replace(".", "-") for t in str(tickers).split(",") if t.strip()}
        for s in list(ouverts):
            if s not in membres:
                lignes.append((s, ouverts.pop(s), d))      # sorti à cette date
        for s in membres - ouverts.keys():
            ouverts[s] = d
    lignes += [(s, debut, pd.NaT) for s, debut in ouverts.items()]
    out = pd.DataFrame(lignes, columns=["symbol", "debut", "fin"]).sort_values(["symbol", "debut"])
    out["debut"] = out["debut"].dt.date
    out["fin"] = out["fin"].dt.date
    return out


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else SOURCE
    out = intervalles(pd.read_csv(src))
    out.to_csv(SORTIE, index=False)
    print(f"{len(out)} périodes, {out['symbol'].nunique()} titres -> {SORTIE}")
