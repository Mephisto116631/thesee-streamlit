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
| Volatilité de chaque titre | 3 ans d'historique, ou prévue par l'IA (6 mois) si son dernier test est probant | Portefeuille › « Risque mesuré avec » | Seul modèle probant (§ 4.3) |
| Projection à l'horizon | Log-normale, fourchette de 90 % des scénarios | Paramètres (confiance) | Sous-estime les chocs extrêmes (krachs) : à garder en tête |
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
| Secteurs représentés | 6 | 8 |
| Risque attendu (volatilité) | 20,6 % | 15,5 % |
| Rentabilité de long terme (hypothèse CAPM) | 14,1 % | 12,2 % |
| Données publiées pour l'appli | covariance 40 x 40 | 494 titres, 20 facteurs, 83 Ko |
