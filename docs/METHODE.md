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
| **Biais du survivant** | **Partiellement** évité : à chaque date, seuls les membres du S&P 500 **de cette date** (`data/sp500_historique.csv`). Mais jusqu'au § 4.22, le laboratoire ne téléchargeait que les titres de l'univers **actuel** : 48 % des membres de 2008 seulement (§ 18). |

Familles d'essais (chacune a son propre seuil corrigé) : rendement, risque, portefeuille, régime de marché.
Tous les essais sont enregistrés dans la table Supabase `experiences` (onglet Analyse › Modèles IA › Laboratoire).

---

## 2. Hypothèses en vigueur

| Hypothèse | Valeur | Où la régler | Pourquoi |
|---|---|---|---|
| Taux sans risque | Taux des bons du Trésor US à 3 mois (FRED `DGS3MO`), lu à chaque passage ; 4,35 %/an s'il est indisponible (§ 2.1) | Paramètres (appli : « suivre le taux du marché » ou valeur fixe) ; `fred.taux_sans_risque()`, `portefeuille.RF` (repli) | Bons du Trésor US, base du CAPM ; une valeur figée devient fausse avec le temps |
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


### 2.1 Taux sans risque lu sur le marché (règle écrite le 24/11/2026, avant le code ; revue de code, docs/REVUE_2026-11.md)

**Constat.** Le taux sans risque était figé à 4,35 %/an à trois endroits (`portefeuille.RF`, `settings.ts`, `portfolio.ts`). Les taux
courts américains changent de plusieurs points en quelques années : une valeur figée devient fausse sans que rien ne le signale.

**Règle.**
1. **Source** : taux des bons du Trésor US à 3 mois, marché secondaire (FRED, série `DGS3MO`, en % par an), dernière valeur connue.
   C'est la mesure habituelle du « sans risque » du CAPM et de la prime de risque de long terme (5 %, mesurée au-dessus des bons).
2. **Lecture** : à chaque passage du cron (`fred.taux_sans_risque()`). Valeur retenue seulement si elle est plausible
   (entre −1 % et 20 %) et datée de moins de 15 jours ; sinon **4,35 %** (`portefeuille.RF`), et le passage est noté « partiel ».
3. **Usage serveur** : le portefeuille conseillé (CAPM, frontière, meilleur ratio de Sharpe) utilise le taux du jour. Le taux et sa
   date sont publiés avec le portefeuille (`univers_facteurs.taux_sans_risque`, `taux_sans_risque_date`).
4. **Usage appli** : par défaut, l'appli suit le taux publié (« suivre le taux du marché ») ; saisir une valeur dans les Paramètres
   la fige, comme avant. Sans taux publié (ancien serveur), 4,35 %.
5. **Ce qui ne change pas** : le laboratoire et les backtests gardent 4,35 % fixe, pour que les essais passés et futurs restent
   comparables entre eux (un essai ne doit pas changer de verdict parce que le taux du jour a bougé).

**Effet attendu.** Le rendement attendu CAPM de chaque titre bouge de 0,9 × Δtaux, le même pour tous : à compromis λ donné, les poids
optimaux ne changent pas (le décalage est le même pour tout portefeuille investi à 100 %). Seuls changent le rendement affiché, le
ratio de Sharpe et donc le point « meilleur ratio de Sharpe » retenu sur la frontière, ainsi que les projections.

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
- **Correction du 23/11/2026 (signalée par l'utilisateur, écrite avant le nouveau calcul)** : l'appli affichait la marge et la part tenue
  de la limite testée la plus proche (10, 12, 15 ou 18 %), calculées seulement avec les niveaux **hybrides**. Pour une limite de 26 %, ou avec la source
  « Historique 3 ans », le chiffre affiché ne correspondait donc pas au choix de l'utilisateur. **Nouveau calcul** (même méthode,
  `backtest_risque.marge_walk_forward`, révision semestrielle) : pour **chaque source** (`hist_3a` et `hybride`) et pour une grille de limites de **8 à 35 %**
  (8, 10, 12, 15, 18, 20, 22, 25, 28, 30, 35 %). L'appli prend la marge et la part tenue **de la source choisie** et de la limite de la grille
  la plus proche, et nomme cette limite si elle diffère. Le verdict de la règle 3 reste calculé, comme avant, sur 10 à 18 % avec la source hybride
  (pas de changement de règle). Résultats : tableau ci-dessous, complété après le calcul.

  **Résultats (run n° 54, 23/11/2026, 37 semestres jugés depuis 2006, révision tous les 6 mois)** — part des semestres où le risque réel est resté sous la limite,
  avec la marge apprise (entre parenthèses : marge actuelle m) :

| Limite | Historique 3 ans | IA + HAR (hybride) |
|---|---|---|
| 8 % | 8 % (0,80) | 3 % (0,89) |
| 10 % | 32 % (0,81) | 5 % (0,89) |
| 12 % | 59 % (0,86) | 22 % (0,89) |
| 15 % | 65 % (0,83) | 57 % (0,89) |
| 18 % | **70 %** (0,91) | 62 % (0,87) |
| 20 % | **70 %** (0,92) | 62 % (0,86) |
| 22 % | **76 %** (0,92) | **70 %** (0,80) |
| 25 % | **70 %** (0,97) | **73 %** (0,80) |
| 28 % | **70 %** (1,04) | **76 %** (0,80) |
| 30 % | **73 %** (1,07) | **84 %** (0,81) |
| 35 % | **78 %** (1,02) | **78 %** (0,80) |

  **Lecture** :
  - En dessous de ~15 %, aucune des deux sources ne tient la limite la plupart du temps. Avec 12 titres au plus, le portefeuille ne peut pas être aussi calme.
  - **Pour les limites basses et moyennes (12 à 20 %), l'historique tient mieux la limite que la prévision IA + HAR.** La prévision juge certains titres plus calmes,
    et ils le sont moins en crise.
  - Au-delà de 22 %, les deux sources tiennent la limite 70 à 84 % des semestres. L'objectif de la règle 3 (70 %) est atteint dès 18 % avec l'historique,
    et dès 22 % avec la prévision.
  - Constat, pas une règle : il n'y a pas de test statistique de l'écart entre sources (37 semestres, fort chevauchement). L'appli affiche le chiffre de la source choisie.

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
  *Précision du 22/11/2026, 20 h 00 UTC, code écrit mais AVANT tout lancement et tout résultat* :
  (1) HAR et HAR-X sont ajustés sur les **mêmes lignes** du passé, celles où β̂ et le VIX existent. Seule la variable x les sépare.
  (2) **Défaut prévisible du placebo** (vu en test sur données simulées) : x = β̂² × VIX² porte **aussi le bêta**, une information propre au
  titre et tirée des cours. Le placebo (VIX d'un an plus tôt) garde ce bêta. Si le bêta seul aide, le placebo battra HAR et la règle 3
  écartera HAR-X **même si le VIX aide aussi**. La règle 3 reste appliquée **telle qu'écrite** (pas de changement de règle). On ajoute un
  **constat** : HAR-X contre son placebo (même bêta, VIX au bon moment ou un an trop tôt). C'est la mesure propre de l'apport du VIX.
  Lecture fixée à l'avance : placebo significatif **et** HAR-X nettement meilleur que son placebo (t ≤ −2) veut dire « le bêta aide, et le
  VIX semble aider en plus ». Cela reste écarté ici, mais c'est la question que tranche le § 4.15.
  (3) Nombre total d'essais pour `t_max_attendu` : **10** (8 jusqu'au § 9, plus le multi-horizon, plus HAR-X).
- **Résultats** : § 11.

### 4.15 Conseils externes (revue du 22/11/2026) et essai « HAR étendu » (protocole écrit AVANT tout code et tout résultat de HAR-X ; règles v2 du § 4.12)

**Revue des conseils reçus (Gemini, 22/11/2026), point par point, contre l'état du projet**

