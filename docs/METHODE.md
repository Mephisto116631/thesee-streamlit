# Thésée — journal de la méthode

Ce document trace **chaque choix de modélisation**, l'**hypothèse** qui le fonde, le **test** fait et son **verdict**.
Il complète l'historique des versions du [README](../README.md) : le README dit *ce qui a changé*, ce journal dit *pourquoi*.

Règle d'or : un chiffre ne sert à décider dans l'appli que s'il est **prouvé**. Sinon il est présenté comme une
**hypothèse**, ou il reste au laboratoire.

---

## 1. Comment on juge un modèle

| Notion | Définition |
|---|---|
| **IC** (Information Coefficient) | Corrélation de rang (Spearman), date par date, entre le classement prévu et le résultat réel. En %, de −100 à +100. |
| **t** (statistique de Student) | IC moyen / écart-type × √(périodes indépendantes) : l'IC moyen se distingue-t-il du hasard ? |
| **Seuil** | Quantile de Student à 5 % bilatéral, **corrigé de Bonferroni** : divisé par le nombre d'essais déjà faits dans la même famille. Plus on essaie, plus le seuil monte. |
| **Force de la preuve** | t / seuil, en %. 100 % = probant (affiché ainsi dans l'appli depuis la PR #23). |
| **Probant** | IC > 3 %, au moins 8 périodes indépendantes (`MIN_PERIODES_SIGNAL`), et force de la preuve ≥ 100 %. |
| **Walk-forward** | 4 fenêtres de test successives ; le modèle n'est entraîné que sur le passé, avec un embargo de la durée de l'horizon. |
| **QLIKE** | Perte d'une prévision de volatilité : r/p − log(r/p) − 1 sur les variances (p prévue, r réalisée). 0 si parfaite ; robuste aux erreurs de mesure (Patton, 2011). |
| **Diebold-Mariano** | Test de l'écart de perte moyen entre deux prévisions, avec un écart-type de Newey-West (les prévisions à 6 mois se chevauchent). |
| **EWMA** | Moyenne mobile exponentielle des rendements² (λ = 0,94, méthode RiskMetrics des banques). |
| **GARCH(1,1)** | Variance de demain = ω + α·rendement² d'aujourd'hui + β·variance d'aujourd'hui : la volatilité vient par vagues, puis revient vers son niveau de long terme. |
| **HAR** | Régression de la variance future sur les variances du dernier jour, de la semaine, du mois et du trimestre (Corsi, 2009) ; réputée très dure à battre. |
| **PBO** | Probability of Backtest Overfitting (Bailey et López de Prado) : probabilité que la meilleure variante d'un backtest ne soit bonne que par chance. |
| **Biais du survivant** | Évité : à chaque date, seuls les membres du S&P 500 **de cette date** (`data/sp500_historique.csv`). |

Familles d'essais (chacune a son propre seuil corrigé) : rendement, risque, portefeuille, régime de marché.
Tous les essais sont enregistrés dans la table Supabase `experiences` (onglet Analyse › Modèles IA › Laboratoire).

---

## 2. Hypothèses en vigueur

| Hypothèse | Valeur | Où la régler | Pourquoi |
|---|---|---|---|
| Taux sans risque | 4,35 %/an | Paramètres (appli) ; `portefeuille.RF` | Bons du Trésor US, base du CAPM |
| Prime de risque actions | 5 %/an | Paramètres ; `portefeuille.PRIME_RISQUE` | Moyenne historique de long terme (4 à 6 %) |
| Rendement attendu | 90 % CAPM + 10 % historique 3 ans | Paramètres (part d'historique) ; `POIDS_HISTORIQUE` | Aucun modèle ne prévoit le rendement (§ 3) : hypothèse de long terme, pas une prévision |
| Covariance | Ledoit-Wolf sur 3 ans de cours quotidiens | `JOURS_ESTIMATION` | Plus stable qu'1 an ; Ledoit-Wolf rétrécit vers une cible pour limiter l'erreur d'estimation |
| Forme de la covariance | 20 facteurs (composantes principales) + risque propre ; variance de chaque titre exacte | `N_FACTEURS` | 500 titres : 150 Ko au lieu de 3 Mo, calcul instantané sur le téléphone (§ 4.6) |
| Candidats du portefeuille | Tous les titres du S&P 500 avec 3 ans d'historique, hors Z-Score < 1,81 | `portefeuille.candidats()` | Pas de pari non prouvé (§ 4.6) |
| Contraintes | 20 % max par ligne, ≤ 12 lignes, ≥ 3 % par ligne | Paramètres ; `POIDS_MAX`, `N_MAX_LIGNES`, `POIDS_MIN` | Lisibilité et frais pour un petit capital |
| Optimiseur | FISTA (gradient projeté accéléré), 400 itérations, grille de 18 compromis λ | `optim.ts` et `portefeuille.py` (identiques) | Même résultat sur le serveur et le téléphone |
| Volatilité de chaque titre | 3 ans d'historique, ou prévision **hybride** sur 6 mois : ordre des titres par l'IA, niveau par HAR (si ses tests sont probants) | Portefeuille › « Risque mesuré avec » | Meilleure méthode en ordre et en niveau (§ 7) |
| Révision du portefeuille | Tous les 6 mois (janvier, juillet), ou tous les ans | Paramètres | Suivre chaque mois coûtait ~180 ordres/an et 3 à 5 points de rendement (§ 6.6, § 7) |
| Marge « Je limite le risque » | On vise limite × m, m appris sur le passé (≈ 0,85 à 0,93) | Automatique (laboratoire, `model_runs.marge_risque`) | Le risque réel varie plus que prévu (§ 7) |
| Projection à l'horizon | Rendements composés, écarts selon une loi de Student à 5 degrés (échelle σ), fourchette de 90 % | Paramètres (confiance) | La loi normale sous-estimait les mauvaises années (§ 7) |
| Ratios SEC affichés | PER entre 2 et 1000, cours / valeur comptable entre 0,1 et 500 ; sinon « n.d. » | `fondamentaux_sec.PER_MIN…` | Plutôt « non disponible » qu'un chiffre faux (§ 4.5) |

---

## 3. Bilan des essais (laboratoire, novembre 2026)

| Essai | Horizon | IC | t / seuil | Verdict |
|---|---|---|---|---|
| Rendement relatif (référence) | 6 mois / 1 an | 3,7 % / 7,7 % | 1,72 / 3,14 ; 2,19 / 3,51 | non probant |
| Alpha de Jensen | 6 mois / 1 an | 3,7 % / 4,9 % | 1,70 / 3,14 ; 1,36 / 3,51 | non probant |
| Alpha sectoriel | 6 mois / 1 an | 4,8 % / 5,6 % | 2,74 / 3,14 ; 2,33 / 3,51 | non probant |
| Alpha sectoriel sans facteur taille | 6 mois / 1 an | 3,3 % / 4,3 % | 1,79 ; 1,55 | non probant |
| Cours + comptes SEC | 6 mois / 1 an | 3,5 % / 6,1 % | 1,92 ; 2,35 | non probant |
| Comptes SEC seuls (valeur, rentabilité…) | 6 mois / 1 an | 1,8 % / 1,4 % | 0,99 ; 0,56 | non probant |
| Ensemble XGBoost + linéaire | 6 mois / 1 an | 4,2 % / 7,1 % | 2,25 / 3,20 ; 2,84 / 3,59 | non probant |
| CNN sur la forme des courbes | 6 mois / 1 an | −0,4 % / 1,1 % | −0,27 ; 0,67 | non probant |
| Régime de marché (baisse > 10 % en 6 mois) | 6 mois | AUC 52,5 % (logistique), 51,3 % (XGBoost) | négatif | non probant |
| **IA de volatilité** | **6 mois** | **76,4 % (référence 72,0 %)** | **6,50 / 2,97** | **probant** |
| IA de volatilité | 1 an | 74,3 % (réf. 71,0 %) | 2,96 / 3,29 | non probant (proche) |
| IA de volatilité + comptes SEC | 6 mois | 76,4 % | 6,48 / 2,97 | probant, sans gain sur la version sans comptes |
| IA de perte maximale (avec ou sans comptes) | 6 mois / 1 an | 42,7 % (réf. 40,6 %) | 2,40 / 2,97 au mieux | non probant |
| Backtest portefeuille Hold, volatilité IA | mensuel 2013-2026 | volatilité réelle −1,6 pt | 7,16 / 2,52 | probant (moins risqué ; rendement un peu plus faible) |
| Base large (tout le S&P 500) contre 40 au momentum | mensuel 2013-2026 | écart de rendement mensuel ≈ 0 | 0,15 / 2,52 (Sharpe max) | équivalente : base large adoptée (§ 5) |

Pour l'IA de risque, l'IC compte comme gain **par rapport à la référence** (la volatilité des 3 derniers mois prévoit déjà
très bien la volatilité future) : seul ce gain est testé.

---

## 4. Journal des décisions

### 4.1 Le modèle « hausse demain » est retiré (PR #19)
- **Hypothèse de départ** : XGBoost peut prévoir la hausse à 1 jour.
- **Test** : précision comparée à la référence naïve.
- **Résultat** : aucun gain stable.
- **Décision** : retiré de l'appli (`cron_sync.MODELE_1J = False`). Le code est conservé.

### 4.2 Prévoir le rendement : 16 essais, aucun probant (PR #9 à #21)
- **Hypothèse** : avec 20 ans d'historique (depuis 2005), des facteurs de long terme, les comptes SEC et de meilleurs
  algorithmes (ensemble, CNN), on peut classer les titres du S&P 500 selon leur rendement futur.
- **Précautions** :
  - composition historique de l'indice ;
  - walk-forward avec embargo ;
  - réglage choisi sur le passé seulement ;
  - seuil corrigé du nombre d'essais.
- **Résultat** (§ 3) : les meilleurs IC (5 à 8 %) restent sous le seuil. Le signal apparent de l'alpha sectoriel venait
  en partie d'un pari sur les petites valeurs (PR #11-12).
- **Décision** : les scores de rendement restent au laboratoire, marqués « en test ». Ils ne servent à **aucune décision**
  dans l'appli. Le rendement attendu du portefeuille est une **hypothèse** CAPM (§ 2).

### 4.3 La volatilité, elle, se prévoit (PR #14 à #16)
- **Hypothèse** : le risque est plus prévisible que le rendement.
- **Test** : IC de la volatilité réalisée sur 6 mois, comparé à la volatilité des 3 derniers mois.
- **Résultat** :
  - IC 76,4 % contre 72,0 % ;
  - meilleure que la référence sur 91 % des dates et sur les 4 périodes 2013-2026 ;
  - force de la preuve ≈ 220 %.
- **Décision** : la volatilité IA est proposée en option pour construire le portefeuille.

### 4.4 La preuve doit tenir dans le temps (PR #22)
- **Hypothèse** : un modèle probant hier peut cesser de l'être.
- **Dispositif** :
  - **re-test mensuel automatique** (`experiences.yml`, le 2 du mois) ;
  - **garde-fou** dans `publish.py` : la prévision n'est publiée que si le dernier test est probant ;
  - **suivi en conditions réelles** : la prévision de chaque titre est enregistrée chaque semaine
    (table `suivi_volatilite`), puis comparée au risque réellement observé 6 mois plus tard. **Premier bilan prévu le 13/05/2027.**

### 4.5 Les ratios SEC sont des faits, pas des signaux (PR #13, #22, #23)
- **Constat** : au laboratoire, valeur, rentabilité, croissance des actifs, émissions d'actions et accruals n'ont pas
  prédit le rendement sur 2012-2026. Les titres « pas chers » ont même fait un peu moins bien.
- **Décision** : ces ratios sont affichés pour **comprendre** un titre (PER, ROE, endettement…), avec ce rappel.
- **Fiabilité** :
  - bornes de plausibilité ;
  - nombre d'actions déduit seulement du bénéfice par action publié. Le nombre en couverture ne compte souvent
    qu'une catégorie d'actions : Visa sortait à un PER de 8 au lieu de ~30.
  - Valeur douteuse → « n.d. ».

### 4.6 Markowitz sur tout le S&P 500 (PR #25)
- **Avant** : le portefeuille était optimisé parmi les **40 titres** au meilleur momentum 12-1 mois / volatilité.
- **Problèmes** :
  1. le momentum n'a pas été probant (IC « momentum seul » ≈ 0 dans les diagnostics des modèles horizon). C'était
     donc un pari non prouvé, contraire à la règle d'or ;
  2. ce groupe se ressemble : les titres qui ont le plus monté viennent des mêmes thèmes. La covariance ne pouvait
     diversifier qu'à l'intérieur, et la tech pesait 41 % du portefeuille conseillé (novembre 2026).
- **Choix de l'utilisateur** : tous les titres du S&P 500, **sans plafond par secteur**. La covariance diversifie seule.
- **Conséquence technique** :
  - **Forme factorielle** : la covariance de ~500 titres est publiée sous la forme Σ = B·Bᵀ + D (20 facteurs).
    La variance de chaque titre est exacte, les covariances sont approchées à quelques % près.
  - **Optimiseur** : SLSQP (scipy) est remplacé par le même FISTA que l'appli. La projection sur les contraintes
    se fait par Newton exact.
  - **Temps de calcul** : ~1 s pour une frontière de 500 titres sur le serveur, < 2 s sur le téléphone.
- **Compatibilité** : le nouveau format est publié dans une nouvelle colonne, `univers_facteurs` (migration V13).
  Les anciennes versions de l'appli, qui lisent `univers.cov`, trouvent `univers` vide et affichent la frontière
  calculée par le serveur. Elles n'ont pas d'« Ajuster les titres » tant que l'appli n'est pas mise à jour.
- **Hypothèse testée** : la base large ne fait pas nettement moins bien que l'ancienne base, en rendement mensuel
  apparié, sur 2013-2026, avec le même moteur.
- **Règle de décision** : adopter la base large (elle retire un pari non prouvé), **sauf** si elle est nettement moins
  bonne (force de la preuve ≥ 100 % dans le mauvais sens).
- **Résultat du backtest** : équivalente dans les 4 comparaisons ; la base large est adoptée (détail au § 5).

### 4.7 Affichage de la preuve en pourcentage (PR #23)
- **Demande de l'utilisateur** : un pourcentage est plus parlant qu'un t.
- **Décision** : « force de la preuve = t / seuil » en %, avec le t et le seuil en petit à côté.

---

### 4.8 Examen approfondi de l'IA de volatilité (PR #26)
- **Pourquoi** : l'IA de volatilité est le seul modèle probant et elle pilote le risque du portefeuille. Mais sa preuve avait des angles morts :
  - **référence facile** : la seule comparaison était la volatilité des 3 derniers mois ;
  - **ordre seulement** : le test portait sur l'ordre des titres, pas sur le niveau, alors que l'appli annonce « 15 % de risque » ;
  - **pas de 2008** : la crise n'était pas dans la période de test ;
  - **aucun placebo** ;
  - **backtest sans frais**.
- **Données** : historique depuis 1998, membres du S&P 500 à chaque date. La période de test (dernier tiers des dates, 4 fenêtres) couvre 2008.
  Limite connue : Yahoo n'a pas les titres disparus de la cote, donc un biais du survivant partiel subsiste.
- **Règles de décision, fixées AVANT les essais** :
  1. L'IA reste si elle bat la **meilleure** des trois références (EWMA, GARCH, HAR) en QLIKE, avec une force de preuve ≥ 100 % (Diebold-Mariano, seuil corrigé pour 3 comparaisons). Sinon, l'appli bascule sur cette référence, plus simple et explicable, avec le même garde-fou.
  2. Biais de niveau médian > 10 % → facteur de correction appris sur le passé seulement.
     « Je limite le risque » dépassé plus de 30 % des semestres → l'appli l'écrit en clair.
     Fourchette « mauvais cas 5 % » touchée beaucoup plus de 5 % du temps → projection à queues épaisses (loi de Student).
  3. Placebo : avec une cible mélangée, |IC| < 2 % ; avec une fuite volontaire, l'IC doit exploser (le test sait voir une fuite). Sinon, on arrête tout et on cherche la fuite.
  4. Crises, VIX, secteurs, tailles : on rapporte les résultats. Si l'IA est nettement moins bonne en crise, l'appli le dit.
  5. Sensibilité (gain positif avec les 4 réglages), autre marché (S&P MidCap 400, même signe), PBO < 50 % : en cas d'échec, c'est documenté et la décision revient à l'utilisateur.
- **Résultats** : § 6.

### 4.9 Après l'examen : hybride IA + HAR, révision semestrielle, marge de sécurité (PR #27)
- **Décisions de l'utilisateur** (§ 6.7) :
  - hybride : l'IA donne l'ordre des titres, HAR le niveau ;
  - révision du portefeuille 1 à 2 fois par an ;
  - marge de sécurité sur la limite « Je limite le risque ».
- **Hybride** : le rang prédit par l'IA est converti en niveau avec les quantiles des **niveaux HAR** du jour, au lieu des
  volatilités 3 mois. On garde ainsi l'ordre de l'IA, et le niveau suit HAR : retour vers la moyenne, prudence en crise.
- **Règles de décision, fixées AVANT les essais** :
  1. L'hybride est publié si, en walk-forward 2008-2026, (a) il n'est pas nettement moins bon que HAR en QLIKE (force de
     la preuve en faveur de HAR < 100 %), et (b) son IC bat la volatilité 3 mois avec une force ≥ 100 %. C'est le 4ᵉ
     essai de la famille « références » (seuil corrigé pour 4). En cas d'échec, on publie **HAR seul**.
  2. Révision par défaut tous les 6 mois, réglable sur 12 mois. Entre deux révisions, on ne touche au portefeuille que si
     une ligne dépasse le seuil de rééquilibrage. Le backtest avec frais compare les rythmes mensuel, semestriel et
     annuel : c'est un constat, pas une condition.
  3. Marge de sécurité m = 1 / quantile 70 % du rapport risque réel / risque prévu par semestre, apprise sur le passé
     seulement. La limite visée devient limite × m, et doit être respectée au moins 70 % des semestres au backtest ;
     sinon c'est documenté, et l'appli l'affiche.
  4. Placebo : 10 tirages de cible mélangée ; |moyenne des IC| < 2 %, sinon on arrête et on cherche une fuite.
  5. Fourchette à 1 an : si, avec les niveaux hybrides, le « mauvais cas 5 % » est touché plus de 7,5 % des fois, la
     projection passe à une loi de Student à 5 degrés de liberté.
  6. *(Ajoutée le 19/11/2026 à la demande de l'utilisateur, AVANT l'essai « examen_ia_contre_har »)*. L'IA ne reste dans
     l'hybride que si elle bat **HAR** sur l'ordre des titres : écart d'IC par date entre l'hybride et HAR, force de la
     preuve ≥ 100 % (seuil corrigé pour 5 essais de la famille « références »). Sinon, l'appli passe à **HAR seul**, plus
     simple et explicable, et l'IA retourne au laboratoire. Le backtest 2006-2026 (frais, révision semestrielle) avec
     l'hybride puis avec HAR seul est rapporté : risque réel, rendement net, limite tenue. C'est un constat, pas une condition.
- **Résultats** : § 7.

### 4.10 Essai « XGBoost sur le niveau de volatilité » (protocole écrit le 20/11/2026, AVANT tout résultat)
- **Question (demande de l'utilisateur)** : l'IA actuelle apprend le **rang** du jour (`y` = rang du risque relatif). Elle ignore donc le niveau
  global (un krach double toutes les volatilités sans changer les rangs) et emprunte celui de HAR. Un XGBoost qui prévoit directement
  le **niveau** apporte-t-il quelque chose que HAR n'a pas ?
- **Hypothèses**
  - H0 : à information égale, XGBoost n'améliore pas la QLIKE de HAR (différence nulle ou en faveur de HAR).
  - H1 : XGBoost, en corrigeant HAR à partir de variables supplémentaires, a une QLIKE plus basse que HAR.
- **Variantes** (2 essais, ajoutés à la famille « références », qui en compte déjà 5 : seuil corrigé pour **7**)
  - **B (hypothèse principale)** : cible `ln(σ réalisée 6 mois) − ln(σ HAR)`. Niveau prévu = `σ HAR × exp(prévision) × lissage`.
  - **A (diagnostic)** : cible `ln(σ réalisée 6 mois)`, sans HAR comme point de départ. Niveau prévu = `exp(prévision) × lissage`.
  - A n'est pas candidat à la publication seul. Si A ≈ B, l'ancrage sur HAR n'apporte rien ; si A ≪ B, HAR est indispensable.
- **Variables** (toutes connues à la date t) : les rangs de `modele_horizon.FEATURES`, plus des niveaux en logarithme :
  `ln σ 3 mois`, `ln σ EWMA`, `ln σ 5 jours`, `ln σ 22 jours`, `ln σ HAR`, **niveau de marché** (médiane du jour de `ln σ 3 mois`) et sa
  **dispersion** (écart-type du jour).
- **Modèle** : XGBoost « prudent » fixe (300 arbres, profondeur 2). **Aucun réglage choisi sur les données** : pas de degré de liberté en plus.
- **Lissage** : prévoir un logarithme sous-estime la variance moyenne. Facteur `sqrt(moyenne(exp(2 × résidu)))`, calculé sur les résidus
  d'entraînement de chaque fenêtre. Limite assumée : résidus d'entraînement trop petits (sur-apprentissage), donc lissage possiblement
  insuffisant. **Pas de retouche après coup** : le biais éventuel est rapporté.
- **Protocole** : identique à `examen_risque.walk_forward` (membres du S&P 500 à chaque date, 4 fenêtres de test depuis 2008, embargo de la durée
  de l'horizon, HAR ajusté sur le passé seulement, 919 dates). Mêmes dates de test que l'examen de la PR #26.
- **Règles de décision, fixées AVANT l'essai**
  1. **Niveau (primaire)** : Diebold-Mariano sur la QLIKE, B contre HAR. B bat HAR si `force = −t / seuil ≥ 100 %` (seuil de Student corrigé pour 7).
  2. **Placebo** : même modèle B entraîné sur une cible mélangée. Il ne doit pas battre HAR (force < 100 % ET écart de QLIKE ≥ 0). Sinon : fuite ou
     défaut du banc d'essai, on arrête et on cherche, et le résultat 1 est écarté.
  3. **Crises** : QLIKE de B / QLIKE de HAR en 2008-2009 et en 2020, rapport ≤ 1,10 dans les deux. Sinon B est écartée même si la règle 1 est vraie
     (le défaut connu de l'IA est la sous-estimation dans les chocs).
  4. **Ordre** : IC de B (classement des niveaux prévus) rapporté contre HAR (74,9 %) et l'hybride (78,3 %). Constat, pas condition.
  5. **Calibration** : biais médian et par décile rapportés, constat.
  6. **Publication** : les règles 1, 2 et 3 réunies rendent B *candidate* au remplacement du niveau HAR dans l'hybride. Elle ne change **rien** à
     l'appli sans une décision écrite de l'utilisateur et une PR séparée (essai de laboratoire seulement).
- **Lecture d'un échec (à l'avance)**

| Observation | Conclusion | Suite possible (nouvel essai, compté) |
|---|---|---|
| B ≈ HAR (force entre −100 % et +100 %) | HAR contient déjà l'information utile ; XGBoost n'apporte que l'ordre | Rien : HAR + IA pour l'ordre reste le meilleur choix |
| B moins bonne que HAR (force ≥ 100 % pour HAR) | Sur-apprentissage ou lissage insuffisant | Modèle de plus faible capacité (régression ridge sur les logs) |
| B meilleure en moyenne mais ratio > 1,10 en crise | Dépendance au régime | Ajouter VIX / régime de marché aux variables |
| Placebo qui gagne | Fuite ou artefact du banc d'essai | Arrêt, recherche de la fuite |
| A ≈ B | L'ancrage sur HAR ne compte pas | — |
| A ≪ B | HAR indispensable ; XGBoost seul ne sait pas poser le niveau | — |

- **Limites déclarées** : biais du survivant partiel (Yahoo ne couvre pas les titres disparus) ; cibles à 6 mois qui se chevauchent (Newey-West, décalage
  de 25 semaines) ; HAR de la phase d'entraînement évalué sur ses propres données ; une seule période de test (2008-2026).
- **Résultats** : § 8.

## 5. Résultats du backtest de la base large (PR #25)

Expérience `backtest_base_large`, lancée le 19/11/2026 :
- **Période** : 169 mois de 2013 à 2026, rééquilibrage mensuel, **avant frais**.
- **Univers** : membres du S&P 500 à chaque date.
- **Moteur** : le même que l'appli (covariance factorielle, FISTA, au plus 12 lignes, 20 % maximum par ligne).
- **Mesures** : rendement et volatilité mesurés sur les mois suivant chaque rééquilibrage.

Repère, l'indice (SPY) : **12,1 %/an**, volatilité 15,7 %, rendement / risque 0,77, perte maximale −26 %.

| Portefeuille | Base | Rendement / an | Volatilité | Rendement / risque | Perte max | 1er secteur (moyenne) | Écart de rendement mensuel : force de la preuve |
|---|---|---|---|---|---|---|---|
| Sharpe max, volatilité historique 3 ans | **S&P 500** | 16,4 % | 18,8 % | **0,87** | −34 % | 31 % | +0,03 pt/mois, 6 % du seuil |
| | momentum 40 | 15,8 % | 19,9 % | 0,79 | −32 % | 32 % | |
| Sharpe max, volatilité IA | **S&P 500** | 14,6 % | 16,2 % | **0,90** | −29 % | 31 % | +0,04 pt/mois, 6 % du seuil |
| | momentum 40 | 13,7 % | 18,1 % | 0,75 | −30 % | 34 % | |
| Variance min, volatilité historique | **S&P 500** | 7,5 % | 13,4 % | 0,56 | −26 % | 36 % | −0,24 pt/mois, 44 % du seuil |
| | momentum 40 | 10,2 % | 16,0 % | 0,64 | −30 % | 34 % | |
| Variance min, volatilité IA | **S&P 500** | 9,0 % | 12,6 % | 0,72 | −24 % | 36 % | −0,16 pt/mois, 29 % du seuil |
| | momentum 40 | 10,6 % | 15,5 % | 0,69 | −29 % | 35 % | |

Seuil : 2,52 (loi de Student, corrigée pour 4 comparaisons). Verdict : **équivalente dans les 4 cas**.
Selon la règle de décision du § 4.6, la base large est **adoptée** : elle retire un pari non prouvé sans faire
nettement moins bien.

**Lecture honnête**
- **Portefeuille conseillé (Sharpe max)** :
  - Avec tout le S&P 500, le rendement / risque est un peu meilleur : 0,87 à 0,90, contre 0,75 à 0,79 pour l'ancienne base et 0,77 pour l'indice. Le risque est aussi un peu plus faible.
  - Ces écarts **ne sont pas prouvés** : force de la preuve de 6 % seulement. Il ne faut pas en conclure que l'appli « bat le marché ».
- **Perte maximale** : avec la volatilité historique, le portefeuille Sharpe max a connu −34 %, plus que l'indice (−26 %). Le portefeuille est concentré, 12 lignes au plus.
- **Avec la volatilité IA** : la perte maximale descend à −29 % et la volatilité à 16,2 %. C'est cohérent avec le § 4.3.
- **Variance minimale** :
  - Elle est nettement plus calme (12,6 à 13,4 % de volatilité, perte maximale −24 à −26 %).
  - Elle rapporte moins : 7,5 à 9 %/an, contre 12,1 % pour l'indice.
  - Elle correspond au mode « Je limite le risque » avec un risque bas.
- **Frais non comptés** : un rééquilibrage mensuel complet coûterait plus cher. Dans l'appli, le rééquilibrage ne se
  fait qu'au-delà d'un seuil d'écart (Paramètres).

**Portefeuille conseillé avant / après (synchro du 19/11/2026)**

| | Avant (40 au momentum) | Après (494 titres du S&P 500) |
|---|---|---|
| Lignes | TRV 19 %, TRGP 13 %, STT 11 %, VTRS 9 %, GWW 8 %, MU 8 %, STX 7 %, AMD 6 %, TWLO 5 %, LITE 5 %, OKTA 5 %, FTNT 5 % | BNY 18 %, MU 12 %, WELL 11 %, CRWD 10 %, EBAY 8 %, WMT 7 %, CAH 7 %, MCK 7 %, TRV 6 %, MO 6 %, ECHO 4 %, CBOE 4 % |
| Premier secteur | Technologie 41 % | Finance 28 % |
| Secteurs représentés | 5 | 7 |
| Risque attendu (volatilité) | 20,6 % | 15,5 % |
| Rentabilité de long terme (hypothèse CAPM) | 14,1 % | 12,2 % |
| Données publiées pour l'appli | covariance 40 x 40 | 494 titres, 20 facteurs, 83 Ko |

## 6. Résultats de l'examen approfondi (PR #26)

Essais `examen_*` lancés le 19/11/2026 :
- **Données** : historique depuis 1998, test du 20/02/2008 à 2026 (919 dates hebdomadaires), membres du S&P 500 à chaque date.
- **Règles** : celles du § 4.8, fixées avant les essais.

### 6.1 Contre les méthodes reconnues : **règle 1 déclenchée (bascule sur HAR)**

| Méthode | QLIKE (plus bas = mieux) | IC (ordre des titres) |
|---|---|---|
| **HAR** | **0,332** | 74,9 % |
| GARCH(1,1) | 0,374 | 76,8 % |
| IA | 0,425 | **78,3 %** |
| Volatilité 3 mois | 0,449 | 75,4 % |
| EWMA | 0,493 | 72,7 % |

- **Niveau du risque (QLIKE)** : l'IA ne bat pas HAR ; c'est l'inverse (force de la preuve −37 %). Elle ne bat pas non plus GARCH (−43 %). Elle bat presque EWMA (95 % du seuil).
- **Ordre des titres (IC)** : l'IA reste la meilleure (78,3 %, contre 74,9 % pour HAR).
- **Pourquoi l'écart** : la perte QLIKE punit beaucoup plus une sous-estimation du risque qu'une surestimation. HAR surestime en médiane (+27 %, § 6.2) et évite ainsi les fortes sous-estimations. L'IA est juste en médiane, mais sous-estime lourdement certaines dates de choc.
  - Hors crises, l'IA fait mieux que HAR sur 68 % des dates, mais elle perd en moyenne à cause de ces dates.
- **Conséquence** : HAR prévoit mieux le **niveau** du risque (ce que l'appli affiche, et la limite du mode « Je limite le risque »). L'IA prévoit mieux l'**ordre** (ce qui compte le plus pour composer le portefeuille).

### 6.2 Calibration du niveau : IA calibrée en médiane, mais trop dispersée
- **Biais médian prévu / réel** : IA −1 % (calibrée), volatilité 3 mois −1 %, EWMA −4 %, GARCH +10 %, HAR +27 %.
- **Par décile, l'IA est trop dispersée** : elle sous-estime les titres calmes (−21 % pour le 1er décile) et surestime les plus agités (+43 % pour le dernier). Il lui manque un retour vers la moyenne.

### 6.3 Crises : l'IA est moins bonne en niveau pendant les chocs
- **Contre HAR, en QLIKE**, l'IA est meilleure dans une seule crise sur 6 (2015-2016). Elle n'a été meilleure que sur 5 % des dates du Covid et 17 % des dates de 2008.
- **En ordre des titres (IC)**, elle reste comparable ou meilleure, sauf en 2008 (84,5 % contre 85,4 %).
- **VIX** : en marché nerveux (VIX > 25), l'IA n'est meilleure que sur 48 % des dates.
- **Secteurs et tailles** : l'IC de l'IA est meilleur presque partout, sauf l'énergie (78,1 % contre 78,8 %).

### 6.4 Placebo : **règle 3 déclenchée** (|IC| avec cible mélangée = 8,8 % > 2 %)
- **Cible mélangée** : IC de −8,8 %. Le signe est **négatif** : une fuite du futur donnerait un IC positif et élevé.
- **Fuite volontaire** : IC de 95,7 %. Le test détecte bien une fuite quand il y en a une.
- **Facteur aléatoire** : classé dernier sur 15, importance 0.
- **Interprétation probable** : avec une cible mélangée, le modèle ajuste du bruit. Comme la volatilité est très persistante d'une semaine à l'autre, ce bruit garde le même signe sur toutes les dates. Un seul tirage ne suffit donc pas.
- **À confirmer** par la moyenne de plusieurs tirages avant de conclure, comme le prévoit la règle 3.

### 6.5 Sensibilité et autre marché : réussis
- **Gain d'IC sur la volatilité 3 mois** : positif avec les 4 réglages (+2,7 à +3,1 points, t de 4,6 à 7,2).
- **S&P MidCap 400**, 397 titres jamais vus : IC de 78,3 % contre 77,3 %, gain +1,0 point (t 2,3). Même signe : le modèle se généralise.

### 6.6 Backtest réel 2006-2026 : **règle 5 déclenchée (PBO 85 %)**, frais très lourds
- **Rééquilibrage chaque mois** vers la nouvelle recommandation, comme si l'on suivait l'appli à la lettre. Capital de 5 000 €, 1 € par ordre, 0,1 % d'écart de prix.

| Portefeuille | Rendement brut | Rendement net de frais | Volatilité | Ordres / an | Frais / an |
|---|---|---|---|---|---|
| Sharpe max, volatilité historique | 11,4 % | 8,3 % | 21,0 % | 171 | 238 € |
| Sharpe max, IA | 8,6 % | 4,0 % | 19,8 % | 190 | 266 € |
| Variance min, volatilité historique | 6,7 % | 4,1 % | 14,3 % | 143 | 171 € |
| Variance min, IA | 7,0 % | 1,9 % | 14,6 % | 195 | 256 € |

- **Frais** : suivre chaque mois la nouvelle recommandation parmi 500 titres change presque tout le portefeuille, avec environ 170 à 190 ordres par an. Les frais coûtent alors 3 à 5 points de rendement par an : c'est **le problème pratique n° 1**.
- **Promesse « Je limite le risque »** :
  - avec la volatilité IA, la limite de 15 % est dépassée **61 %** des semestres, et celle de 12 % **68 %** des semestres ;
  - avec la volatilité historique : 34 % et 51 %.

  Les deux dépassent la règle 2 (30 %) : l'appli doit le dire.
- **Fourchette à 1 an** : le « mauvais cas 5 % » a été touché **10,8 %** des fois avec la volatilité IA, et 5,6 % avec la volatilité historique.
- **PBO de 85 %** : parmi les 16 variantes testées, celle qui gagne sur une moitié de la période finit le plus souvent dans la moitié basse sur l'autre. Le choix de variante n'est pas robuste.

### 6.7 Décisions
L'**IA de volatilité garde sa place pour l'ordre des titres**, qu'elle prévoit mieux que toutes les références.
Les règles 1, 3 et 5, ainsi que les constats sur la promesse de risque et sur les frais, appellent des décisions de
l'utilisateur. Décisions du 19/11/2026 :

| Constat | Décision de l'utilisateur | Mise en œuvre |
|---|---|---|
| Règle 1 : HAR prévoit mieux le niveau, l'IA mieux l'ordre | **Hybride** : l'IA pour l'ordre des titres, HAR pour le niveau | Nouvel essai (compté dans le seuil), publié seulement s'il est probant, avec le même garde-fou (PR #27) |
| Frais : ~180 ordres/an en suivant chaque recommandation mensuelle | **Rééquilibrer 1 à 2 fois par an** ; entre-temps, garder les titres | Recommandation figée entre deux révisions, testée au backtest avec frais (PR #27) |
| Limite « Je limite le risque » dépassée de 34 à 68 % des semestres | **Marge de sécurité** apprise sur le passé, et fréquence réelle de dépassement affichée | PR #27 |
| Règle 3 : placebo, un seul tirage à −8,8 % | Confirmer avec plusieurs tirages, comme prévu par la règle | PR #27 |
| Règle 5 : PBO de 85 % | Ne plus choisir parmi des variantes : une seule méthode, fixée à l'avance | Conséquence des décisions ci-dessus |

## 7. Hybride, révision et marge (PR #27)

Essais du 19/11/2026 :
- **Données** : historique depuis 1998, test de 2008 à 2026.
- **Backtest** : 2006-2026, frais réels (1 € par ordre, 0,1 % d'écart de prix, 5 000 €).
- **Règles** : § 4.9, commitées avant les essais (commit e6e5fc0).

### 7.1 Hybride : **publié** (règle 1 validée)

| Méthode | QLIKE (niveau, plus bas = mieux) | IC (ordre des titres) |
|---|---|---|
| **Hybride (ordre IA, niveau HAR)** | **0,331** | **78,3 %** |
| HAR | 0,332 | 74,9 % |
| IA seule | 0,425 | 78,3 % |
| Volatilité 3 mois | 0,449 | 75,4 % |

- **(a) Niveau** : l'hybride est un peu meilleur que HAR (force de la preuve de HAR : −56 %, donc pas nettement meilleur).
- **(b) Ordre** : il bat la volatilité 3 mois avec une force de **217 %** du seuil (seuil 2,63, corrigé pour 4 essais).
- **Verdict** : publié. Il hérite de l'ordre de l'IA et du niveau de HAR.
- **Limite connue** : comme HAR, il surestime le niveau en médiane (+27 %). La perte QLIKE le préfère, car une sous-estimation du risque coûte bien plus cher qu'une surestimation.

### 7.2 Placebo : **réussi** (règle 4 validée)
- **Moyenne de 10 tirages** de cible mélangée : IC de **−1,5 %** (|moyenne| < 2 %).
- **Dispersion** : les tirages vont de −12,5 % à +10,2 % (écart-type 7,9 %). Le premier tirage (−8,8 %, § 6.4) relevait donc bien du hasard, et un seul tirage ne suffisait pas.
- **Contrôles** : la fuite volontaire donne un IC de 95,7 %, et le facteur aléatoire est classé dernier.

### 7.3 Rythme de révision : la décision de l'utilisateur est confirmée par les chiffres

| Portefeuille (hybride) | Rythme | Ordres / an | Frais / an | Rendement brut | Rendement net |
|---|---|---|---|---|---|
| Conseillé (Sharpe max) | chaque mois | 165 | 231 € | 8,8 % | 5,7 % |
| | **tous les 6 mois** | **34** | **63 €** | 10,9 % | **10,2 %** |
| | tous les ans | 21 | 49 € | 13,0 % | 12,6 % |
| « Je limite le risque » 15 % | chaque mois | 180 | 277 € | 11,4 % | 8,5 % |
| | **tous les 6 mois** | **35** | **76 €** | 12,2 % | **11,6 %** |
| | tous les ans | 21 | 51 € | 12,8 % | 12,4 % |

Réviser moins souvent divise les ordres par 5 à 8 et rend 4 à 7 points de rendement net par an. Le rythme annuel a fait
encore un peu mieux que le semestriel sur cette période. L'écart entre les deux n'est pas testé, et les deux restent proposés.

### 7.4 Marge de sécurité : **règle 3 non atteinte** (documentée et affichée)

| Limite | Marge m (actuelle) | Limite tenue avec marge | Sans marge |
|---|---|---|---|
| 10 % | 0,93 | 8 % des semestres | 8 % |
| 12 % | 0,93 | 24 % | 24 % |
| 15 % | 0,89 | 54 % | 51 % |
| 18 % | 0,85 | 62 % | 54 % |

- **Une marge ne suffit pas.** En moyenne, le risque prévu est juste (rapport réel / prévu médian ≈ 0,97 à 0,99). Mais :
  - **les limites basses sont hors d'atteinte** : avec 12 titres au plus, le portefeuille le plus calme de la frontière
    dépasse souvent 10 à 12 % ; la marge ne peut alors rien changer ;
  - **les crises** font monter le risque de tous les titres à la fois, plusieurs semestres de suite.
- **Décision** (prévue par la règle 3) : la marge est appliquée, et l'appli affiche, pour la limite choisie, la part des
  semestres où elle a été tenue (en rouge sous 70 %), avec une explication. Une limite sous ~15 % est à considérer comme
  un objectif, pas une garantie.

### 7.5 Fourchette à 1 an : **règle 5 déclenchée**, loi de Student
- Avec les niveaux hybrides et la loi normale, le « mauvais cas 5 % » a été touché **8,8 %** des fois (seuil 7,5 %). La projection passe donc à une loi de Student à 5 degrés de liberté.
- **Précision de mise en œuvre** : à volatilité égale, une loi de Student à 5 degrés a une fourchette à 90 % **plus étroite**
  que la loi normale (±1,56 σ contre ±1,64 σ) ; ses queues ne s'épaississent qu'au-delà de ~2,5 σ. On utilise donc la
  Student d'échelle σ (±2,02 σ), qui élargit réellement la fourchette, conformément au texte de la règle (« loi de Student
  à 5 degrés »).
- **Couverture revérifiée** (251 portefeuilles gardés 1 an, 2006-2025, prévision hybride) :

  | Loi de la projection | « Mauvais cas 5 % » touché | « Bon cas 5 % » dépassé |
  |---|---|---|
  | Normale | 8,8 % | 5,2 % |
  | **Student à 5 degrés (échelle σ)** | **6,4 %** | 1,6 % |

  Avec la loi de Student, le mauvais cas repasse sous le seuil de 7,5 % : la règle 5 est satisfaite. Contrepartie
  assumée : le bon cas devient prudent (dépassé 1,6 % des fois au lieu de 5 %). La fourchette est un peu trop large
  vers le haut, ce qui est préférable pour décider.

### 7.6 L'IA bat-elle HAR sur l'ordre des titres ? **Oui, elle reste** (règle 6)
Essai `examen_ia_contre_har`, 2008-2026, 919 dates, membres du S&P 500 à chaque date :
- **Ordre des titres** : IC de l'hybride 78,3 % contre 74,9 % pour HAR (+3,4 points). L'hybride est meilleur sur
  **82 % des dates**. t = 5,67 pour un seuil de 2,72 (corrigé pour 5 essais) : force de la preuve **208 %**.
- **Effet sur le portefeuille** (backtest 2006-2026, frais réels, révision tous les 6 mois) :

  | Portefeuille | Prévision | Rendement net | Volatilité | Ordres / an | Limite 15 % dépassée |
  |---|---|---|---|---|---|
  | Conseillé (Sharpe max) | **hybride** | **10,2 %** | 25,9 % | 34 | — |
  | | HAR seul | 7,3 % | 26,4 % | 34 | — |
  | « Je limite le risque » 15 % | **hybride** | **11,6 %** | 19,1 % | 35 | 46 % des semestres |
  | | HAR seul | 9,4 % | 19,0 % | 37 | 49 % des semestres |

  À risque égal, le meilleur ordre des titres de l'IA a rapporté environ 2 à 3 points de plus par an. C'est un constat :
  cet écart de rendement n'est pas testé statistiquement.
- **Décision** : l'IA reste dans l'hybride. Cet essai est relancé chaque mois, avec `risque_volatilite` et
  `examen_hybride`. Si l'IA cessait de battre HAR, l'appli basculerait d'elle-même sur HAR seul.

### 7.7 Bilan de la PR #27
| Règle | Résultat | Conséquence dans l'appli |
|---|---|---|
| 1. Hybride | validée (niveau = HAR, ordre 217 % du seuil) | Prévision « IA + HAR » publiée |
| 2. Révision | constat : 165 → 34 ordres/an, +4,5 pts de rendement net | Portefeuille révisé tous les 6 mois (ou 12) |
| 3. Marge | non atteinte pour les limites < 18 % | Marge appliquée, part de semestres tenue affichée en clair |
| 4. Placebo | validée (moyenne −1,5 %) | — |
| 5. Fourchette | déclenchée puis satisfaite (8,8 % → 6,4 %) | Projection selon une loi de Student à 5 degrés |
| 6. IA contre HAR | validée (208 % du seuil) | L'IA reste ; HAR seul en repli automatique |

### 4.11 Essai « HAR remis à l'échelle » (protocole écrit le 20/11/2026, AVANT l'essai)
- **Origine** : le placebo de l'essai § 4.10 a gagné 0,0032 de QLIKE sur HAR en ne faisant que le remettre à l'échelle (§ 8.3). Hypothèse née
  **après** un résultat : elle est donc testée ici comme un essai neuf, sans réutiliser les chiffres du § 8.
- **Question** : un simple facteur multiplicatif, appris sur le passé, améliore-t-il la QLIKE de HAR, sans aucune IA ?
- **Hypothèses** : H0 : QLIKE(HAR × k) = QLIKE(HAR). H1 : QLIKE(HAR × k) < QLIKE(HAR).
- **Méthode** : une seule variante, un seul paramètre. Dans chaque fenêtre, HAR est ajusté sur l'entraînement (comme § 4.10), puis
  `k² = moyenne(σ_réelle² / σ_HAR²)` sur l'entraînement (c'est le facteur qui minimise la QLIKE d'entraînement, forme fermée).
  Niveau prévu = `σ_HAR × k`. Mêmes dates, mêmes fenêtres et même embargo que § 4.10. **Aucun réglage**, aucun modèle d'IA.
- **Multiplicité** : 1 essai de plus dans la famille « références » (7 déjà comptés) : seuil de Student corrigé pour **8**.
- **Règles de décision, fixées AVANT l'essai**
  1. **Niveau** : Diebold-Mariano sur la QLIKE, HAR × k contre HAR. Gain réel si `force = −t / seuil ≥ 100 %`.
  2. **Crises** : ratio de QLIKE (HAR × k) / HAR ≤ 1,10 en 2008-2009 **et** en 2020. Sinon écarté même si la règle 1 est vraie.
  3. **Stabilité** : HAR × k meilleur que HAR dans au moins 3 des 4 fenêtres de test.
  4. **Constats** (pas des conditions) : valeur de k par fenêtre, biais médian, part de sous-estimations, ratio par crise (dont 2022).
  5. **Pas de placebo** : il n'y a qu'un paramètre appris, il ne peut rien mémoriser. Le contrôle est le cas k = 1, qui est HAR.
  6. Les règles 1, 2 et 3 réunies rendent HAR × k *candidat* au remplacement de HAR dans l'hybride. Aucun changement de l'appli sans décision
     écrite de l'utilisateur et PR séparée.
- **Lecture d'un échec (à l'avance)**

| Observation | Conclusion |
|---|---|
| Règle 1 échoue (force < 100 %) | Le biais de HAR n'est pas corrigeable de façon détectable : HAR reste tel quel |
| Règle 1 réussit, règle 2 échoue | Le gain vient de périodes calmes et se paie en crise : rejeté (la sous-estimation en crise est le risque à éviter) |
| Règles 1 et 2 réussissent, règle 3 échoue | Gain concentré sur une fenêtre : non fiable, rejeté |
| k très différent d'une fenêtre à l'autre | Le biais n'est pas stable : un facteur fixe est inadapté |
- **Limites** : mêmes que § 4.10 ; n effectif ≈ 36 : un gain faible restera indétectable même s'il est réel (un échec ne prouve pas l'absence d'effet).
- **Résultats** : § 9.

### 4.12 Règles v2 de test (rédigées le 20/11/2026 ; valables pour les essais PROTOCOLÉS APRÈS cette date)
- **Origine** : demande de l'utilisateur d'améliorer les tests, après l'essai § 8 (écart de QLIKE 0,014, erreur-type 0,058). Revue de littérature
  (Patton 2011 ; Giacomini-White 2006 ; Lazarus-Lewis-Stock-Watson 2018 ; Coroneo-Iacone 2020 ; Quaedvlieg 2021 ; Holm 1979 ; Romano-Wolf 2005 ;
  Hansen 2005 ; Hansen-Lunde-Nason 2011 ; Harvey-Liu-Zhu 2016 ; Harvey-Liu 2020 ; Benjamin et al. 2018 ; Bailey-López de Prado 2014).
  Les chiffres de puissance de la revue sont des calculs de l'assistant : seule la taille du test a été vérifiée par simulation (ci-dessous).
- **Diagnostic** : avec n effectif ≈ 36, l'écart minimal détectable (80 % de puissance, 5 %) est ≈ 0,16 de QLIKE, soit 10 fois l'écart observé.
  Le t de −0,24 se lit « non informatif », **jamais** « équivalent ». Aucun changement de seuil ne corrige cela ; seule de l'information nouvelle le peut.
- **Non-rétroactivité** : ces règles ne changent aucun verdict des essais §§ 8 et 9 (leurs règles étaient fixées avant, elles restent celles qui jugent).
  Les statistiques v2 y sont ajoutées comme **constats**, dans `diagnostics.inference_v2`.

| # | Règle v2 | État |
|---|---|---|
| 1 | **Rapport systématique** pour chaque comparaison : écart, erreur-type, t, p, IC 95 %, n effectif, ν, écart minimal détectable (MDE) et écart/MDE | **Fait** (`inference.rapport_dm`) |
| 2 | **Puissance a priori** : un essai dont le MDE dépasse l'effet plausible est déclaré « sans pouvoir de conclure » avant d'être lancé ; il ne peut alors produire qu'une piste | À appliquer dans chaque protocole |
| 3 | **Variance de long terme EWC** (Lazarus et al. 2018) avec ν = min(0,4·T^(2/3), T/(2h)), loi de Student à ν degrés de liberté, au lieu de Newey-West avec loi normale | **Fait** (`inference.variance_long_terme_ewc`) |
| 4 | **Panel** : l'écart de perte est déjà moyenné sur les titres à chaque date (estimateur de type Driscoll-Kraay). Le gain de puissance du panel est donc **déjà inclus** dans l'erreur-type de 0,058 | Constat : pas de gain restant de ce côté |
| 5 | **Famille confirmatoire corrigée par Holm** (jamais moins puissant que Bonferroni) ; SPA / StepM quand on compare N variantes à une référence ; MCS pour le rapport | Holm **fait** (`inference.holm`) ; SPA/StepM/MCS à faire |
| 6 | **Compteur d'essais** : t maximal attendu par hasard pour N essais (`inference.t_max_attendu`) rapporté à côté du meilleur t | **Fait** |
| 7 | **Deux niveaux de preuve** : *piste* = t ≥ 2 (p < 5 %), même signe sur ≥ 3 des 4 fenêtres ; *publication* = p corrigé < 0,5 % (t ≈ 3), effet ≥ minimum économique déclaré, **et réplication** sur des données non utilisées (autre période ou autre indice) avec t ≥ 2 | Règle écrite ; remplace « force ≥ 100 % » pour les essais futurs |
| 8 | **Référence recalibrée** : toute IA de niveau est comparée à HAR direct à 126 jours remis à l'échelle (l'essai § 9) en plus de HAR brut | Essai § 9 |
| 9 | **Test multi-horizon** (1, 5, 22, 63, 126 jours ; Quaedvlieg 2021) : la seule source nouvelle d'information (n effectif ≈ 200 à 1 mois). La décision produit reste à 126 jours | À faire (nouvel essai) |
| 10 | **Test d'équivalence** (TOST, marge déclarée) quand l'objectif est de montrer « pas pire » ; exige MDE < marge | À appliquer |
| 11 | **Purge et embargo ≥ horizon (126 jours)**, placebos maintenus | Déjà en place pour l'embargo |
| 12 | **Perte primaire QLIKE, secondaire MSE**, pré-déclarées | En place (MSE à ajouter) |

- **Vérification de la taille du test** (simulation, 1 500 tirages, T = 919 dates, chevauchement de 25 dates, nulle vraie, seuil nominal 5 %) :

| Méthode | Taux de rejet à tort |
|---|---|
| Écart-type naïf (indépendance) | **70,5 %** |
| Newey-West, h−1 retards, loi normale | 13,3 % |
| EWC, ν = 0,4·T^(2/3) = 38 (Lazarus et al.) | 9,0 % |
| **EWC, ν plafonné à T/(2h) = 18 (règle v2)** | **5,9 %** |

  Lecture : le test utilisé jusque-là sur-rejette (13 % au lieu de 5 %), donc ses « échecs » ne viennent pas d'un test trop sévère : il était, au
  contraire, plutôt généreux. Le plafond ν ≤ T/(2h) ramène la taille près de 5 % ; c'est la règle heuristique de la revue, validée ici **dans ce seul
  schéma** (chevauchement pur, sans persistance supplémentaire).
- **Ce qui n'est pas résolu** : la puissance. Les règles 2, 9 et 10 sont les seules qui l'améliorent ou la rendent lisible. La règle 7 abaisse le seuil
  d'exploration mais exige une réplication avant toute publication.

### 4.13 Essai « test multi-horizon » (protocole écrit le 20/11/2026, AVANT l'essai ; règles v2 du § 4.12)
- **Question** : l'IA de niveau (variante B du § 4.10 : XGBoost corrigeant HAR) bat-elle HAR **à court et moyen terme**, là où la littérature
  (Christensen, Siggaard et Veliyev 2023 ; Bollerslev, Patton et Quaedvlieg 2016) trouve des gains, et où l'on dispose de bien plus de périodes
  indépendantes (≈ 920 × 5 / h : 184 à 22 jours, 73 à 63 jours, contre 37 à 126 jours) ?
- **Ce que l'essai ne peut PAS faire (déclaré à l'avance)** : la décision du produit reste le risque à 6 mois. Un gain à court terme **ne prouve rien** à
  126 jours. Il ne peut donner qu'une **piste** (§ 4.12, règle 7) ; toute publication exigerait un protocole séparé à 126 jours avec réplication.
- **Horizons** : 5, 22, 63, 126 jours de bourse (le jour seul est écarté : sa volatilité réalisée, une seule observation, est trop bruitée pour QLIKE).
- **Modèles** : à chaque horizon h, HAR direct (variance future de l'horizon h régressée sur v1, v5, v22, v63, ajustée sur le passé) et B (cible
  `ln σ_h − ln σ_HAR,h`, mêmes variables que § 4.10, XGBoost prudent fixe, lissage de Duan). Même procédure que § 4.10 : 4 fenêtres de test depuis 2008,
  embargo = durée de l'horizon, membres du S&P 500 à chaque date.
- **Statistique primaire (aSPA simplifié)** : `d_t = moyenne sur h de [QLIKE_B,h,t − QLIKE_HAR,h,t]`, avec **poids égaux** déclarés à l'avance, sur les dates
  communes aux 4 horizons. Test : EWC, ν = min(0,4·T^(2/3), T/(2·h_max)) avec h_max = 126 jours (le plus prudent), loi de Student (§ 4.12, règle 3).
  Le test uniforme uSPA de Quaedvlieg n'est **pas** implémenté (il exige un bootstrap par blocs) : il est remplacé, comme contrôle plus conservateur,
  par **Holm sur les 4 tests par horizon**.
- **Règles de décision, fixées AVANT l'essai**
  1. **Piste** si les trois conditions sont réunies : (a) `t_aSPA ≤ −2` (B meilleure) ; (b) `d_t` moyen < 0 dans au moins 3 des 4 blocs de dates consécutifs de même taille ;
     (c) le placebo (même modèle, cible mélangée) ne bat pas HAR de façon significative (`t_placebo > −2`).
  2. **Fuite probable** si `t_placebo ≤ −2` : arrêt, recherche d'une fuite, résultat écarté.
  3. **B pire que HAR** si `t_aSPA ≥ +2` (sur-apprentissage) : rapporté, pas de suite.
  4. **Équivalence (TOST, § 4.12 règle 10)** : marge Δ = 0,01 de QLIKE (≈ 3 % de la QLIKE de HAR). Équivalence seulement si l'IC à 90 % de `d_t` ⊂ [−Δ, +Δ].
     Elle n'est concluable que si le MDE rapporté est < Δ ; sinon on écrit « sans pouvoir de conclure ».
  5. **Constats (pas des conditions)** : t, p, erreur-type, IC 95 %, n effectif, MDE, écart/MDE **à chaque horizon** ; Holm sur les 4 horizons ; ratio en crise (2008-2009, 2020, 2022) ; IC (ordre) à chaque horizon.
- **Puissance annoncée a priori (§ 4.12, règle 2)** : à 126 jours, l'erreur-type de l'écart B − HAR était de 0,058 (Newey-West, § 8) et de 0,017 pour HAR × k (EWC, § 9) :
  la fourchette est large. Si l'on suppose un écart-type par observation comparable et un n effectif ∝ 1/h, l'erreur-type vaudrait environ 0,03 à 22 jours et 0,015 à 5 jours,
  donc un MDE de l'ordre de **0,04 à 0,08** pour l'aSPA. C'est **plus grand que les écarts plausibles à 126 jours (0,003 à 0,014)** : l'essai peut détecter des gains
  nettement plus gros à court terme (comme ceux de la littérature), mais **pas** prouver l'équivalence. Cette estimation est grossière et sera remplacée par le MDE mesuré.
- **Lecture d'un échec (à l'avance)**

| Observation | Conclusion |
|---|---|
| Piste (règle 1) | L'IA apporte quelque chose à court terme ; suite possible : protocole à 126 jours avec réplication (S&P MidCap 400), jamais une publication directe |
| t_aSPA entre −2 et +2, MDE > 0,02 | Sans pouvoir de conclure : pas de preuve, pas de preuve du contraire |
| t_aSPA entre −2 et +2, MDE < Δ et IC 90 % ⊂ [−Δ, Δ] | Équivalence démontrée : HAR suffit à toutes les échéances testées |
| Gain à 5 ou 22 jours seulement (Holm) | Gain de court terme, sans lien avec le portefeuille semestriel ; pourrait servir un suivi mensuel du risque (à protocoler) |
| Placebo significatif | Fuite ou défaut du banc d'essai : arrêt |

- **Limites** : mêmes que § 4.10 ; poids égaux arbitraires mais déclarés ; uSPA absent ; les dates communes aux 4 horizons se chevauchent entre horizons (l'EWC à ν prudent en tient compte de façon approximative) ;
  4 horizons × 4 fenêtres = peu de blocs indépendants au total.
- **Précision de lecture, ajoutée le 20/11/2026 à 13 h 20 UTC, AVANT le résultat** (run n° 42 en file, aucune donnée de l'essai vue) :
  la règle 2 n'est **pas modifiée** et s'applique à la lettre. Mais le § 8.3 a montré qu'un placebo à cible mélangée ne prévoit qu'une constante,
  donc qu'il **remet HAR à l'échelle**. À 5 et 22 jours, le test a beaucoup plus de puissance qu'à 126 jours : un simple gain d'échelle peut y devenir
  significatif et déclencher la règle 2 sans aucune fuite. Si la règle 2 se déclenche, on rapportera donc en plus, comme **constat** :
  (i) le placebo comparé à HAR × k (le facteur d'échelle du § 4.11, appris sur l'entraînement au même horizon) ;
  (ii) la lecture « effet d'échelle » si placebo ≈ HAR × k, « fuite à chercher » sinon. Le verdict à la lettre (« fuite probable »,
  donc pas de piste) reste celui qui compte ; la lecture ne sert qu'à orienter la suite.
- **Résultats** : § 10.

### 4.14 Essai « HAR-X : HAR + volatilité implicite (VIX) » (protocole écrit le 20/11/2026, AVANT tout code ; règles v2 du § 4.12)
- **Origine** : les essais §§ 8, 9 et 10 n'utilisent que les **cours passés**. HAR en extrait déjà presque tout ; le reste vient surtout des chocs
  de marché (2020, 2022), là où les IA de niveau échouent. Le § 4.12 (règles 2 et 9) dit que seule une **information nouvelle** peut changer
  la donne. La volatilité implicite (VIX) est la seule information **tournée vers l'avenir** disponible gratuitement depuis 1990. La littérature
  la trouve informative au-delà de HAR pour la volatilité de marché (Busch, Christensen et Nielsen 2011 ; Christensen et Prabhala 1998).
- **Question** : ajouter le VIX à HAR améliore-t-il la prévision du **niveau** de volatilité de chaque titre ?
- **Hypothèses** : H0 : QLIKE(HAR-X) = QLIKE(HAR). H1 : QLIKE(HAR-X) < QLIKE(HAR).
- **Modèle** (une seule variante, pas de réglage) : HAR direct du § 4.10 (variance future régressée sur v1, v5, v22, v63, moindres carrés sur le
  passé) avec **une variable de plus** : `x = β̂² × (VIX / 100)² / 252`, la variance quotidienne que le marché des options anticipe pour la part
  « marché » du titre (β̂ : bêta sur 1 an, déjà calculé, sans information future). VIX : clôture `^VIX` (Yahoo), au jour de la prévision.
  Mêmes dates, fenêtres, embargo (= horizon) et membres du S&P 500 que § 4.10. Aucune IA.
- **Horizons** : **126 jours** (primaire : c'est l'horizon du produit) et **22 jours** (secondaire). La littérature trouve l'apport du VIX
  plus fort à 1 mois, ce qui correspond à l'échéance du VIX lui-même.
- **Multiplicité** : 1 essai de plus dans la famille « références » ; famille confirmatoire de 2 tests (126 et 22 jours), corrigée par **Holm**.
- **Statistique** : `d_t = QLIKE_HAR-X − QLIKE_HAR` par date (moyenne sur les titres), `inference.rapport_dm`, EWC avec ν = min(0,4·T^(2/3), T/(2h)), loi de Student.
- **Règles de décision, fixées AVANT l'essai** (§ 4.12, règle 7)
  1. **Piste** (à chaque horizon) : t ≤ −2 et `d_t` moyen < 0 dans au moins 3 des 4 fenêtres de test.
  2. **Candidat à la publication** (126 jours seulement) : (a) p unilatéral corrigé par Holm < 0,5 % ; (b) écart ≤ **−0,01** de QLIKE (minimum économique,
     ≈ 3 % de la QLIKE de HAR, même marge Δ que le § 4.13) ; (c) ratio de QLIKE HAR-X / HAR ≤ 1,10 en 2008-2009 **et** en 2020 ; (d) **réplication** sur le
     S&P MidCap 400 (titres jamais utilisés, `universe.get_sp400_tickers`) avec t ≤ −2 dans le même sens.
  3. **Placebo** : même modèle avec un VIX **décalé de 252 jours** (vraie série, mauvais moment). Il garde la forme et l'échelle du VIX mais perd sa
     valeur de prévision. Il ne doit pas battre HAR (t > −2). Sinon le gain viendrait de la variable en plus, pas de l'information : résultat écarté.
     Ce placebo évite le défaut du § 8 : les deux modèles gardent les 5 coefficients de HAR, il n'y a aucun effet d'échelle à « remettre ».
  4. **Pire que HAR** si t ≥ +2 : rapporté, pas de suite.
  5. **Équivalence** (TOST, Δ = 0,01) concluable seulement si le MDE < Δ ; sinon « sans pouvoir de conclure ».
  6. **Constats** (pas des conditions) : coefficient du VIX par fenêtre et son signe, biais médian, part de sous-estimations, ratio par crise (dont 2022),
     IC (ordre des titres), MSE en perte secondaire, `t_max_attendu` pour le nombre total d'essais.
  7. Les règles 2 (a) à (d) réunies rendent HAR-X **candidat** au remplacement de HAR dans l'hybride (le niveau seulement ; l'ordre reste à l'IA).
     Aucun changement de l'appli sans décision écrite de l'utilisateur et PR séparée.
- **Puissance annoncée a priori (§ 4.12, règle 2)** : à 126 jours, le MDE mesuré au § 9 est ≈ 0,05. Un gain de 0,01 à 0,03 (ordre de grandeur plausible si le
  VIX aide surtout en début de crise) n'est **pas** détectable à 126 jours : l'horizon primaire risque d'être « sans pouvoir de conclure ». À 22 jours, le MDE
  attendu (≈ 0,02 à 0,03, § 4.13) rend un gain de cette taille **détectable**. C'est pourquoi une piste à 22 jours est l'issue la plus probable si le VIX aide.
  Le MDE mesuré remplacera cette estimation.
- **Lecture d'un échec (à l'avance)**

| Observation | Conclusion |
|---|---|
| Candidat (règle 2) | Le VIX apporte au niveau ce que les cours n'ont pas ; proposition de l'intégrer au niveau de l'hybride (décision de l'utilisateur) |
| Piste à 22 jours seulement | Le VIX aide à 1 mois, pas prouvé à 6 mois ; pourrait servir un risque « à court terme » affiché (à protocoler), pas le portefeuille semestriel |
| Piste à 126 jours sans réplication midcaps | Peut-être propre au S&P 500 ou à la période : non publié |
| t entre −2 et +2, MDE > 0,02 | Sans pouvoir de conclure : on ne sait pas, et les seules données publiques ne permettront pas de savoir à 6 mois |
| Placebo significatif | Le gain vient du degré de liberté, pas de l'anticipation : écarté |
| Coefficient du VIX instable ou de signe changeant selon les fenêtres | Relation non stable : écarté même si la moyenne est bonne |
| Pire en crise (règle 2 c) | Le VIX réagit trop tard ou trop fort aux chocs : écarté |

- **Limites** : un seul VIX pour tous les titres (pas de volatilité implicite par titre, payante) ; le bêta de 1 an peut changer en crise ;
  n effectif ≈ 36 à 126 jours ; les midcaps n'ont pas de composition historique (biais du survivant reconnu).
- **Additif du 20/11/2026, 14 h 10 UTC, AVANT tout code de HAR-X** (après le résultat du § 10, qui ne porte pas sur HAR-X) : le § 10 a mesuré les
  écarts minimaux détectables (MDE) entre B et HAR à chaque horizon : **0,039 à 5 jours, 0,108 à 22 jours, 0,273 à 63 jours, 0,200 à 126 jours**.
  Mon estimation a priori pour 22 jours (≈ 0,02 à 0,03) était donc **trop optimiste**. À court terme, la volatilité réalisée sur peu de jours est très
  bruitée, et la QLIKE l'est aussi. Nuance : le MDE dépend de l'écart entre les deux prévisions comparées. HAR-X ne diffère de HAR que par une
  variable : ses prévisions resteront très proches de celles de HAR, comme HAR × k au § 9 (MDE 0,051 à 126 jours, contre 0,20 pour B). On s'attend
  donc à un MDE de HAR-X nettement plus petit que celui de B, mais **non mesuré**. **Ajout au protocole** (aucune règle de décision modifiée) :
  **5 jours** devient un horizon de **constat** (le seul où le MDE mesuré est < 0,04), sans entrer dans la famille confirmatoire (126 et 22 jours).
  Le MDE de HAR-X sera rapporté à chaque horizon. Si à 126 et 22 jours il dépasse 0,03, l'essai sera déclaré « sans pouvoir de conclure »
  (§ 4.12, règle 2) quel que soit t.
  *Précision du 21/11/2026, avant tout code* : « quel que soit t » contredit la règle v2 n° 2, qui dit qu'un essai peu puissant « ne peut produire
  qu'une piste ». On applique la règle v2 : un horizon dont le MDE dépasse 0,03 ne peut être ni **candidat** ni **équivalent**, mais une **piste**
  (règle 1 du § 4.14) y reste possible. Si aucune piste n'apparaît, le verdict est « sans pouvoir de conclure ». Les autres règles sont inchangées.
  *Mise en œuvre* : la réplication sur le S&P MidCap 400 (règle 2 d) n'est calculée que si les règles 2 (a) à (c) sont réunies ; sinon elle ne
  changerait pas le verdict, et l'essai économise ~15 minutes de téléchargement.
- **Résultats** : § 11.

---

## 8. Résultats de l'essai « XGBoost sur le niveau » (PR #28, lancé le 19/11/2026 23:05 UTC)

Protocole : § 4.10, inchangé depuis son commit. 919 dates de test, du 20/02/2008, 4 fenêtres, n effectif 36,5, seuil de Student corrigé pour 7 essais : **2,86**.

### 8.1 Règles de décision

| Règle | Résultat | Verdict |
|---|---|---|
| 1. Niveau : B bat HAR (force ≥ 100 %) | QLIKE 0,3186 contre 0,3325 ; t = −0,24 ; **force 8 %** | **Échec** (écart non significatif) |
| 2. Placebo ne bat pas HAR (force < 100 % et écart ≥ 0) | QLIKE 0,3293 : **écart −0,0032** (force 8 %) | **Échec à la lettre** (voir 8.3) |
| 3. Crises : ratio B / HAR ≤ 1,10 en 2008-2009 et 2020 | 2008-2009 : 0,94 ; **2020 : 1,30** | **Échec** |
| **Candidate à la publication** | non | **B n'est pas candidate** |

### 8.2 Constats (règles 4 et 5, et variante A)

| Mesure | HAR | B (XGBoost sur HAR) | A (XGBoost seul) | Placebo de B |
|---|---|---|---|---|
| QLIKE (plus bas = mieux) | 0,3325 | 0,3186 | 0,3251 | 0,3293 |
| Force de la preuve contre HAR | — | 8 % | 5 % | 8 % |
| IC (ordre des titres) | 74,9 % | 77,8 % | — | — |
| Biais médian prévu / réel | +27 % | **+7 %** | — | — |
| Part de prévisions sous-estimées | 23 % | **41 %** | — | — |

Ratio de QLIKE B / HAR par période (< 1 : B meilleure) : 2015-2016 : 0,42 · 2011 : 0,86 · fin 2018 : 0,76 · 2008-2009 : 0,94 · **2020 : 1,30** · **2022 : 1,65**.

### 8.3 Lecture, selon la grille écrite à l'avance (§ 4.10)

- **Ligne « B ≈ HAR »** : l'écart de QLIKE (−4 % pour B) est **loin du seuil** (force 8 %, il en faudrait 100 %). Avec n effectif = 36, un gain de cette taille ne se distingue pas du hasard. **Conclusion retenue : on ne détecte pas d'information de niveau que HAR n'ait pas déjà.** Ce n'est pas la preuve que B est équivalente à HAR, seulement qu'on ne peut pas dire qu'elle fait mieux.
- **A ≈ B** (0,3251 contre 0,3186, forces 5 % et 8 %) : l'ancrage sur HAR ne change pas le résultat.
- **Crises** : B est la plus mauvaise là où le coût d'une sous-estimation est le plus fort : 2020 (×1,30) et 2022 (×1,65). Cela rejoint le défaut déjà connu de l'IA (§ 6.1). Sa meilleure calibration moyenne (+7 % contre +27 %) a un prix : 41 % de sous-estimations contre 23 % pour HAR. La QLIKE punit ce déplacement.
- **Placebo (règle 2)** : la règle est **déclenchée à la lettre**, mais **ce n'est pas une fuite**. Un modèle entraîné sur une cible mélangée prévoit en gros une constante, donc il ne fait que **remettre HAR à l'échelle** : il corrige son biais de +27 %. Cette correction seule gagne 0,0032 de QLIKE. La règle 2 était mal posée : le placebo était censé tester une fuite, pas l'effet d'un simple changement d'échelle. Aucune décision ne repose dessus, car la règle 1 échoue indépendamment.
- **Observation après coup (non prévue au protocole, donc à ne pas retenir comme preuve)** : si on retire cet effet d'échelle, le gain de B sur le placebo est de l'ordre de 0,0107 de QLIKE. Il n'a pas été testé statistiquement.
- **Ordre des titres** : l'IC du classement par niveau de B (77,8 %) est proche de celui de l'IA publiée (78,3 %) et au-dessus de HAR (74,9 %). Le gain d'ordre existe, mais il est déjà dans l'hybride.

### 8.4 Décision

Aucun changement : l'hybride (ordre de l'IA, niveau de HAR) reste en place. B n'est pas adoptée.

