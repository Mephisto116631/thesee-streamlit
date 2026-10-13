# glossaire.py
# ==============================================================================
# GLOSSAIRE — fiches des indicateurs (source unique pour le Guide et les boutons ℹ️)
# Chaque fiche : titre, def (définition), lecture (comment interpréter), limites.
# ==============================================================================
import streamlit as st

FICHES = {
    # ---------------- Indicateurs techniques ----------------
    "rsi_14": {
        "titre": "RSI 14 jours",
        "def": "Relative Strength Index : compare la moyenne des hausses à celle des baisses sur 14 jours (lissage exponentiel). Échelle 0-100.",
        "lecture": "> 70 : titre suracheté (risque de repli). < 30 : survendu (rebond possible). 40-60 : neutre.",
        "limites": "Dans une forte tendance, le RSI peut rester > 70 ou < 30 longtemps : ce n'est pas un signal de retournement à lui seul.",
    },
    "pct_vs_ma50": {
        "titre": "Écart à la moyenne mobile 50j",
        "def": "(Cours − MM50) / MM50 : distance relative du prix à sa moyenne des 50 derniers jours.",
        "lecture": "Positif : au-dessus de la tendance moyen terme. Très positif : étiré, risque de retour vers la moyenne.",
        "limites": "Mesuré sur l'historique, cet écart n'a pas de pouvoir prédictif significatif à 1-5 jours.",
    },
    "macd_diff": {
        "titre": "MACD (écart des moyennes exponentielles)",
        "def": "EMA 12 jours − EMA 26 jours du cours (en unités de prix).",
        "lecture": "Positif : élan haussier. Négatif : élan baissier. Un changement de signe signale un possible changement de tendance.",
        "limites": "Exprimé en unités de prix : non comparable d'un titre à l'autre. Indicateur retardé.",
    },
    "mom_5j": {
        "titre": "Momentum 5 jours",
        "def": "Rendement du titre sur les 5 derniers jours de bourse.",
        "lecture": "Sur l'historique testé, un fort rendement récent tend à être suivi d'un léger repli (effet de retournement court terme, IC négatif).",
        "limites": "Effet faible (IC ≈ −0,01) et sensible aux coûts de transaction.",
    },
    "mom_20j": {
        "titre": "Momentum 20 jours",
        "def": "Rendement du titre sur environ un mois de bourse.",
        "lecture": "Capte la tendance de court-moyen terme. Pouvoir prédictif non significatif sur l'historique testé.",
        "limites": "Mélange tendance et bruit ; à lire avec la volatilité.",
    },
    "mom_60j": {
        "titre": "Momentum 60 jours",
        "def": "Rendement du titre sur environ trois mois de bourse.",
        "lecture": "Tendance de moyen terme. Utilisé en rang cross-sectionnel dans le modèle relatif.",
        "limites": "Pouvoir prédictif non significatif seul ; sert de contexte au modèle.",
    },
    "mom_12_1": {
        "titre": "Momentum 12-1 mois",
        "def": "Rendement de J−252 à J−21 : un an de performance en excluant le dernier mois, pour éviter l'effet de retournement court terme.",
        "lecture": "Le facteur le plus documenté en finance. Sur l'historique testé : IC positif (≈ +0,02) et statistiquement significatif. Les gagnants sur 12 mois tendent à continuer à surperformer.",
        "limites": "Sujet à des « krachs de momentum » lors des retournements de marché brutaux. Nécessite plus d'un an d'historique.",
    },
    "volatility": {
        "titre": "Volatilité 20 jours (annualisée)",
        "def": "Écart-type des rendements quotidiens sur 20 jours × √252.",
        "lecture": "Mesure l'amplitude des mouvements : 15 % = calme, 40 % et plus = titre très nerveux.",
        "limites": "Rétrospective : elle décrit le passé récent, pas le risque futur.",
    },
    "vol_relative": {
        "titre": "Volume relatif",
        "def": "Volume du jour / moyenne des volumes des 20 derniers jours.",
        "lecture": "> 1,5 : activité inhabituelle (annonce, rotation de portefeuilles). Sur l'historique testé, c'est la feature au signal le plus significatif (t ≈ 6 à 1 jour).",
        "limites": "Effet très faible (IC ≈ +0,01). Ne dit pas si le volume est acheteur ou vendeur.",
    },
    "dollar_volume_relatif": {
        "titre": "Dollar-volume relatif (ETF)",
        "def": "(Prix × volume) du jour / sa moyenne sur 20 jours. Proxy de l'intérêt des investisseurs pour l'ETF.",
        "lecture": "Un pic suggère une rotation sectorielle ou un événement de marché.",
        "limites": "Ce n'est PAS un vrai flux de création/rachat de parts : ces données sont payantes (ETF.com, ETF Global).",
    },
    "tracking_vs_ref": {
        "titre": "Écart à l'indice de référence (ETF)",
        "def": "Rendement quotidien de l'ETF moins celui de son indice de référence (ex. XLK − SPY).",
        "lecture": "Positif : le secteur surperforme le marché large ce jour-là, signal de rotation sectorielle.",
        "limites": "Un jour seulement : très bruité. Pour SPY et QQQ, la référence est l'autre indice.",
    },
    # ---------------- Macro ----------------
    "vix_regime": {
        "titre": "Régime de volatilité (VIX)",
        "def": "Découpe le VIX en 3 régimes : 0 = calme (< 15), 1 = normal (15-25), 2 = stress (> 25).",
        "lecture": "Permet au modèle d'adapter son comportement au contexte de marché. Audit IA détaille la performance par régime.",
        "limites": "Seuils fixes et arbitraires ; le VIX est un indicateur coïncident, pas avancé.",
    },
    "rsi_rank_sec": {
        "titre": "Rang du RSI dans le secteur",
        "def": "Rang percentile (0-1) du RSI du titre parmi les titres de son secteur, calculé chaque jour.",
        "lecture": "Proche de 1 : le titre est le plus suracheté de son secteur ; proche de 0 : le plus survendu.",
        "limites": "Les secteurs ne sont définis que pour la liste « core » ; les autres titres reçoivent 0,5 par défaut.",
    },
    "spread_hy": {
        "titre": "Spread High Yield (FRED BAMLH0A0HYM2)",
        "def": "Prime de rendement exigée sur les obligations d'entreprises notées spéculatives, par rapport aux emprunts d'État.",
        "lecture": "Bas (< 400 pb) : le marché est confiant. En hausse rapide : stress de crédit, souvent avant les phases de baisse des actions.",
        "limites": "Indice agrégé, pas le spread d'un émetteur précis. Publié avec un jour de décalage.",
    },
    "spread_ig": {
        "titre": "Spread Investment Grade (FRED BAMLC0A0CM)",
        "def": "Prime de rendement des obligations d'entreprises de bonne qualité (BBB et plus) par rapport aux emprunts d'État.",
        "lecture": "Plus stable que le HY. Une hausse indique un resserrement du crédit même pour les bons émetteurs.",
        "limites": "Indice agrégé, pas le spread d'un émetteur précis.",
    },
    # ---------------- Crédit & bilan ----------------
    "zscore": {
        "titre": "Z-Score d'Altman",
        "def": "Z = 1,2·A + 1,4·B + 3,3·C + 0,6·D + 1,0·E, avec A = fonds de roulement/actif, B = bénéfices non distribués/actif, C = EBIT/actif, D = capitalisation/passif total, E = chiffre d'affaires/actif.",
        "lecture": "> 2,99 : zone sûre. 1,81-2,99 : zone grise. < 1,81 : risque de détresse financière.",
        "limites": "Modèle conçu pour les entreprises industrielles cotées. Non pertinent pour les banques et sociétés de paiement (JPM, V, MA). Capitalisation approchée par prix actuel × actions du dernier bilan annuel.",
    },
    "rating_sp": {
        "titre": "Rating S&P",
        "def": "Note de crédit de l'émetteur. Investment Grade : AAA à BBB−. High Yield (spéculatif) : BB+ et en dessous.",
        "lecture": "Plus la note est basse, plus le risque de défaut est élevé et plus le coût de financement augmente.",
        "limites": "Table statique renseignée à la main : les changements de notes ne sont pas détectés automatiquement.",
    },
    "debt_eq": {
        "titre": "Dette / Capitaux propres",
        "def": "Dette financière rapportée aux fonds propres.",
        "lecture": "Un ratio élevé amplifie les gains comme les pertes. À comparer au secteur (les utilities sont structurellement plus endettées).",
        "limites": "Les rachats d'actions peuvent rendre les fonds propres négatifs et le ratio inexploitable.",
    },
    "roe": {
        "titre": "ROE (Return on Equity)",
        "def": "Résultat net / capitaux propres.",
        "lecture": "Mesure la rentabilité de l'argent des actionnaires. > 15 % est généralement bon.",
        "limites": "Gonflé artificiellement par l'endettement ou par des fonds propres réduits (rachats d'actions).",
    },
    "margin": {
        "titre": "Marge opérationnelle",
        "def": "Résultat d'exploitation / chiffre d'affaires.",
        "lecture": "Part de chaque euro de ventes qui reste après les charges d'exploitation. Comparer à des sociétés du même secteur.",
        "limites": "Varie fortement d'un secteur à l'autre (logiciel vs distribution).",
    },
    "ev_ebitda": {
        "titre": "EV / EBITDA",
        "def": "Valeur d'entreprise (capitalisation + dette nette) / EBITDA.",
        "lecture": "Multiple de valorisation indépendant de la structure financière. Plus il est bas, moins le titre est cher (toutes choses égales).",
        "limites": "Un multiple bas peut refléter une faible croissance ou un déclin du secteur.",
    },
    # ---------------- Modèle IA ----------------
    "accuracy": {
        "titre": "Accuracy vs baseline",
        "def": "Part de prédictions correctes sur le jeu de test (derniers 20 % des dates). La baseline prédit toujours la classe majoritaire du train.",
        "lecture": "Seul l'écart avec la baseline compte : le marché monte plus souvent qu'il ne baisse, donc 53 % peut être le score d'un modèle qui n'apprend rien.",
        "limites": "L'accuracy ignore la confiance de la prédiction : voir log loss et IC.",
    },
    "roc_auc": {
        "titre": "ROC AUC",
        "def": "Probabilité que le modèle attribue une probabilité plus élevée à une vraie hausse qu'à une vraie baisse.",
        "lecture": "50 % = hasard, 100 % = parfait. Au-dessus de 55 %, il y a un signal ; en finance quotidienne, 51-53 % est déjà fréquent.",
        "limites": "Mesure le classement, pas le calibrage des probabilités.",
    },
    "logloss": {
        "titre": "Log loss et Brier score",
        "def": "Mesurent la qualité des probabilités prédites en pénalisant les prédictions confiantes et fausses.",
        "lecture": "Le log loss doit être inférieur à celui de la baseline (taux de base constant, ≈ 0,693 si 50/50). Sinon, les probabilités du modèle valent moins qu'un simple taux de base.",
        "limites": "Sensible aux valeurs extrêmes ; à lire avec l'AUC.",
    },
    "ic": {
        "titre": "IC (Information Coefficient)",
        "def": "Chaque jour : corrélation de rang entre la probabilité prédite et le rendement réalisé des titres. L'IC est la moyenne sur les jours de test.",
        "lecture": "0,02 à 0,05 est déjà un signal exploitable en gestion quantitative. |t| > 2 : significatif.",
        "limites": "Les rendements à 5 jours se chevauchent : le t-stat est optimiste. Exige une stabilité dans le temps (voir walk-forward).",
    },
    "walk_forward": {
        "titre": "Walk-forward",
        "def": "Répète l'entraînement et le test sur 5 fenêtres temporelles successives, pour obtenir une moyenne et un écart-type plutôt qu'un chiffre unique.",
        "lecture": "Un écart-type élevé entre fenêtres indique un signal instable, dépendant de la période.",
        "limites": "Fenêtres courtes : chaque résultat est lui-même bruité.",
    },
    "zone_neutre": {
        "titre": "Zone neutre",
        "def": "Les mouvements dont |rendement| est inférieur au seuil sont exclus de l'entraînement et du test.",
        "lecture": "Prédire « hausse » ou « baisse » sur un mouvement de 0,01 % est du bruit. Un seuil plus élevé donne des labels plus nets mais moins d'exemples.",
        "limites": "Un seuil élevé réduit fortement l'échantillon de test : le delta peut alors être dû au hasard.",
    },
    "cible_relative": {
        "titre": "Cible relative à 5 jours",
        "def": "Le titre bat-il la médiane de l'univers sur les 5 prochains jours ? Les features sont exprimées en rang percentile par date.",
        "lecture": "Retire l'effet de marché commun, qui domine la cible « hausse demain ». Un embargo de 5 jours sépare le train du test pour éviter toute fuite d'information.",
        "limites": "Aucun gain n'est garanti : seul l'IC mesuré sur le test fait foi.",
    },
}


def info_button(cle: str, libelle: str = "ℹ️"):
    """Petit bouton ℹ️ qui ouvre la fiche d'un indicateur dans un popover."""
    fiche = FICHES.get(cle)
    if not fiche:
        return
    with st.popover(libelle, help=f"Définition : {fiche['titre']}"):
        render_fiche(cle)


def render_fiche(cle: str):
    fiche = FICHES.get(cle)
    if not fiche:
        return
    st.markdown(f"**{fiche['titre']}**")
    st.markdown(f"**Définition.** {fiche['def']}")
    st.markdown(f"**Lecture.** {fiche['lecture']}")
    st.caption(f"⚠️ Limites : {fiche['limites']}")
