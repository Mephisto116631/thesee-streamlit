# modele_regime.py
# ==============================================================================
# ALGORITHME 2 — RÉGIME DE MARCHÉ : quelle est la probabilité que le S&P 500
# baisse de plus de 10 % (par rapport au cours du jour) dans les 6 prochains mois ?
#
# Facteurs lisibles, sur un historique long (depuis 1993) :
#   vix            volatilité attendue du S&P 500 (« indice de la peur »)
#   vix_vs_1a      VIX par rapport à sa moyenne d'un an
#   credit         surcoût d'emprunt des entreprises notées Baa par rapport à l'État (FRED BAA10Y)
#   credit_3m      variation de ce surcoût sur 3 mois
#   pente          pente des taux : 10 ans − 2 ans (FRED T10Y2Y ; < 0 = courbe inversée)
#   ecart_mm200    écart du S&P 500 à sa moyenne 200 jours
#   mom_12m        performance du S&P 500 sur 12 mois
#   vol_3m         volatilité réalisée du S&P 500 sur 3 mois
#
# Deux modèles : régression logistique (chaque coefficient se lit directement) et
# XGBoost prudent. Protocole honnête : un point par mois, walk-forward à fenêtre
# croissante, embargo de 6 mois entre entraînement et test (les cibles se chevauchent).
# Mesures : AUC (« Area Under the Curve » : 50 % = hasard) et gain de log-loss face
# au taux de base (la fréquence historique des baisses de 10 %).
# ==============================================================================
import numpy as np
import pandas as pd

HORIZON = 126            # jours de bourse (~6 mois)
SEUIL_BAISSE = 0.10
FEATURES = ["vix", "vix_vs_1a", "credit", "credit_3m", "pente", "ecart_mm200", "mom_12m", "vol_3m"]
LABELS = {
    "vix": "VIX (volatilité attendue)", "vix_vs_1a": "VIX par rapport à sa moyenne 1 an",
    "credit": "Surcoût d'emprunt des entreprises", "credit_3m": "Variation du surcoût d'emprunt sur 3 mois",
    "pente": "Pente des taux (10 ans − 2 ans)", "ecart_mm200": "S&P 500 par rapport à sa moyenne 200 jours",
    "mom_12m": "Performance du S&P 500 sur 12 mois", "vol_3m": "Volatilité du S&P 500 sur 3 mois",
}
SERIES_FRED = {"credit": "BAA10Y", "pente": "T10Y2Y"}
MOIS_INITIAUX = 96       # 8 ans d'entraînement avant le premier test
EMBARGO_MOIS = 6


def telecharger(debut: str = "1993-01-01") -> pd.DataFrame:
    """Série quotidienne : spx (SPY), vix, credit, pente. Rien n'est stocké."""
    import yfinance as yf
    import fred
    d = yf.download(["SPY", "^VIX"], start=debut, progress=False, auto_adjust=True)["Close"]
    out = pd.DataFrame({"spx": d["SPY"], "vix": d["^VIX"]})
    out.index = pd.to_datetime(out.index).tz_localize(None)
    for nom, serie in SERIES_FRED.items():
        f = fred._fetch_fred_serie(serie, start_date=debut).set_index("date")["valeur"]
        out[nom] = f.reindex(out.index).ffill()
    return out.dropna(subset=["spx"]).ffill()


def caracteristiques(d: pd.DataFrame) -> pd.DataFrame:
    """Facteurs quotidiens, sans information future."""
    ret = d["spx"].pct_change()
    X = pd.DataFrame(index=d.index)
    X["vix"] = d["vix"]
    X["vix_vs_1a"] = d["vix"] / d["vix"].rolling(252).mean() - 1
    X["credit"] = d["credit"]
    X["credit_3m"] = d["credit"] - d["credit"].shift(63)
    X["pente"] = d["pente"]
    X["ecart_mm200"] = d["spx"] / d["spx"].rolling(200).mean() - 1
    X["mom_12m"] = d["spx"] / d["spx"].shift(252) - 1
    X["vol_3m"] = ret.rolling(63).std() * np.sqrt(252)
    return X


def cible(d: pd.DataFrame, h: int = HORIZON, seuil: float = SEUIL_BAISSE) -> pd.Series:
    """1 si le S&P 500 passe à un moment sous (1 − seuil) × cours du jour dans les h jours suivants."""
    px = d["spx"].values
    y = np.full(len(px), np.nan)
    for i in range(len(px) - h):
        y[i] = float(px[i + 1:i + h + 1].min() / px[i] - 1 <= -seuil)
    return pd.Series(y, index=d.index)