### 8.5 Suites possibles (chacune serait un nouvel essai compté, soumis à l'accord de l'utilisateur)
1. **Remise à l'échelle de HAR seule** : le placebo suggère qu'un facteur correctif du biais de HAR (appris sur le passé) gagne un peu de QLIKE sans aucune IA. À tester comme essai à part, avec son protocole.
2. **Modèle de plus faible capacité** (ridge sur les logs), pour limiter la sous-estimation en crise.
3. **Variable de régime** (VIX) pour les chocs de 2020 et 2022.
4. Laisser le niveau à HAR : l'essai n'a rien à lui reprocher qu'il soit possible de prouver.

---

## 9. Résultats de l'essai « HAR remis à l'échelle » (PR #28, lancé le 20/11/2026)

Protocole : § 4.11, inchangé depuis son commit. Verdict jugé par les règles de ce protocole (lot du 12:44 UTC) ; les statistiques v2 (§ 4.12) viennent du second
lot (12:55 UTC), ajoutées comme **constats**. Les deux lots divergent à la 3ᵉ ou 4ᵉ décimale (Yahoo a corrigé quelques cours entre les deux) : limite de
reproductibilité à retenir, elle est bien plus petite que tout écart discuté ici. 919 dates de test, n effectif 36,5, seuil de Student corrigé pour 8 essais : **2,91**.

