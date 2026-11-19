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
- **Résultats** : § 7.

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
- **Couverture revérifiée** : voir ci-dessous.