def mensuel(X: pd.DataFrame, y: pd.Series) -> pd.DataFrame:
    """Un point par fin de mois (les cibles quotidiennes se chevauchent trop)."""
    data = X.assign(y=y)
    fins = data.groupby(data.index.to_period("M")).tail(1)
    return fins.dropna(subset=FEATURES)


def _modele(nom: str):
    if nom == "logistique":
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
        return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=1000))
    from xgboost import XGBClassifier
    return XGBClassifier(n_estimators=200, max_depth=2, learning_rate=0.03, min_child_weight=10,
                         subsample=0.8, colsample_bytree=0.8, reg_lambda=5.0, random_state=42)


def _auc(y: np.ndarray, p: np.ndarray) -> float:
    from sklearn.metrics import roc_auc_score
    return float(roc_auc_score(y, p)) if len(set(y)) == 2 else float("nan")


def _logloss(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def evaluer(m: pd.DataFrame, nom: str, garder_tests: bool = False) -> dict:
    """Walk-forward mensuel, fenêtre croissante, test par blocs de 12 mois, embargo de 6 mois.
    `garder_tests` : ajoute les prévisions de test (`_tests`) pour l'audit du § 4.27 (à retirer avant d'enregistrer)."""
    m = m.dropna(subset=["y"])
    if len(m) < MOIS_INITIAUX + 24:
        return {}
    tests = []
    for debut in range(MOIS_INITIAUX, len(m), 12):
        test = m.iloc[debut:debut + 12].copy()
        train = m.iloc[:max(0, debut - EMBARGO_MOIS)]
        if train["y"].nunique() < 2 or len(train) < 60:
            continue
        mod = _modele(nom).fit(train[FEATURES], train["y"].astype(int))
        test["p"] = mod.predict_proba(test[FEATURES])[:, 1]
        test["base"] = float(train["y"].mean())       # taux de base connu à ce moment-là
        tests.append(test)
    if not tests:
        return {}
    t = pd.concat(tests)
    y = t["y"].values.astype(int)
    gain = _logloss(y, t["base"].values) - _logloss(y, t["p"].values)   # > 0 : mieux que le taux de base
    n_eff = max(1.0, len(t) / EMBARGO_MOIS)                              # cibles de 6 mois qui se chevauchent
    t_stat = float(gain.mean() / gain.std() * np.sqrt(n_eff)) if gain.std() > 0 else 0.0
    decennies = {}
    for dec, g in t.groupby((t.index.year // 10) * 10):
        decennies[str(dec)] = {"auc": _auc(g["y"].values.astype(int), g["p"].values), "n": int(len(g)),
                               "baisses": int(g["y"].sum())}
    return ({"_tests": t} if garder_tests else {}) | {
        "auc": _auc(y, t["p"].values), "gain_logloss": float(gain.mean()), "t_stat": t_stat,
        "n_mois_test": int(len(t)), "n_effectif": float(n_eff), "taux_base": float(y.mean()),
        "debut_test": str(t.index.min().date()), "decennies": decennies,
        "historique": [{"date": str(i.date()), "p": float(p), "y": int(v)} for i, p, v in zip(t.index, t["p"], t["y"])][-120:],
    }


def explication(m: pd.DataFrame, nom: str) -> list[dict]:
    """Logistique : coefficients standardisés (sens et poids de chaque indicateur). XGBoost : importances."""
    m = m.dropna(subset=["y"])
    mod = _modele(nom).fit(m[FEATURES], m["y"].astype(int))
    if nom == "logistique":
        coefs = mod[-1].coef_[0]
        return sorted([{"feature": f, "label": LABELS[f], "coef": float(c)} for f, c in zip(FEATURES, coefs)],
                      key=lambda x: -abs(x["coef"]))
    return sorted([{"feature": f, "label": LABELS[f], "importance": float(v)} for f, v in zip(FEATURES, mod.feature_importances_)],
                  key=lambda x: -x["importance"])


def probabilite_du_jour(d: pd.DataFrame, nom: str = "logistique") -> dict:
    """Probabilité actuelle d'une baisse de plus de 10 % dans les 6 mois, modèle entraîné sur tout l'historique."""
    X, y = caracteristiques(d), cible(d)
    m = mensuel(X, y).dropna(subset=["y"])
    mod = _modele(nom).fit(m[FEATURES], m["y"].astype(int))
    dernier = X.dropna(subset=FEATURES).iloc[[-1]]
    return {"date": str(dernier.index[0].date()), "proba": float(mod.predict_proba(dernier[FEATURES])[0, 1]),
            "taux_base": float(m["y"].mean()), "valeurs": {f: float(dernier[f].iloc[0]) for f in FEATURES}}