### 9.1 Règles de décision (§ 4.11)

| Règle | Résultat | Verdict |
|---|---|---|
| 1. Niveau : HAR × k bat HAR (force ≥ 100 %) | QLIKE 0,3298 contre 0,3325 ; écart −0,0027 ; t = −0,19 ; **force 6 %** | **Échec** |
| 2. Crises : ratio ≤ 1,10 en 2008-2009 et 2020 | 2020 : 1,04 ; **2008-2009 : 1,16** | **Échec** |
| 3. Stabilité : meilleur dans ≥ 3 fenêtres sur 4 | **2 sur 4** | **Échec** |
| **Candidat** | non | **HAR × k n'est pas candidat** |

### 9.2 Constats

- **Facteur k** : 0,945 ; 0,949 ; 0,943 ; 0,966 selon la fenêtre. **Très stable**, mais proche de 1 : HAR, ajusté en moindres carrés sur la variance, est déjà quasi calibré **en moyenne**
  (il ne surestime que de 5 % en moyenne).
- **Biais médian** : +27 % pour HAR, +21 % pour HAR × k. Le « biais de 27 % » du § 6.2 est donc surtout un **effet d'asymétrie** : une prévision correcte de la moyenne d'une variable
  asymétrique surestime sa médiane. Ce n'était pas un défaut de HAR à corriger (point soulevé par la revue de littérature, Patton 2011).
