# fondamentaux_sec.py
# ==============================================================================
# FONDAMENTAUX « POINT IN TIME » DEPUIS LA SEC (Securities and Exchange
# Commission, le gendarme de la Bourse américaine) — données XBRL gratuites.
#
# Chaque chiffre est daté de sa PUBLICATION (champ « filed ») : à une date donnée,
# le modèle ne voit que les comptes déjà publiés ce jour-là (pas de fuite du futur).
#
# La SEC exige un User-Agent avec un contact : secret GitHub SEC_USER_AGENT
# (« Nom adresse@exemple.com »). Il n'est envoyé qu'aux serveurs sec.gov.
#
# Facteurs calculés (documentés dans la littérature académique) :
#   fd_rentabilite     marge brute / actifs (Novy-Marx 2013)            ↑ mieux
#   fd_rendement_benef bénéfice net / capitalisation (valeur)            ↑ mieux
#   fd_valeur_comptable fonds propres / capitalisation (Fama-French)     ↑ mieux
#   fd_croissance_actifs croissance des actifs sur 1 an (Cooper et al.)  ↓ mieux
#   fd_emissions       variation du nombre d'actions sur 1 an            ↓ mieux
#   fd_accruals        (bénéfice − trésorerie d'exploitation) / actifs   ↓ mieux (Sloan 1996)
# ==============================================================================
import os
import time

import numpy as np
import pandas as pd
import requests