| Conseil | État chez Thésée | Décision |
|---|---|---|
| Cible = variance moyenne sur tout l'intervalle [t+1, t+h], pas un point isolé | **Déjà le cas** : `brut` = écart-type des rendements de t+1 à t+h, annualisé (`modele_risque.cible_risque`) | Rien à changer |
| Correction de Jensen si on modélise log(RV) | HAR travaille en variance (pas de log) ; seule la variante B (§ 8) travaillait en log, et elle est écartée | Rien à changer |
| Ridge / ElasticNet en panel | HAR est **déjà estimé en panel** (tous les titres ensemble). Avec ~300 000 lignes pour ~15 variables, une pénalité ne change presque rien | Moindres carrés gardés ; effets fixes de secteur **testés** (§ 4.15) |
| HAR étendu : retards 126 et 252 jours, semivariance négative, VIX, VRP, pente des taux, écart de crédit | Seul le VIX est protocolé (§ 4.14) | **Testé en un seul modèle** (§ 4.15) |
| VIX à 6 mois / 1 an (`^VIX6M`, `^VIX1Y`) | Séries qui commencent vers 2007-2008 : l'entraînement commence en 1998 | Écarté (historique trop court) ; `^VIX` seul |
| Écart de crédit à haut rendement (HY OAS, ICE) | FRED ne diffuse plus que ~3 ans d'historique de ces séries | Remplacé par `BAA10Y` (depuis 1986), déjà utilisé par le modèle de régime |
| GARCH-MIDAS | GARCH(1,1) a déjà perdu contre HAR (§ 6.1) ; la part « macro lente » est couverte par le crédit et la pente du § 4.15 | Non retenu |
| Changement de régime (Markov-Switching HAR, HMM) | Le modèle de régime de marché n'a pas battu le hasard (AUC 52 %) | Non retenu |
| Prévision itérée (pas journalier, puis itération jusqu'à h) | Résultats mitigés dans la littérature (Marcellino, Stock et Watson 2006) ; ajouterait un essai | Non retenu pour l'instant (pourrait être protocolé plus tard) |
| Horizon 252 jours | Le produit révise tous les 6 mois ; à 1 an, il n'y aurait que ~18 périodes indépendantes, donc encore moins de puissance qu'à 126 jours (MDE ≈ 0,2 pour B) | Non testé |
| Données point-in-time, normalisation dans le pli, walk-forward avec embargo = h | **Déjà le cas** (membres du S&P 500 à la date, ajustements sur le passé, embargo = horizon) ; FRED décalé d'un jour (publication) au § 4.15 | Rien à changer |
| QLIKE log σ̂² + σ²/σ̂² | Même perte à une constante près (la nôtre vaut 0 si la prévision est parfaite) : mêmes écarts, mêmes tests | Rien à changer |
| Diebold-Mariano avec Newey-West + correction de Harvey-Leybourne-Newbold | Chevauchement très fort (126 jours, une date par semaine) : Newey-West sous-estime alors l'erreur. On utilise **EWC + loi de Student** (Lazarus, Lu, Stock et Watson 2018), mieux calibré dans ce cas | Gardé |
| R² hors échantillon contre HAR, analyse calme / stress | Crises déjà rapportées | R² hors échantillon ajouté en **constat** |
| Refonte en modules (`src/models`, `backtest.py`…) | Les modules existants (`examen_risque`, `inference`, `experiences`) ont produit tous les résultats publiés ; les refondre maintenant romprait la reproductibilité | Reporté |

**Ce que ces conseils ne règlent pas** : le frein principal est la **puissance**, pas le choix du modèle. Il y a ~36 semestres indépendants
depuis 2008, et le MDE à 126 jours vaut 0,05 (modèles proches de HAR) à 0,20 (modèles éloignés). Tester cinq familles de modèles ajouterait
cinq essais (seuil plus haut, `t_max_attendu`) sans ajouter de données. D'où **un seul** modèle ci-dessous, qui regroupe les variables
proposées, et une décomposition pour savoir d'où viendrait un gain.

**Essai « HAR étendu »**
- **Question** : les cours passés au-delà de HAR (M1), puis l'information de marché tournée vers l'avenir ou macro (M2), améliorent-ils le
  niveau prévu à **126 jours** ?
- **Modèles** (moindres carrés sur le passé, en variance, cible `brut² / 252`, même garde-fou `v63 × 0,25`, aucun réglage) :
  - **HAR** : v1, v5, v22, v63.
  - **M1 = HAR + cours** : v126 et v252 (moyennes de r² sur 126 et 252 jours) ; semivariance négative sur 22 jours (moyenne de r² les jours
    de baisse ; version quotidienne de Patton et Sheppard 2015) ; `x_beta = β̂² × variance quotidienne du SPY sur 22 jours` (part « marché »
    vue par les cours) ; indicatrices de secteur (secteur actuel : limite reconnue).
  - **M2 = M1 + marché et macro** : `x_vix` du § 4.14 ; `credit × v63` et `pente × v63` (BAA10Y et T10Y2Y, FRED, valeur de la **veille**).
    La macro module ainsi le niveau propre de chaque titre. Le VRP n'est pas ajouté : β̂² × VRP = `x_vix − x_beta`, déjà combinaison des
    deux variables présentes.
- **Statistique primaire** (un seul test) : `d_t = QLIKE_M2 − QLIKE_HAR` par date, à 126 jours, `inference.rapport_dm`.
- **Règles de décision, fixées AVANT l'essai**
  1. **Piste** : t ≤ −2, et d moyen < 0 dans au moins 3 des 4 fenêtres.
  2. **Candidat** : (a) p unilatéral < 0,5 % ; (b) écart ≤ −0,01 ; (c) ratio de QLIKE M2 / HAR ≤ 1,10 en 2008-2009 **et** en 2020 ; (d) MDE ≤ 0,03 ;
     (e) réplication sur le S&P MidCap 400 avec t ≤ −2 (sans indicatrices de secteur, faute de secteurs ; calculée seulement si (a) à (d) tiennent).
  3. **Placebo** : M2 dont les seules variables de marché et macro (VIX, crédit, pente) sont **décalées de 252 jours**. Il garde la forme et les
     degrés de liberté de M2, mais l'information arrive au mauvais moment. **Règle** : le placebo ne doit pas battre M1 (t > −2). Sinon le gain
     de M2 sur M1 vient des degrés de liberté, pas de l'information : la part « marché et macro » est écartée. On garde alors au mieux M1,
     comme piste.
  4. **Pire que HAR** si t ≥ +2.
  5. **Constats** : M1 contre HAR et M2 contre M1 (DM), M2 contre son placebo, coefficients par fenêtre (signe stable ?), biais médian, IC,
     ratio par crise (dont 2022), R² hors échantillon par rapport à HAR (1 − MSE / MSE_HAR), `t_max_attendu` pour **11** essais.
  6. Un candidat est **proposé** au remplacement du niveau de l'hybride. Rien ne change dans l'appli sans décision écrite de l'utilisateur et PR séparée.
- **Puissance annoncée a priori** : M2 reste proche de HAR, donc on attend un MDE de l'ordre de 0,05 (comme HAR × k au § 9). La règle 2 (d)
  rend « candidat » improbable. L'issue la plus probable si les variables aident : une **piste**.
- **Lecture (à l'avance)**

| Observation | Conclusion |
|---|---|
| M1 bat HAR, M2 ne bat pas M1 | Les cours ont encore de l'information (retards longs, baisses, bêta) ; le marché et la macro n'ajoutent rien de visible |
| M2 bat M1, placebo ne bat pas M1 | Le VIX ou la macro apportent une vraie information d'avenir |
| Placebo bat M1 | Gain de degrés de liberté : part « marché et macro » écartée |
| Rien ne bat HAR, MDE > 0,03 | Sans pouvoir de conclure : HAR reste, et les données publiques ne permettent pas de trancher à 6 mois |
| Coefficients de signe changeant selon les fenêtres | Relation instable : écarté |

- **Limites** : secteur actuel (pas historique) ; semivariance quotidienne (pas intrajournalière) ; un seul VIX pour tous les titres ; FRED peut
  réviser `BAA10Y` (rare, données de marché) ; midcaps sans composition historique.
- **Résultats** : § 12.

### 4.16 Essai « Confirmation de HAR-X à 1 mois » (protocole écrit le 22/11/2026, AVANT tout code ; règles v2 du § 4.12)
- **Origine** : au § 11, HAR-X bat HAR à 22 jours (−8 % de QLIKE, t = −3,20, Holm < 0,5 %, 4 fenêtres sur 4, placebo propre). C'est une **piste** :
  le § 4.14 et sa grille demandent une confirmation sur des données jamais utilisées avant tout affichage. L'utilisateur veut un « risque du mois
  à venir » dans l'appli, s'il est confirmé.
- **Question** : le gain du VIX à 22 jours se retrouve-t-il sur des titres que le § 11 n'a jamais vus ?
- **Données** : **S&P MidCap 400** (`universe.get_sp400_tickers`), cours depuis 1998, sans composition historique (biais du survivant reconnu).
  Même code que le § 11 : `walk_forward_harx` (HAR et HAR-X ajustés sur les mêmes lignes, 4 fenêtres, embargo = horizon), `ajouter_x_vix`,
  bêta brut sur 1 an contre le SPY. Horizon **22 jours** seulement. Aucun réglage.
- **Multiplicité** : 12ᵉ essai de la famille « références » ; un seul test confirmatoire (les midcaps), donc pas de correction supplémentaire.
- **Règles de décision, fixées AVANT l'essai**
  1. **Confirmé** si, sur les midcaps à 22 jours, toutes ces conditions tiennent : (a) t ≤ −2 et écart moyen < 0 ;
     (b) d moyen < 0 dans au moins 3 des 4 fenêtres ; (c) placebo (VIX décalé de 252 jours) : t > −2 ; (d) coefficient du VIX de même signe dans les 4 fenêtres.
  2. Sinon : **non confirmé**. Rien n'est affiché dans l'appli, et le § 11 reste une piste.
  3. **Constats** (pas des conditions) : le même essai sur le S&P 500 (reproduction du § 11, sur des cours re-téléchargés) ; biais médian prévu / réel ;
     **couverture** : part des couples (titre, date) où la baisse réalisée sur 22 jours dépasse le « mauvais cas 5 % » de HAR-X (loi de Student à
     5 degrés, même loi que la projection de l'appli, rendement moyen supposé nul). Si cette part dépasse **7,5 %** (1,5 × 5 %, même seuil que la
     règle 5 de la PR #27), l'appli l'écrit à côté du chiffre.
  4. **Re-test mensuel** : l'essai rejoint les re-tests du laboratoire (le 2 de chaque mois). L'appli affiche le risque du mois seulement si le
     **dernier** verdict est « confirmé ».
- **Lecture (à l'avance)**

| Observation | Conclusion |
|---|---|
| Confirmé | Le VIX aide à 1 mois au-delà du S&P 500 : affichage du « risque du mois à venir », avec son test |
| Midcaps t entre −2 et 0 | Gain non retrouvé ailleurs : peut-être propre aux grandes valeurs ou à la période, pas d'affichage |
| Placebo significatif sur les midcaps | Gain de degrés de liberté : écarté |
| Couverture > 7,5 % | Affiché si confirmé, avec l'avertissement « le mauvais cas a été dépassé X % des mois » |

- **Limites** : midcaps sans composition historique ; un seul VIX pour tous ; le bêta des midcaps est estimé contre le SPY.
- **Résultats** : § 15.

### 4.17 Essai « Confirmation de HAR-X à 1 mois, données nettoyées » (protocole écrit le 22/11/2026, après le résultat du § 15 et AVANT tout code ; décision de l'utilisateur)
- **Origine** : la confirmation du § 4.16 est « non confirmée » (§ 15), mais **non informative**. Sur les midcaps, la QLIKE de HAR vaut 5,43, contre 0,36 sur
  le S&P 500, et le MDE vaut 3,77, contre ~0,03 pour l'effet attendu. Quelques cours aberrants dominent la perte. L'utilisateur demande un nouvel
  essai, avec un **nettoyage d'abord** et une normalisation seulement en second recours.
- **Honnêteté** : c'est un **13ᵉ essai compté**. La règle de nettoyage est écrite ici, avant tout code et avant de regarder les données nettoyées.
  Elle porte sur la **qualité des données**, pas sur le résultat, et s'applique à l'identique aux deux univers et à l'entraînement comme au test.
  Le résultat est **définitif** dans les deux sens : pas de 3ᵉ tentative.
- **Étape 1 — Nettoyage** : on retire un couple (titre, date) si (i) le cours de clôture à la date est < 5 $, ou (ii) un rendement quotidien du titre dépasse
  ±50 % entre t − 63 et t + 22 séances. Ces cas sont des titres en détresse, des cours aberrants ou des divisions mal ajustées. La part retirée est rapportée
  pour chaque univers.
- **Étape 2 — Normalisation (seulement si l'étape 1 reste non informative)** : elle est déclenchée **uniquement** si le MDE des midcaps après nettoyage
  dépasse **0,10**. C'est un critère de puissance, jamais le signe ou la valeur de t. La perte de chaque date devient alors la moyenne des QLIKE
  **winsorisées** aux centiles 1 % et 99 % des titres de cette date, pour HAR, HAR-X et le placebo. Une seule étape est retenue comme résultat : la
  dernière exécutée.
- **Règle de décision** (identique au § 4.16, sur les midcaps à 22 jours) : (a) t ≤ −2 et écart < 0 ; (b) d moyen < 0 dans ≥ 3 fenêtres sur 4 ;
  (c) placebo t > −2 ; (d) coefficient du VIX de même signe dans les 4 fenêtres. **Confirmé** : affichage du « risque du mois à venir ». **Sinon** :
  abandon définitif de cet affichage.
- **Constats** : reproduction sur le S&P 500 avec le même traitement ; couverture du mauvais cas 5 % ; biais médian ; part des données retirées ;
  étape retenue (1 ou 2).
- **Re-test mensuel** : cet essai remplace celui du § 4.16 dans les re-tests du laboratoire. L'appli suit son dernier verdict.
- **Résultats** : § 16.

### 4.18 Suivi en conditions réelles du risque du mois à venir (protocole écrit le 23/11/2026, AVANT tout code)
- **Pourquoi** : les §§ 15 et 16 jugent HAR-X sur le passé. La preuve la plus forte, ce sont des prévisions **enregistrées** au moment où elles sont faites,
  puis comparées à ce qui arrive : aucune donnée jugée n'a pu servir à l'ajustement. C'est la même idée que le suivi réel de l'IA à 6 mois (§ 6, `suivi_volatilite`).
- **Enregistrement** : une fois par semaine au plus, le serveur enregistre pour chaque titre publié la prévision HAR-X à 22 séances (`vol_harx`) **et**
  celle de HAR seul (`vol_har`). Les deux sont ajustées sur les mêmes lignes, et seule la variable VIX les sépare. Table `suivi_risque_mois`
  (date, titre, vol_harx, vol_har), lecture publique. Rien n'est jamais réécrit après coup.
- **Jugement** : seules les prévisions dont les 22 séances suivantes sont connues sont jugées. Volatilité réalisée des séances t+1 à t+22
  (`cible_risque`, comme au laboratoire). Par date, `d_t` = moyenne sur les titres de QLIKE(vol_harx) − QLIKE(vol_har). Test `inference.rapport_dm`, avec un
  chevauchement de 22/5 dates.
- **Règles de décision, fixées AVANT les données**
  1. Tant qu'il y a **moins de 26 dates jugées** (≈ 6 mois) : verdict « en attente », aucune conclusion.
  2. **t ≤ −2** : « HAR-X meilleur en conditions réelles ».
  3. **t ≥ +2** : « HAR-X moins bon en conditions réelles ». **Garde-fou** : le risque du mois à venir n'est plus publié, même si le re-test mensuel
     du laboratoire reste « confirmé ». Le réel prime sur le passé.
  4. Sinon : « pas de différence détectable » (on continue de publier tant que le laboratoire confirme).
- **Constats** (pas des conditions) : couverture du mauvais cas 5 % par titre (même calcul que § 4.16 : z de Student à 5 degrés, rendement moyen nul),
  biais médian, nombre de dates et de titres jugés, date du premier bilan possible.
- **Écart au plan initial, noté avant le code** : la couverture est mesurée **par titre**, comme au laboratoire, et non sur le portefeuille conseillé.
  Le portefeuille change à chaque révision et à chaque réglage de l'utilisateur, ce qui rendrait la mesure ambiguë.
- **Publication** : `model_runs`, kind `risque_mois_reel`. L'appli affiche la ligne « En conditions réelles » dans la carte « Face aux chocs ».

### 4.19 Essai « Le risque baissier se prévoit-il, et dit-il le sens ? » (protocole écrit le 23/11/2026, AVANT tout code)
- **Origine** : l'utilisateur veut savoir si la volatilité à venir sera plutôt « à la baisse » ou « à la hausse ». La volatilité ne dit pas le sens.
  Mais la **part baissière** du risque (semi-variance négative) se mesure. La littérature (Barndorff-Nielsen, Kinnebrock et Shephard 2010 ;
  Patton et Sheppard 2015) la trouve **persistante** et utile pour prévoir le niveau du risque. Elle ne la trouve pas utile pour prévoir le sens des prix.
- **Définition** : sur une fenêtre de jours, `part_baisse` = Σ r² des jours de baisse / Σ r² de tous les jours (0,5 = risque symétrique ; plus de 0,5 = le
  risque vient surtout des baisses). Rendements quotidiens de clôture, aucune estimation, aucun réglage.
- **Données** : membres du S&P 500 à chaque date, une date par semaine depuis 1999, mêmes données que l'examen (`preparer`). Passé : 126 séances avant t.
  Avenir : séances t+1 à t+h, h = **22** et **126**.
- **Tests** (4, famille corrigée par **Holm** à 5 %) : à chaque date, corrélation de rang entre titres (IC) entre la `part_baisse` passée et :
  - **A (persistance)** : la `part_baisse` future, à 22 et 126 jours ;
  - **B (sens)** : le rendement futur du titre relatif à la médiane du jour, à 22 et 126 jours.
  Moyenne des IC par date, `inference.rapport_dm` (EWC, chevauchement h/5 dates).
- **Règles de décision, fixées AVANT l'essai**
  1. **A, « le risque baissier persiste »** à un horizon si l'IC moyen > 0, p corrigé par Holm < 5 % **et** IC > 0 dans au moins 3 des 4 blocs de dates.
     Alors l'appli peut afficher la part baissière passée comme **indication** du risque baissier à venir, avec l'IC mesuré.
  2. **B, « il prévoit le sens »** à un horizon si |IC| > 0, p corrigé par Holm < 5 %, même signe dans au moins 3 des 4 blocs, **et IC ≥ 2 %** en valeur
     absolue (minimum économique : en dessous, l'avantage disparaît dans les frais). Sinon l'appli continue de dire que **le sens n'est pas prévisible**.
  3. **Placebo** : même calcul avec la `part_baisse` passée **mélangée entre titres** à chaque date. Son IC doit être non significatif (|t| < 2) pour A et B.
     Sinon : fuite ou artefact, essai écarté.
- **Constats** : marché seul (SPY), où la `part_baisse` passée est comparée au rendement futur du SPY à 126 jours. C'est un constat seulement : il y a environ 36 semestres
  indépendants, donc pas de puissance. Corrélation part passée / part future du portefeuille conseillé si disponible. `t_max_attendu` pour 15 essais.
- **Lecture (à l'avance)**

| Observation | Conclusion |
|---|---|
| A oui, B non | Résultat attendu : un titre dont le risque vient des baisses le reste un peu, mais on ne sait pas s'il va monter ou baisser |
| A oui, B oui | Indice d'une prime (ou d'une décote) liée au risque baissier ; à confirmer sur les midcaps avant tout usage pour choisir des titres |
| A non | La répartition hausse / baisse du risque passé n'informe pas sur l'avenir : l'appli la montre comme une mesure du passé, sans plus |
| Placebo significatif | Artefact : écarté |

- **Limites** : rendements de clôture (pas intrajournaliers) ; secteur et taille non contrôlés (constat seulement) ; survivants des midcaps non utilisés ici.
- **Résultats** : § 17.


### 4.20 Fidélité laboratoire / production de la prévision de volatilité (écrit le 24/11/2026, avant le code ; correction, pas un essai)
- **Constat de la revue de code** : la prévision publiée ne passait pas les mêmes données au modèle que le laboratoire qui l'a validé.
  1. **Classement des titres** : au laboratoire, chaque caractéristique est un rang **parmi les membres du S&P 500 du jour**
     (`membres_a_date`). En production, le jour de la prévision, le rang était calculé **parmi tout l'univers de l'appli** (S&P 500,
     Nasdaq-100 hors S&P 500, ETF sectoriels). Les ETF (diversifiés, donc calmes) décalaient ainsi les rangs de tous les titres.
  2. **Date des caractéristiques** : le modèle classait les titres avec la dernière date **échantillonnée** (une par semaine), jusqu'à 4 séances
     avant le dernier cours, alors que les niveaux HAR étaient ceux du dernier jour.
- **Correction** (aucune nouvelle information, aucun réglage) :
  1. Caractéristiques calculées **au dernier jour de cours**.
  2. **Membres du S&P 500 du jour** : rangs recalculés parmi eux seuls, comme au laboratoire. **Autres actions** (Nasdaq-100 hors S&P 500) : rang
     = place de leur valeur parmi les membres (aucune ne déplace celui des membres). **ETF** : pas de classement par l'IA (elle n'a appris que sur
     des actions) ; leur niveau est celui de HAR (ou la volatilité 3 mois si l'IA seule est publiée).
  3. Rang → niveau : quantile des niveaux **des membres** (la population sur laquelle le rang est défini).
- **Ce qui ne change pas** : le modèle, ses réglages, ses données d'entraînement, le laboratoire. Les verdicts passés restent valables : ils portaient
  déjà sur la version « membres du jour ».

### 4.21 Audit des biais de la prévision de risque (protocole écrit le 24/11/2026, AVANT tout code ; constats, aucun essai compté)
- **Origine** : l'utilisateur veut vérifier que l'IA de risque n'est pas biaisée. Un biais de niveau **par type de titre** a une conséquence directe :
  Markowitz **favorise** les titres dont le risque est sous-estimé. Le § 6 a déjà mesuré l'IC par secteur et par taille, et le biais médian global ;
  il manquait la **calibration par groupe** (celle qui compte pour le portefeuille) et sa stabilité dans le temps.
- **Données** : le walk-forward de l'examen (`walk_forward`, 4 fenêtres de test depuis 2008), mêmes titres et mêmes dates que `examen_hybride`.
  Prévision jugée : **l'hybride publié** (ordre de l'IA, niveau HAR), et HAR seul pour comparaison.
- **Mesures, par groupe** (secteur actuel ; quintiles de taille `liquidite`, de bêta `beta_1a`, de volatilité passée `vol_3m` ; année) :
  1. **Rapport de variance** = moyenne(σ prévue²) / moyenne(σ réalisée²) : la calibration **en moyenne**, celle que Markowitz utilise
     (1 = juste ; < 1 = risque sous-estimé). Aussi : biais médian de σ (constat seulement, car asymétrie attendue, § 9), part de sous-estimations,
     QLIKE de l'hybride et de HAR.
  2. **IC dans le groupe** (titres du groupe classés entre eux) : l'IA classe-t-elle bien **à l'intérieur** d'un secteur, ou seulement d'un secteur à l'autre ?
  3. Le rapport de variance **par fenêtre de test** (4 fenêtres), pour la stabilité.
- **Alertes, fixées AVANT l'audit** (ce ne sont pas des décisions) :
  - **Sous-estimation persistante** d'un groupe : rapport de variance < **0,85** dans au moins **3 des 4 fenêtres**.
  - **Surestimation persistante** : rapport > **1,25** dans au moins 3 des 4 fenêtres.
  - **Classement creux** : IC dans le groupe de l'IA **inférieur** à celui de HAR dans au moins 3 des 4 fenêtres.
  Une alerte ne change rien à l'appli : elle déclenche la **proposition** d'un essai de correction (protocole à écrire, accord de l'utilisateur).
- **Constats complémentaires** :
  - **Biais du survivant** : par année, part des membres du S&P 500 de la date pour lesquels Yahoo fournit un cours (les titres disparus manquent).
  - **IC dans les secteurs** (moyenne des IC calculés secteur par secteur) contre IC global, pour l'IA et HAR.
- **Fréquence** : chaque mois avec le re-test (`experiences.yml`), pour une surveillance continue.
- **Limites** : secteur **actuel** des titres (pas celui de l'époque) ; titres disparus absents (mesuré par le constat ci-dessus) ; seuils d'alerte
  choisis à l'avance mais sans test de significativité (constats).
- **Résultats** : § 18.


### 4.22 Membres historiques retrouvés : moins de biais du survivant au laboratoire (protocole écrit le 24/11/2026, AVANT tout code ; correction de données)
- **Constat (§ 18)** : le laboratoire ne téléchargeait que les titres de l'univers **actuel**. Filtrer « membres de la date » n'y change rien : un titre
  sorti de l'indice (racheté, rétrogradé, failli) n'était jamais dans les données. Part des membres de l'époque présents : 48 % en 2008, 60 % en 2014,
  72 % en 2018, 97 % en 2026. Les titres absents sont justement ceux qui ont mal fini, souvent les plus risqués.
- **Correction** : le laboratoire télécharge aussi **tous les titres ayant appartenu au S&P 500** (`data/sp500_historique.csv`, 737 symboles sortis).
  Yahoo ne fournit que ceux encore cotés sous le même symbole (rétrogradés, encore indépendants) ; les faillis et rachetés restent absents.
  Tous les examens d'un lot (`lancer_examen`) utilisent ces données : walk-forward, hybride, IA contre HAR, audit, backtests.
- **Garde-fou contre les symboles réattribués** (un symbole sorti peut avoir été repris par une autre société) : un titre n'est gardé à une date que
  s'il a un cours **au moins 80 % des séances** de son année d'appartenance précédente ; les séries qui démarrent après la sortie de l'indice sont ainsi
  écartées d'elles-mêmes (aucune donnée pendant l'appartenance).
- **Règles, fixées AVANT de voir les résultats** :
  1. Les décisions de publication restent celles des examens existants (`examen_hybride`, `examen_ia_contre_har`, règles des §§ 4.8 et 4.9), désormais
     calculées sur les données corrigées. **Si une décision change**, la nouvelle s'applique (c'est la plus honnête), et l'appli suit au passage suivant.
  2. Constats : couverture du survivant avant / après, par année ; IC et QLIKE de l'IA et de HAR avant / après ; alertes de l'audit avant / après.
- **Production** : la prévision publiée reste entraînée sur l'univers actuel (télécharger 1 200 titres trois fois par jour est trop lourd). Si les
  constats montrent un écart d'IC de l'IA > 0,02 entre les deux jeux de données, un entraînement hebdomadaire sur les membres historiques sera proposé.
- **Limites** : faillis et rachetés absents de Yahoo (biais résiduel, mesuré) ; secteur inconnu des titres sortis (groupe « ? » dans l'audit).
- **Résultats** : § 19.

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


---

## 11. Résultats de l'essai « HAR-X : HAR + VIX » (PR #28, lot du 22/11/2026 20:10 UTC, run n° 45)

Protocole : § 4.14 avec son additif (14 h 10) et ses deux précisions (21/11 et 22/11, 20 h 00), toutes commitées avant le lancement. 488 titres,
cours depuis 1999 ; 919 à 935 dates de test selon l'horizon, du 20/02/2008, 4 fenêtres, membres du S&P 500 à chaque date. Journaux sans
`[LABO][ERREUR]`. Durée : 89 s (moindres carrés seulement). Réplication midcaps non calculée (règles 2 (a) à (c) non réunies à 126 jours).

### 11.1 Règles de décision (§ 4.14) — d = QLIKE(HAR-X) − QLIKE(HAR) ; < 0 : HAR-X meilleur

| Règle | 126 jours (primaire) | 22 jours (secondaire) |
|---|---|---|
| 1. Piste : t ≤ −2 et d < 0 dans ≥ 3 fenêtres sur 4 | t = −0,86 ; 3/4 → **non** | t = **−3,20** ; **4/4** → **oui** |
| 2 (a). p unilatéral corrigé par Holm < 0,5 % | p = 0,20 → non | p = 0,0014 < 0,0025 (seuil Holm) → rejet (constat : la règle 2 ne vise que 126 j) |
| 2 (b). Écart ≤ −0,01 | −0,013 → oui | −0,029 |
| 2 (c). Ratio de QLIKE ≤ 1,10 en 2008-2009 et 2020 | 0,89 et 1,01 → oui | 0,79 et 0,99 |
| Additif : MDE ≤ 0,03 (sinon ni candidat ni équivalence) | MDE **0,045** → non | MDE 0,026 → oui |
| 3. Placebo (VIX d'un an plus tôt) ne bat pas HAR : t > −2 | t = +0,62 → oui | t = +1,19 → oui |
| 4. Pire que HAR : t ≥ +2 | non | non |
| Coefficient du VIX de signe stable | oui (0,40 à 0,60) | oui (0,72 à 0,83) |
| **Verdict** | **Sans pouvoir de conclure** | **Piste** |

À 5 jours (constat) : écart +0,003, t = +0,24, MDE 0,041. Rien.

### 11.2 Constats

| Mesure | 126 jours | 22 jours |
|---|---|---|
| QLIKE HAR → HAR-X | 0,3327 → 0,3195 (−4 %) | 0,3574 → 0,3286 (**−8 %**) |
| IC 95 % de l'écart | [−0,045 ; +0,019] | [−0,047 ; −0,011] |
| Écart par fenêtre | −0,013 ; −0,053 ; **+0,029** ; −0,016 | −0,012 ; −0,082 ; −0,009 ; −0,011 |
| HAR-X contre son placebo (apport du VIX lui-même, précision du 22/11) | −0,021, t = −1,18 | **−0,040, t = −3,51** |
| Part de la variance prévue venant du VIX (médiane, par fenêtre) | 10 à 22 % | — |
| Biais médian prévu / réel | HAR +27 % → HAR-X +25 % | — |
| Part de sous-estimations | 23 % → 24 % | — |
| IC (ordre des titres) | 74,8 % → 75,9 % | — |
| Ratio de QLIKE par crise (< 1 : HAR-X meilleur) | 2008-09 0,89 ; 2011 1,15 ; 2015-16 0,93 ; fin 2018 1,00 ; 2020 1,01 ; 2022 0,89 | 2008-09 0,79 ; 2011 0,92 ; 2015-16 0,97 ; fin 2018 **1,30** ; 2020 0,99 ; 2022 0,95 |

`t_max_attendu` pour 10 essais : 1,57. Le t de 22 jours (−3,20) le dépasse nettement ; celui de 126 jours (−0,86) non.

### 11.3 Lecture, selon la grille écrite à l'avance (§ 4.14)
- **22 jours : piste solide.** C'est le **premier résultat significatif sur le niveau** de tout le laboratoire. Il passe même les critères qui seraient ceux d'un
  candidat à cet horizon : p corrigé par Holm < 0,5 %, écart économique, 4 fenêtres sur 4, coefficient stable, placebo propre, crises sans dégât sauf fin 2018.
  Le constat HAR-X contre placebo (t = −3,51) montre que le gain vient bien **du VIX au bon moment**, pas du bêta que porte aussi la variable.
  Ligne de la grille : « Piste à 22 jours seulement → le VIX aide à 1 mois, pas prouvé à 6 mois ; pourrait servir un risque à court terme affiché (à protocoler) ».
- **126 jours : sans pouvoir de conclure.** Le sens est le même (−4 %, 3 fenêtres sur 4, pas pire en crise), mais l'écart ne fait que 29 % du MDE.
  C'est ce que prévoyait la littérature : le VIX anticipe 30 jours, son information s'use sur 6 mois.
- **5 jours : rien.** La volatilité réalisée sur 5 jours est trop bruitée.
- **Défaut prévisible du placebo (précision du 22/11)** : il ne s'est pas produit (placebo t > 0 aux deux horizons). Le bêta seul n'apporte rien au-delà de HAR.

### 11.4 Décision
Aucun changement de l'appli : à 126 jours (l'horizon du produit), HAR-X n'est pas candidat. Le niveau de l'hybride reste HAR.
Une utilisation à 1 mois (« risque du mois à venir ») demanderait son propre protocole, avec réplication sur les midcaps, et la décision de l'utilisateur.

### 11.5 Limites
Un seul VIX pour tous les titres ; bêta sur 1 an ; n effectif 54 à 126 jours ; données Yahoo (reproductibilité à la 3ᵉ-4ᵉ décimale, § 9).

---

## 12. Résultats de l'essai « HAR étendu » (PR #28, même lot et même run que le § 11)

Protocole : § 4.15, commité avant tout code et tout résultat de HAR-X. 919 dates de test à 126 jours, du 20/02/2008. Réplication midcaps non calculée.

### 12.1 Règles de décision (§ 4.15) — d = QLIKE(M2) − QLIKE(HAR)

| Règle | Résultat | Verdict |
|---|---|---|
| 1. Piste : t ≤ −2, ≥ 3 fenêtres sur 4 | t = −0,23 ; 2/4 | **Non** |
| 2. Candidat (a) à (e) | p = 0,41 ; écart −0,006 ; crises 1,28 (2008-09) et 1,25 (2020) ; MDE 0,076 | **Non** (toutes échouent) |
| 3. Placebo (VIX, crédit, pente d'un an plus tôt) ne bat pas M1 | t = **−2,28** | **Échec** : part « marché et macro » écartée |
| 4. Pire que HAR | t = −0,23 | Non |
| **Verdict** | | **Sans pouvoir de conclure ; marché et macro écartés** |

### 12.2 Constats

| Mesure | HAR | M1 (HAR + cours) | M2 (M1 + VIX, crédit, pente) |
|---|---|---|---|
| QLIKE | 0,3327 | 0,3332 | 0,3267 |
| Contre HAR (t) | — | +0,04 | −0,23 |
| R² hors échantillon par rapport à HAR | — | **−4,6 %** | **−6,6 %** |
| IC (ordre des titres) | **74,8 %** | 65,5 % | 67,7 % |
| Ratio de QLIKE 2008-09 / 2020 | 1 / 1 | 1,08 / 1,04 | **1,28 / 1,25** |

- M2 contre M1 : t = −0,38. M2 contre son placebo : t = **+1,03** (M2 fait **moins bien** que sa version au mauvais moment).
- Variables de signe changeant selon les fenêtres : crédit, v1, v252, bêta² × marché. Le poids de v63 passe de 0,74 (fenêtre 1) à 0,19 (fenêtre 4) :
  les retards longs (v63, v126, v252) se disputent la même information.
- Biais médian de M2 : +21 % (HAR : +27 %).

### 12.3 Lecture, selon la grille écrite à l'avance (§ 4.15)
- **M1 ne bat pas HAR** (t = +0,04) : les retards longs, la variance des baisses, le bêta et les secteurs n'apportent rien que HAR n'ait déjà.
- **Placebo qui bat M1** : le crédit et la pente agissent comme des **niveaux lents** (ils changent peu en un an), pas comme une information d'avenir.
  C'est un gain de degrés de liberté, et la grille l'écarte. M2 fait d'ailleurs moins bien que son placebo.
- **Coefficients instables, R² négatif, crises plus mauvaises (×1,25 à ×1,28), ordre dégradé (−7 à −9 points d'IC)** : signature d'un modèle trop riche
  pour ~36 semestres indépendants. **Ajouter des variables a coûté, pas rapporté.**
- Comparé au § 11 : le VIX seul (HAR-X) est meilleur que le VIX noyé parmi dix variables (M2).

### 12.4 Décision
Aucun changement. Les conseils externes du § 4.15 (« HAR étendu ») sont testés et **non retenus**.

### 12.5 Bilan des cinq essais sur le niveau (§§ 8 à 12)

| Essai | Information ajoutée | 126 jours | 22 jours |
|---|---|---|---|
| XGBoost sur HAR (§ 8) | cours passés, non linéaire | sans preuve, pire en crise | — |
| HAR × k (§ 9) | correction d'échelle | sans preuve | — |
| Multi-horizon (§ 10) | cours passés, 4 horizons | sans pouvoir de conclure | sans pouvoir de conclure |
| HAR-X (§ 11) | VIX | sans pouvoir de conclure (même sens) | **piste solide** (t −3,20) |
| HAR étendu (§ 12) | cours + VIX + macro | sans pouvoir de conclure, pire en crise | — |

À 6 mois, **HAR reste le meilleur niveau qu'on puisse justifier**. Les données publiques ne permettent pas de faire mieux de façon prouvable, et les modèles
plus riches font pire en crise. La seule information qui aide vraiment est le VIX, et seulement à 1 mois.

---

## 13. Décision finale du modèle (22/11/2026, décision de l'utilisateur)

Après cinq essais sur le niveau (§ 12.5), le modèle est **figé** :
- **Ordre des titres** : l'IA de volatilité (prouvée, IC 78,3 % contre 74,9 % pour HAR, re-testée chaque mois).
- **Niveau du risque à 6 mois** : **HAR**. C'est le plus simple, aucun concurrent ne le bat de façon prouvable, et il tient en crise.
- **Garde-fous** : marge de sécurité, fourchette en loi de Student à 5 degrés, révision tous les 6 mois (§ 7).

Toute nouvelle tentative sur le niveau à 6 mois devra apporter une **information nouvelle** (pas un modèle de plus sur les mêmes données),
avec un protocole écrit et commité avant le code. Les données publiques actuelles (cours depuis 1998, VIX, crédit, pente des taux) ont été exploitées.

Deux ajouts au produit, décidés le même jour :
1. une carte **« stress test »** qui rejoue les crises passées (§ 14) : pas une prévision, donc rien à prouver statistiquement ;
2. un **« risque du mois à venir »** par HAR-X, **seulement s'il est confirmé** (protocole § 4.16, résultats § 15).

---

## 14. Stress test historique (méthode écrite le 22/11/2026, avant le code)

- **But** : montrer en euros ce que les grandes crises passées auraient fait au portefeuille **actuel**. C'est ce qui aide à tenir pendant un choc.
  Ce n'est **pas une prévision** : aucune règle statistique n'est nécessaire, mais la méthode est fixée avant le code.
- **Fenêtres** : trouvées sur le SPY, sans date choisie à la main, dans six plages de recherche :
  2008 (01/10/2007 – 30/06/2009) ; 2011 (01/04/2011 – 31/12/2011) ; 2015-2016 (01/05/2015 – 29/02/2016) ; fin 2018 (01/09/2018 – 31/12/2018) ;
  2020 (01/02/2020 – 30/06/2020) ; 2022 (01/01/2022 – 31/10/2022).
  **Creux** = plus bas du SPY dans la plage ; **sommet** = plus haut du SPY entre le début de la plage et le creux.
- **Rendement d'un titre** : cours au creux / cours au sommet − 1 (dernier cours connu à chaque date). Pas de cours au sommet (titre absent à l'époque) : `null`.
- **Portefeuille** : somme des poids × rendements, poids fixés au sommet (on garde les titres pendant la chute, comme la révision semestrielle).
  Titre sans cours à l'époque : rendement estimé = bêta (3 ans, celui de l'univers) × chute du SPY. La **part estimée** du portefeuille est affichée.
- **Marché** : chute du SPY du sommet au creux, et **temps de retour** au sommet (jours de bourse jusqu'à un cours ≥ celui du sommet ; `null` si pas encore revenu).
- **Limites (affichées)** : seuls les titres d'aujourd'hui sont rejoués (biais du survivant : les faillites de l'époque n'y sont pas) ;
  rendements de prix sans dividendes ; le bêta d'aujourd'hui peut différer de celui de l'époque ; l'historique du serveur commence en 2005.

---

## 15. Résultats de la confirmation de HAR-X à 1 mois (§ 4.16 ; lot du 22/11/2026 23:23 UTC, run n° 47)

| Condition (midcaps, 22 jours) | Résultat | Verdict |
|---|---|---|
| (a) t ≤ −2 et écart < 0 | écart −1,36 ; **t = −1,04** | **Échec** |
| (b) d moyen < 0 dans ≥ 3 fenêtres sur 4 | 4 sur 4 (−0,004 ; −0,114 ; **−5,330** ; −0,004) | Réussi |
| (c) placebo t > −2 | t = −0,05 | Réussi |
| (d) signe du VIX stable | 0,41 à 0,94, toujours positif | Réussi |
| **Verdict** | | **Non confirmé** (appliqué : rien n'est affiché) |

**Constats** :
- 398 midcaps. QLIKE HAR **5,43** contre HAR-X 4,07, alors qu'elle vaut ≈ 0,36 sur le S&P 500. MDE **3,77**. Biais médian de HAR-X **+69 %**.
- Ratio de QLIKE par crise : tous < 1 (0,84 à 1,00).
- HAR-X contre son placebo : t = −1,04.
- **Reproduction S&P 500** : identique au § 11 (t = −3,20, écart −0,029, placebo t = +1,19).
- **Couverture** : le mauvais cas 5 % n'est dépassé que 0,9 % des mois sur les midcaps et 1,7 % sur le S&P 500. Les prévisions sont **prudentes**.

**Lecture** :
- Le verdict « non confirmé » est appliqué tel qu'écrit.
- Mais l'essai est **non informatif** : un seul bloc de dates (fenêtre 3, écart −5,33) porte presque toute la perte. Avec un MDE de 3,77, aucun effet
  plausible (~0,03) n'était détectable.
- Les signes vont tous dans le sens d'une confirmation (4 fenêtres sur 4, crises, placebo propre), mais ce n'est pas une preuve.
- Cause probable : des cours aberrants ou des titres en détresse dans les données Yahoo des midcaps (sans composition historique), qui donnent des
  volatilités réalisées énormes face à des prévisions normales. La QLIKE punit très fortement ces sous-estimations.

**Décision de l'utilisateur** : un nouvel essai, données nettoyées d'abord (protocole § 4.17, écrit avant tout code, 13ᵉ essai, résultat définitif).

---

## 16. Résultats de la confirmation sur données nettoyées (§ 4.17 ; lot du 22/11/2026 23:51 UTC, run n° 48) : **confirmé**

Étape retenue : **1** (nettoyage seul). Le MDE des midcaps après nettoyage vaut 0,021 < 0,10, donc pas de winsorisation. Données retirées : **4,8 %**
des couples (titre, date) des midcaps, 1,1 % du S&P 500.

| Condition (midcaps nettoyés, 22 jours) | Résultat | Verdict |
|---|---|---|
| (a) t ≤ −2 et écart < 0 | écart **−0,016** (QLIKE 0,340 → 0,324, −4,8 %) ; **t = −2,26** ; IC 95 % [−0,031 ; −0,002] | Réussi |
| (b) d moyen < 0 dans ≥ 3 fenêtres sur 4 | 4 sur 4 : −0,0005 ; −0,036 ; −0,029 ; −0,00002 | Réussi |
| (c) placebo (VIX d'un an plus tôt) t > −2 | t = +1,45 | Réussi |
| (d) signe du VIX stable | 0,64 ; 0,62 ; 0,65 ; **0,0003** (toujours positif) | Réussi |
| **Verdict** | | **Confirmé** : le risque du mois à venir est affiché |

**Constats** :
- **Apport du VIX lui-même** (HAR-X contre son placebo) : t = **−3,17**.
- **Ratio de QLIKE par crise** : 2008-09 0,81 ; 2011 0,87 ; 2015-16 0,98 ; fin 2018 1,06 ; 2020 0,90 ; 2022 0,96.
- **Biais médian** : +25 %.
- **S&P 500 nettoyé (reproduction)** : t = −3,35, écart −0,019 (−5,6 %), placebo t = +1,11.
- **Couverture** : le mauvais cas 5 % n'est dépassé que **1,5 %** des mois sur les midcaps et 1,8 % sur le S&P 500.

**Points d'honnêteté** (affichés ou suivis) :
1. **Seuil passé de justesse** : t = −2,26, pour un seuil à −2. Sur le S&P 500, la preuve est plus forte (t = −3,35).
2. **L'effet s'efface dans la fenêtre la plus récente** (4ᵉ, jusqu'en 2026) : coefficient du VIX ≈ 0 et gain ≈ 0. La règle (d) est réussie à la lettre
   (signe positif), mais le VIX n'a presque rien apporté ces dernières années. C'est pour ça que l'essai est **re-testé chaque mois**. L'appli suit le dernier verdict.
3. **Prévision prudente** : le « mauvais cas 5 % » n'est dépassé qu'environ 1,5 % des mois (biais +25 %). La baisse affichée est plutôt **trop forte** que trop faible.
   L'appli ne montre pas d'avertissement, puisque le seuil d'alerte (7,5 %) n'est pas atteint.
4. Le nettoyage a été décidé **après** le premier résultat (§ 15), mais **avant** de regarder les données nettoyées. Il porte sur la qualité des données
   (cours < 5 $, sauts > 50 %), pas sur le résultat. C'est un 13ᵉ essai compté, et son résultat est définitif.

**Décision** : le risque du mois à venir est publié par le serveur (`univers_facteurs.vol_1m`, avec le VIX et la date) **seulement si** le dernier
`examen_harx_1m_v2` dit « confirmé ». L'appli l'affiche dans la carte « Face aux chocs » de Portefeuille. Il ne change **rien** au portefeuille
(révision tous les 6 mois). Il sert seulement à ne pas être surpris.

### Hypothèses en vigueur (mise à jour du 23/11/2026)
- **Ordre des titres** : l'IA de volatilité. **Niveau à 6 mois** : HAR (§ 13, modèle figé).
- **Risque du mois à venir** : HAR-X (HAR + VIX × bêta²), données nettoyées, re-testé chaque mois sur les midcaps.
- **Stress test** : crises 2008, 2011, 2015-16, fin 2018, 2020 et 2022 rejouées sur le portefeuille (§ 14). Ce n'est pas une prévision.

---

## 17. Résultats de l'essai « Le risque baissier se prévoit-il, et dit-il le sens ? » (§ 4.19 ; lot du 23/11/2026 08:59 UTC, run n° 52)

487 titres membres du S&P 500, 1 378 dates hebdomadaires depuis 1999. Part baissière passée médiane : 47 %. Seuil de Holm à 5 % pour 4 tests.

| Test | IC moyen | t | IC 95 % | Blocs (4) | Holm | Règle | Verdict |
|---|---|---|---|---|---|---|---|
| A, persistance à 22 j | **−2,0 %** | −3,89 | [−3,0 % ; −1,0 %] | 4 négatifs | rejet | exige IC > 0 | **Non persistant** |
| A, persistance à 126 j | **−4,1 %** | −3,88 | [−6,3 % ; −1,9 %] | 4 négatifs | rejet | exige IC > 0 | **Non persistant** |
| B, sens à 22 j | +1,0 % | +1,84 | [−0,1 % ; +2,2 %] | 3 positifs | non (p = 0,07) | IC ≥ 2 % | **Ne prévoit pas le sens** |
| B, sens à 126 j | +0,5 % | +0,45 | [−1,9 % ; +3,0 %] | mixtes | non | IC ≥ 2 % | **Ne prévoit pas le sens** |

- **Placebo** (part mélangée entre titres) : |t| < 2 pour les 4 tests (le plus haut : −1,81). Propre.
- **Constat marché** (SPY) : corrélation de rang entre la part baissière passée et le rendement à 126 jours de −0,10, sur ~54 semestres indépendants. Pas de puissance.
- `t_max_attendu` pour 15 essais : 1,77.

**Lecture, selon la grille écrite à l'avance**
- **Ligne « A non »** : la répartition hausse / baisse du risque passé n'annonce pas un risque baissier durable. L'appli la montre comme une **mesure du passé**.
- **Constat hors règle (à ne pas utiliser comme preuve)** : le lien est significativement **négatif**, à 22 et à 126 jours, dans les 4 blocs. Un titre dont le risque est
  venu surtout des baisses a ensuite, en moyenne, une part baissière un peu **plus faible** : l'asymétrie se résorbe. L'effet est petit (IC −2 à −4 %).
  Le protocole ne prévoyait pas de l'exploiter, et il ne l'est pas.
- **B** : la part baissière ne prévoit pas le sens des rendements, conformément à la littérature. Le léger IC positif à 1 mois (+1 %, non significatif après
  correction) ressemble à l'effet connu de retournement à court terme. Il est sous le minimum économique de 2 %.

**Décision** : la carte « Face aux chocs » affiche la part baissière du risque **sur 1 an** (portefeuille et titres), avec la mention « mesure du passé ;
elle ne se répète pas ; le sens à venir n'est pas prévisible ». Rien ne change dans le choix des titres.

---

## 18. Premier audit des biais (§ 4.21 ; lot du 24/11/2026 20:24 UTC, PR #41, 920 dates de test 2008-2026, 320 000 prévisions)

### 18.1 Calibration du niveau (hybride publié : ordre de l'IA, niveau HAR)
- **En moyenne, presque juste** : rapport de variance prévue / réalisée **1,07** (HAR seul : 1,07). Biais médian de σ +27 % (asymétrie attendue, § 9).
- **Mais très variable dans le temps** : 0,86 ; **1,88** ; 1,01 ; 1,06 selon la fenêtre de test. La deuxième fenêtre (après la crise de 2008) surestime
  le risque de 88 % : HAR, appris sur une période de crise, met du temps à se calmer.
- **Aucune sous-estimation persistante** d'un groupe : le portefeuille n'est **pas attiré** vers des titres dont le risque serait caché. C'était le biais
  le plus dangereux, il n'est pas là.
- **4 alertes de surestimation persistante** (rapport > 1,25 dans au moins 3 fenêtres sur 4) : **Consumer Staples**, **Utilities**, quintile de bêta
  le plus **bas**, quintile de volatilité passée le plus **bas**. Les titres **calmes** sont jugés plus risqués qu'ils ne le sont. Cause probable : HAR est
  estimé en commun pour tous les titres ; sa constante rapproche chaque titre du risque moyen, ce qui gonfle celui des plus calmes.
  Conséquence : Markowitz les **sous-pondère** un peu. C'est prudent, pas dangereux, mais cela coûte de la diversification.

### 18.2 Classement
- IC de l'IA **0,78** contre 0,75 pour HAR, meilleur dans les 4 fenêtres.
- **Dans les secteurs** (titres d'un même secteur classés entre eux) : IA **0,72**, HAR 0,68. L'IA ne se contente pas de classer les secteurs entre
  eux : elle classe aussi mieux les titres à l'intérieur de chacun. Aucune alerte de classement creux.

### 18.3 Biais du survivant : bien plus fort qu'annoncé
- Part des membres du S&P 500 de l'époque présents dans les données : **48 % en 2008**, 55 % en 2011, 62 % en 2015, 72 % en 2018, 83 % en 2022,
  97 % en 2026. Le laboratoire ne téléchargeait que l'univers actuel (§ 4.22).
- Les verdicts passés restent des comparaisons **à données égales** entre méthodes (IA, HAR, GARCH…), mais sur des titres « survivants ».
  Correction : § 4.22.

### 18.4 Suites
1. **§ 4.22** : membres historiques retrouvés (correction de données, en cours).
2. **Proposé (essai compté, accord de l'utilisateur)** : HAR **relatif au titre** (variance rapportée à celle du titre sur un an), pour corriger la
   surestimation des titres calmes (§ 18.1).
3. **Proposé (essai compté)** : donner à l'IA les variances récentes de HAR (1 jour, 1 semaine, 1 mois) et la part baissière, pour mieux classer.

---

## 19. Résultats avec les membres historiques retrouvés (§ 4.22 ; lot du 24/11/2026 20:30 UTC, PR #41)

### 19.1 Biais du survivant : réduit, pas supprimé
| Année | Avant (univers actuel) | Après (+ anciens membres) |
|---|---|---|
| 2008 | 48 % | **61 %** |
| 2011 | 55 % | 66 % |
| 2014 | 60 % | 72 % |
| 2018 | 72 % | 82 % |
| 2022 | 83 % | 91 % |
| 2026 | 97 % | 98 % |

Prévisions jugées : 320 000 → **364 000**. Il reste 39 % de membres de 2008 absents : faillis et rachetés, que Yahoo ne fournit pas.

### 19.2 Les décisions ne changent pas (règle 1 du § 4.22)
- **IA contre HAR sur l'ordre** : IC 0,796 contre 0,767, gain +0,029, t = 5,5 > seuil 2,72 → **l'IA reste** (hybride). Avant : gain +0,034, t = 5,7.
- **Hybride** : **publié** (il classe mieux que la volatilité 3 mois et HAR ne le bat pas au seuil corrigé).
- **Re-test mensuel** (`risque_volatilite`, univers actuel, inchangé) : 6 mois **probant** ; 1 an non probant.
- **Production** : l'IC de l'IA bouge de **+0,013** entre les deux jeux de données, sous le seuil de 0,02 du § 4.22. L'entraînement de production
  reste sur l'univers actuel.

### 19.3 Ce qui change : le niveau est moins bon qu'on le croyait
- **QLIKE de l'hybride 0,413 contre 0,397 pour HAR** (Diebold-Mariano t = **+2,18** : l'hybride est **moins bon** que HAR en niveau, sans franchir
  le seuil corrigé de 2,63). Avant : 0,331 contre 0,332 (t = −1,49). Sur les survivants, convertir l'ordre de l'IA en niveaux HAR ne coûtait rien ;
  avec les titres sortis de l'indice, cela coûte un peu.
- **Calibration** : rapport de variance **1,16** (avant 1,07) ; par fenêtre 0,82 ; **2,37** ; 1,14 ; 1,20.
- **Audit** : **9 alertes**, toutes de **surestimation** (Communication Services, Consumer Staples, Industrials, Real Estate, Utilities ; bêtas et
  volatilités passées des deux quintiles les plus bas). Toujours **aucune sous-estimation persistante**.
- **Classement dans les secteurs** : IA 0,72 contre HAR 0,69 (inchangé).

### 19.4 Lecture
- L'apport de l'IA est **l'ordre** des titres, et il résiste à la correction du biais du survivant.
- Le **niveau** reste le point faible : il surestime le risque des titres calmes, de plus en plus nettement quand on ajoute les titres sortis.
  C'est l'essai « HAR relatif au titre » (§ 18.4, point 2) qui y répond. Il reste à lancer avec l'accord de l'utilisateur.