- **Par fenêtre** (QLIKE de HAR × k / HAR) : 2008-2012 : 0,438 / 0,413 (HAR meilleur) · 2012-2017 : 0,303 / 0,353 (HAR × k meilleur) · 2017-2021 : 0,429 / 0,410 (HAR meilleur) · 2021-2026 : 0,148 / 0,154 (HAR × k meilleur).
  Le gain n'a pas de signe stable.
- **Statistiques v2** (écart −0,0028) : erreur-type EWC 0,0173 (ν = 18) ; IC à 95 % **[−0,039 ; +0,034]** ; p = 0,87 ; n effectif 37 ; **écart minimal détectable 0,051**, soit l'écart observé = 5 % du MDE.

### 9.3 Lecture, selon la grille écrite à l'avance (§ 4.11)

- **Règle 1 échoue** : le biais d'échelle de HAR n'est pas corrigeable de façon détectable. HAR reste tel quel.
- **Réconciliation avec le § 8** : le placebo du § 8 avait gagné 0,0032 de QLIKE sur HAR ; ici le facteur k seul en gagne 0,0027, du même ordre. Ce gain est **minuscule et non significatif** : l'hypothèse née de l'observation du placebo n'est pas confirmée.
- **Conséquence pour l'essai § 8** : l'écart de B sur le placebo (0,0107, observation après coup) reste sans test. Il n'est pas démontré non plus que B apporte de l'information au-delà d'une recalibration.
- **Limite honnête** : le test ne peut détecter que des écarts d'environ 0,05 ; un gain réel de 0,003 reste invisible. On peut dire « pas de gain détectable », pas « pas de gain ».