URL_TICKERS = "https://www.sec.gov/files/company_tickers.json"
URL_FAITS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
PAUSE = 0.12                      # la SEC limite à 10 requêtes par seconde
FORMULAIRES = {"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "40-F", "10-KT"}

# variable -> (balises par ordre de préférence, unité, type)
CONCEPTS = {
    "actifs": (["Assets"], "USD", "instant"),
    "fonds_propres": (["StockholdersEquity",
                       "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], "USD", "instant"),
    "resultat_net": (["NetIncomeLoss", "ProfitLoss"], "USD", "annuel"),
    "marge_brute": (["GrossProfit"], "USD", "annuel"),
    "chiffre_affaires": (["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                          "SalesRevenueNet"], "USD", "annuel"),
    "cout_ventes": (["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"], "USD", "annuel"),
    "flux_exploitation": (["NetCashProvidedByUsedInOperatingActivities"], "USD", "annuel"),
    "actions": (["dei:EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"], "shares", "instant"),
}
FEATURES_FD = ["fd_rentabilite", "fd_rendement_benef", "fd_valeur_comptable",
               "fd_croissance_actifs", "fd_emissions", "fd_accruals"]
LABELS_FD = {
    "fd_rentabilite": "Rentabilité brute (marge brute / actifs)",
    "fd_rendement_benef": "Rendement bénéficiaire (bénéfice / capitalisation)",
    "fd_valeur_comptable": "Valeur comptable / capitalisation",
    "fd_croissance_actifs": "Croissance des actifs sur 1 an",
    "fd_emissions": "Émissions d'actions sur 1 an",
    "fd_accruals": "Accruals (bénéfice non encaissé / actifs)",
}


def _get(url: str, ua: str):
    for essai in range(4):
        try:
            r = requests.get(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}, timeout=30)
            time.sleep(PAUSE)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
            time.sleep(2 ** essai)
        except requests.RequestException:
            time.sleep(2 ** essai)
    return None


def ciks(ua: str) -> dict[str, int]:
    """Ticker (format Yahoo, BRK-B) -> CIK (identifiant SEC de l'entreprise)."""
    data = _get(URL_TICKERS, ua) or {}
    return {str(v["ticker"]).upper().replace(".", "-"): int(v["cik_str"]) for v in data.values()}


def extraire(faits: dict, symbol: str) -> pd.DataFrame:
    """companyfacts JSON -> lignes (symbol, variable, end, filed, val), dédoublonnées :
    pour chaque période, la PREMIÈRE publication (pas les corrections ultérieures)."""
    lignes = []
    tout = (faits or {}).get("facts", {})
    for var, (balises, unite, genre) in CONCEPTS.items():
        for prio, balise in enumerate(balises):
            tax, nom = balise.split(":") if ":" in balise else ("us-gaap", balise)
            for e in tout.get(tax, {}).get(nom, {}).get("units", {}).get(unite, []):
                if e.get("form") not in FORMULAIRES or e.get("val") is None or not e.get("filed"):
                    continue
                if genre == "annuel":
                    if not e.get("start"):
                        continue
                    duree = (pd.Timestamp(e["end"]) - pd.Timestamp(e["start"])).days
                    if not 330 <= duree <= 400:
                        continue
                lignes.append((symbol, var, e["end"], e["filed"], float(e["val"]), prio))
    if not lignes:
        return pd.DataFrame(columns=["symbol", "variable", "end", "filed", "val"])
    df = pd.DataFrame(lignes, columns=["symbol", "variable", "end", "filed", "val", "prio"])
    df["end"] = pd.to_datetime(df["end"])
    df["filed"] = pd.to_datetime(df["filed"])
    df = df.sort_values(["variable", "end", "prio", "filed"]).drop_duplicates(["variable", "end"])
    return df.drop(columns="prio").reset_index(drop=True)


def telecharger(symboles: list[str], ua: str | None = None) -> pd.DataFrame:
    ua = ua or os.environ.get("SEC_USER_AGENT", "")
    if not ua.strip():
        raise RuntimeError("Secret SEC_USER_AGENT absent : la SEC refuse les requêtes anonymes.")
    table = ciks(ua)
    frames, manquants = [], []
    for s in symboles:
        cik = table.get(s.upper())
        if cik is None:
            manquants.append(s)
            continue
        frames.append(extraire(_get(URL_FAITS.format(cik=cik), ua), s))
    print(f"[SEC] {len(frames)} entreprises, {len(manquants)} sans CIK (ETF, titres étrangers…)")
    frames = [f for f in frames if not f.empty]
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["symbol", "variable", "end", "filed", "val"])
    # Types explicites : une concaténation avec des tables vides laisse des colonnes « object »
    out["end"] = pd.to_datetime(out["end"])
    out["filed"] = pd.to_datetime(out["filed"])
    out["val"] = pd.to_numeric(out["val"], errors="coerce")
    return out


def facteur_splits(splits: pd.DataFrame, dates: pd.DatetimeIndex, symboles: list[str]) -> pd.DataFrame:
    """Produit des divisions d'actions survenues APRÈS chaque date (dates × symboles).
    Les cours Yahoo sont ajustés des divisions : cours réel à la date = cours ajusté × ce facteur."""
    out = pd.DataFrame(1.0, index=dates, columns=symboles)
    if splits is None or splits.empty:
        return out
    for s, g in splits[splits["ratio"] > 0].groupby("symbol"):
        if s not in out.columns:
            continue
        for d, r in zip(g["date"], g["ratio"]):
            out.loc[out.index < d, s] *= r
    return out


def _dernier_connu(faits: pd.DataFrame, var: str) -> pd.DataFrame:
    """Valeurs publiées d'une variable, en ne gardant que les publications qui font avancer
    la période la plus récente (une correction d'un vieux bilan ne remplace pas le dernier)."""
    f = faits[faits["variable"] == var].sort_values(["symbol", "filed", "end"])
    f = f[f["end"] == f.groupby("symbol")["end"].cummax()]
    return f[["symbol", "end", "filed", "val"]]


def _croissance(faits: pd.DataFrame, var: str) -> pd.DataFrame:
    """Variation sur ~1 an : valeur / valeur de la période close ~12 mois plus tôt − 1."""
    f = _dernier_connu(faits, var).rename(columns={"val": "v"})
    tout = faits[faits["variable"] == var][["symbol", "end", "val"]].rename(columns={"end": "end_prec", "val": "v_prec"})
    f["symbol"] = f["symbol"].astype(str)
    tout["symbol"] = tout["symbol"].astype(str)
    f = f.assign(cle=f["end"] - pd.Timedelta(days=365)).sort_values("cle")
    tout = tout.sort_values("end_prec")
    m = pd.merge_asof(f, tout, left_on="cle", right_on="end_prec", by="symbol",
                      direction="nearest", tolerance=pd.Timedelta(days=45))
    m["croissance"] = m["v"] / m["v_prec"] - 1
    return m[["symbol", "end", "end_prec", "filed", "croissance"]]


def _asof(echantillon: pd.DataFrame, valeurs: pd.DataFrame, col: str, nom: str) -> pd.DataFrame:
    """Rattache à chaque (date, titre) la dernière valeur PUBLIÉE avant cette date."""
    v = valeurs.dropna(subset=[col]).sort_values("filed")[["symbol", "filed", col]].rename(columns={col: nom})
    v["symbol"] = v["symbol"].astype(str)
    e = echantillon.assign(symbol=echantillon["symbol"].astype(str)).sort_values("date")
    return pd.merge_asof(e, v, left_on="date", right_on="filed", by="symbol", direction="backward").drop(columns="filed")


def caracteristiques_fondamentales(faits: pd.DataFrame, px_ajuste: pd.DataFrame,
                                   splits: pd.DataFrame | None, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Facteurs fondamentaux BRUTS (non classés) par (date, symbol), sans information future."""
    symboles = list(px_ajuste.columns)
    ech = pd.MultiIndex.from_product([dates, symboles], names=["date", "symbol"]).to_frame(index=False)
    ech["symbol"] = ech["symbol"].astype(str)
    if faits is None or faits.empty:
        return ech.assign(**{f: np.nan for f in FEATURES_FD})
    faits = faits.assign(symbol=faits["symbol"].astype(str), variable=faits["variable"].astype(str),
                         end=pd.to_datetime(faits["end"]), filed=pd.to_datetime(faits["filed"]),
                         val=pd.to_numeric(faits["val"], errors="coerce"))

    for var in ["actifs", "fonds_propres", "resultat_net", "marge_brute", "chiffre_affaires",
                "cout_ventes", "flux_exploitation", "actions"]:
        ech = _asof(ech, _dernier_connu(faits, var).rename(columns={"val": var}), var, var)
    ech = _asof(ech, _croissance(faits, "actifs"), "croissance", "croissance_actifs")

    # Actions : croissance corrigée des divisions survenues entre les deux bilans
    ca = _croissance(faits, "actions")
    if splits is not None and not splits.empty and not ca.empty:
        fs = splits[splits["ratio"] > 0]
        def corr(row):
            g = fs[(fs["symbol"] == row["symbol"]) & (fs["date"] > row["end_prec"]) & (fs["date"] <= row["end"])]
            return float(np.prod(g["ratio"])) if len(g) else 1.0
        ca["croissance"] = (1 + ca["croissance"]) / ca.apply(corr, axis=1) - 1
    ech = _asof(ech, ca, "croissance", "croissance_actions")

    # Capitalisation = cours RÉEL (ajusté × divisions postérieures) × nombre d'actions publié
    fact = facteur_splits(splits, pd.DatetimeIndex(dates), symboles)
    px_reel = (px_ajuste.reindex(dates) * fact).stack(future_stack=True).rename("px_reel").reset_index()
    px_reel.columns = ["date", "symbol", "px_reel"]
    px_reel["symbol"] = px_reel["symbol"].astype(str)
    ech = ech.merge(px_reel, on=["date", "symbol"], how="left")
    capi = ech["px_reel"] * ech["actions"]
    capi = capi.where(capi > 0)

    marge = ech["marge_brute"].fillna(ech["chiffre_affaires"] - ech["cout_ventes"])
    actifs = ech["actifs"].where(ech["actifs"] > 0)
    ech["fd_rentabilite"] = marge / actifs
    ech["fd_rendement_benef"] = ech["resultat_net"] / capi
    ech["fd_valeur_comptable"] = ech["fonds_propres"] / capi
    ech["fd_croissance_actifs"] = ech["croissance_actifs"]
    ech["fd_emissions"] = ech["croissance_actions"].clip(-0.5, 2.0)   # écarte les erreurs d'unité
    ech["fd_accruals"] = (ech["resultat_net"] - ech["flux_exploitation"]) / actifs
    return ech[["date", "symbol"] + FEATURES_FD].replace([np.inf, -np.inf], np.nan)