### 9.4 Décision

Aucun changement. L'hybride (ordre de l'IA, niveau de HAR) reste en place.

### 9.5 Bilan des deux essais sur le niveau (§§ 8 et 9) et suite
1. **HAR brut est une référence solide à 6 mois** : ni XGBoost (§ 8) ni une recalibration simple (§ 9) ne le battent de façon détectable avec la puissance dont on dispose.
2. **Seul levier restant sur la puissance : l'information nouvelle** (§ 4.12, règle 9) : un test multi-horizon (1, 5, 22, 63, 126 jours) donnerait environ 200 périodes indépendantes à 1 mois.
   Il répondrait à une question un peu différente (le gain existe-t-il à court terme ?) sans prouver le gain à 6 mois. À protocoler avant de lancer.
3. **Rapports de puissance** : désormais, chaque essai doit publier son MDE ; ceux-ci montrent que la plupart des écarts discutés (0,003 à 0,014) sont de 5 à 30 % du MDE.

---

## 10. Résultats de l'essai « multi-horizon » (PR #28, lot du 20/11/2026 13:22 UTC, run n° 43)

Protocole : § 4.13, inchangé depuis son commit, plus la précision de lecture de 13 h 20 UTC (écrite avant le résultat ; elle n'a pas servi, voir
règle 2). 911 dates communes aux 4 horizons, du 20/02/2008 au 19/05/2026, 4 fenêtres, membres du S&P 500 à chaque date. Journaux du run sans
`[LABO][ERREUR]`. Dans le même run, les re-tests du produit sont inchangés : hybride publié, l'IA reste, `risque_volatilite` 6 mois probant (t 6,50).

### 10.1 Règles de décision (§ 4.13)

| Règle | Résultat | Verdict |
|---|---|---|
| 1. Piste : t_aSPA ≤ −2, ≥ 3 blocs sur 4 négatifs, placebo non significatif | t_aSPA = **+0,06** ; blocs négatifs 3/4 ; placebo t = −0,55 | **Non** (t loin de −2) |
| 2. Fuite probable : t_placebo ≤ −2 | t_placebo = −0,55 (écart −0,007, IC 95 % [−0,033 ; +0,019]) | **Non** : pas de fuite, pas d'effet d'échelle significatif |
| 3. B pire que HAR : t_aSPA ≥ +2 | t = +0,06 | Non |
| 4. Équivalence (TOST, Δ = 0,01) | IC 90 % [−0,091 ; +0,097] ⊄ [−0,01 ; +0,01] ; MDE 0,160 > Δ | **Non concluable** |
| **Verdict** | | **Sans pouvoir de conclure** |

### 10.2 Constats par horizon (écart = QLIKE de B − QLIKE de HAR ; < 0 : B meilleure)

| Horizon | Écart | Erreur-type | t (ν) | p | IC 95 % | n effectif | MDE (80 %) | Écart / MDE | Holm |
|---|---|---|---|---|---|---|---|---|---|
| 5 jours | **−0,018** | 0,013 | −1,34 (37) | 0,19 | [−0,045 ; +0,009] | 340 | **0,039** | 47 % | non rejeté |
| 22 jours | −0,009 | 0,038 | −0,25 (37) | 0,81 | [−0,086 ; +0,067] | 206 | 0,108 | 9 % | non rejeté |
| 63 jours | +0,054 | 0,095 | +0,56 (36) | 0,58 | [−0,139 ; +0,246] | 84 | 0,273 | 20 % | non rejeté |
| 126 jours | −0,014 | 0,067 | −0,20 (18) | 0,84 | [−0,155 ; +0,128] | 44 | 0,200 | 7 % | non rejeté |
| **aSPA (moyenne)** | +0,003 | 0,054 | +0,06 (18) | 0,95 | [−0,111 ; +0,117] | 63 | 0,160 | 2 % | — |

- **Ordre des titres (IC)**, B contre HAR : 49,8 % contre 47,4 % (5 j) ; 68,6 % contre 65,2 % (22 j) ; 76,2 % contre 73,4 % (63 j) ; 77,8 % contre 74,9 % (126 j).
  B classe mieux à **tous** les horizons (+2,4 à +3,4 points), comme l'IA publiée.
- **Crises** (écart moyen de la moyenne sur les horizons) : 2008-2009 −0,061 (B meilleure) ; 2011 −0,027 ; 2015-2016 −0,031 ; fin 2018 +0,194 ;
  **2020 +0,782** (B très mauvaise) ; 2022 +0,031. Même défaut que § 8 : l'IA de niveau se trompe le plus lors d'un choc soudain (Covid).
- **Blocs de dates** (moyenne de d_t) : −0,042 ; −0,130 ; **+0,197** ; −0,013. Le bloc défavorable contient le Covid.

### 10.3 Lecture, selon la grille écrite à l'avance (§ 4.13)
- **Ligne « t_aSPA entre −2 et +2, MDE > 0,02 »** : **sans pouvoir de conclure**. Pas de preuve d'un gain de B sur HAR, pas de preuve du contraire.
- **Le multi-horizon n'a pas apporté la puissance espérée.** Plus de périodes indépendantes (n effectif 340 à 5 jours, 206 à 22 jours) mais des pertes beaucoup
  plus bruitées : la volatilité réalisée sur 5 ou 22 jours est elle-même très imprécise. Le MDE mesuré à 22 jours (**0,108**) est 4 à 5 fois l'estimation
  a priori (0,02 à 0,03). L'estimation a priori du § 4.13 supposait un bruit par observation comparable à celui de 126 jours ; c'était faux.
- **Seul indice** : à 5 jours, B fait −0,018 (t = −1,34, p = 0,19), soit 47 % du MDE. Ce n'est **pas** une piste au sens de la règle 1, et ce n'est pas un
  signal : à retenir seulement comme l'horizon où un futur test aurait le plus de chances de voir quelque chose.
- **Placebo** : non significatif (t = −0,55). La précision de lecture de 13 h 20 n'a pas eu à servir. Contrairement au § 8, l'effet d'échelle du placebo
  ne ressort pas ici (son écart, −0,007, est dans le bruit).
- **Ordre des titres** : le gain d'IC de B (+2,4 à +3,4 points) se retrouve à tous les horizons. C'est cohérent avec l'IA publiée, qui garde l'ordre dans l'hybride.

### 10.4 Décision
Aucun changement. L'hybride (ordre de l'IA, niveau de HAR) reste en place. Bilan des trois essais sur le niveau (§§ 8, 9, 10) : **aucune IA ni recalibration
ne bat HAR de façon détectable sur le niveau, à aucun horizon de 5 jours à 6 mois**. Avec les seuls cours passés, c'est la limite de l'information
disponible, pas celle du modèle.

### 10.5 Limites
- Poids égaux entre horizons (arbitraires, déclarés) ; test uniforme uSPA absent (remplacé par Holm).
- Les dates communes aux 4 horizons se chevauchent entre horizons : l'EWC à ν = 18 en tient compte de façon approximative.
- Un seul tirage de placebo.
- Données Yahoo : reproductibilité à la 3ᵉ-4ᵉ décimale (§ 9).

### 10.6 Suite
La seule voie restante est une **information nouvelle** : l'essai HAR-X (§ 4.14, avec son additif de 14 h 10 sur la puissance), qui ajoute la volatilité implicite (VIX).
Le multi-horizon est retiré des essais lancés par défaut : c'était un essai de recherche ponctuel, pas un re-test du produit. Le relancer chaque mois
reviendrait à regarder plusieurs fois la même hypothèse.

