# Suivi — essais sur le niveau de volatilité (session du 19-20/11/2026)

Document de reprise pour une nouvelle session (Claude Code). Tout est en français ; l'utilisateur (Medhi) veut des réponses **concises** et une démarche
**méthodique et scientifique**, décrite assez précisément pour tirer des conclusions **même en cas d'échec**. Aucune modification de l'appli ni des modèles publiés n'a été faite.

## 1. État du dépôt et de l'infrastructure

- Dépôt : `Mephisto116631/thesee-streamlit`. `main` a été entièrement refait (appli mobile, IA de risque, hybride IA + HAR, `docs/METHODE.md`).
  L'ancienne architecture (branche `test-modele-relatif`, ex-`DOCUMENTATION.md`) est **abandonnée** : ne pas la fusionner (−18 000 lignes). Suppression de la branche : **non faite**, en attente de l'accord de l'utilisateur (irréversible).
- Branche de travail : **`essai-xgb-niveau`**, **PR #28** (ouverte, non fusionnée). Elle contient uniquement du laboratoire : `examen_risque.py`, `experiences.py`, `inference.py`, tests, `docs/METHODE.md`, `.github/workflows/experiences.yml`.
- Supabase : projet `ommkiaoqnavcxvxsoiwg`, actif. Résultats des essais dans la table `experiences` (colonnes `lot, nom, verdict, ic, t_stat, seuil_t_global, n_essais, diagnostics` jsonb ; pas de `created_at`, trier par `lot`).
- Workflow « Laboratoire — essais du modèle » (`experiences.yml`) : se lance sur chaque PR qui touche les fichiers listés dans `paths`, chaque mois (cron), ou à la main avec l'entrée `experiences`. Durée 12 à 30 minutes. Les modifications de `docs/` seules **ne le déclenchent pas**. Variable `EXPERIENCES` par défaut : `risque_volatilite,examen_hybride,examen_ia_contre_har,examen_multi_horizon`.
- Concurrence : un seul run à la fois (les autres se mettent en file).

## 2. Cadre méthodologique (à respecter)

1. **Pré-enregistrement** : le protocole (hypothèses, variantes, règles de décision, lecture d'un échec) est écrit dans `docs/METHODE.md`, **commité et poussé AVANT** d'écrire ou lancer le code de l'essai.
2. **Jamais de règle modifiée après avoir vu un résultat.** Les nouvelles règles ne s'appliquent qu'aux essais protocolés après leur écriture (non-rétroactivité, § 4.12).
3. Un échec se lit avec la **grille écrite à l'avance** ; un test peu puissant se déclare « sans pouvoir de conclure », jamais « équivalent » (sauf TOST avec MDE < marge).
4. Chaque essai rapporte écart, erreur-type, t, p, IC 95 %, n effectif, écart minimal détectable (MDE). Outils : `inference.py` (`rapport_dm`, `holm`, `t_max_attendu`, `variance_long_terme_ewc`).
5. Les statistiques et résultats sont consignés dans `METHODE.md` (§ 8, 9, 10…) avec la décision prise et les limites.

## 3. Ce qui a été fait

| Essai | Protocole | Résultats | Verdict |
|---|---|---|---|
| XGBoost sur le niveau (B : cible `ln σ − ln σ_HAR` ; A : cible `ln σ` ; placebo) | § 4.10 | § 8 | **B non candidate** : QLIKE 0,3186 contre 0,3325 (HAR), force 8 % (seuil 2,86), crises 2020 ×1,30 et 2022 ×1,65, placebo à la lettre déclenché (il remet HAR à l'échelle : défaut de la règle, pas fuite) |
| HAR remis à l'échelle (un facteur k appris sur le passé) | § 4.11 | § 9 | **Non candidat** : écart −0,0027, force 6 %, 2008-2009 ×1,16, 2 fenêtres sur 4 ; k stable ≈ 0,95 → HAR est déjà calibré en moyenne ; le « biais de 27 % » est un effet d'asymétrie (médiane) |
| Règles v2 de test (littérature : Patton 2011, Giacomini-White 2006, Lazarus et al. 2018, Coroneo-Iacone 2020, Quaedvlieg 2021, Holm 1979, Harvey-Liu 2020…) | § 4.12 | simulation de taille | Test précédent sur-rejetait (NW + normale : 13 % au lieu de 5 % ; naïf : 70 %) ; **EWC avec ν = min(0,4·T^(2/3), T/(2h)) : 5,9 %** |
| Multi-horizon (5, 22, 63, 126 jours ; IA de niveau B contre HAR) | § 4.13 | § 10 | **Sans pouvoir de conclure** : t_aSPA = +0,06, MDE 0,160 ; meilleur indice à 5 jours (−0,018, t −1,34, MDE 0,039) ; MDE à 22 jours 0,108, bien au-dessus de l'estimation a priori ; 2020 très défavorable à B |
| HAR-X : HAR + VIX × β² | § 4.14 (+ additif et précisions) | § 11 | **126 j : sans pouvoir de conclure (−4 %, t −0,86) ; 22 j : piste solide (−8 %, t −3,20, Holm < 0,5 %)** |
| HAR étendu (conseils externes) | § 4.15 | § 12 | **sans pouvoir de conclure ; macro écartée (placebo) ; pire en crise** |

Constat transversal : avec n effectif ≈ 36 à 126 jours, le MDE est ≈ 0,05 à 0,16 de QLIKE, bien au-dessus des écarts discutés (0,003 à 0,014). Les essais disent « pas de gain détectable », pas « pas de gain ». Le panel de titres est **déjà** inclus (l'écart de perte est moyenné par date, estimateur de type Driscoll-Kraay) : pas de gain de puissance de ce côté.

Décision en vigueur : **l'hybride (ordre des titres par l'IA, niveau par HAR) reste en place.**

## 4. À faire ensuite (par ordre)

1. **Fait (22/11/2026)** : multi-horizon (§ 10), HAR-X (§ 11), HAR étendu (§ 12). Bilan au § 12.5 : à 6 mois, HAR reste le meilleur niveau justifiable ;
   le VIX n'aide prouvablement qu'à 1 mois. Requête des résultats : `select lot, verdict, diagnostics from experiences where nom in ('examen_harx','examen_har_etendu') order by lot desc;`
2. **Choix du modèle avec l'utilisateur** : la recherche sur le niveau à 6 mois est close faute de puissance (données publiques épuisées). Décisions à prendre :
   garder l'hybride tel quel ; ou protocoler un « risque du mois à venir » avec HAR-X (réplication midcaps à 22 jours d'abord) ; ou une carte « stress test » historique.
3. Ne pas relâcher les seuils pour « sauver » un résultat ; tout nouvel essai = protocole écrit et commité avant le code.
4. Faire décider l'utilisateur sur : fusion de la PR #28 dans `main` (laboratoire seulement), suppression de la branche `test-modele-relatif`, éventuel keepalive mensuel du workflow `sync.yml`.
5. **Sécurité (en attente depuis longtemps)** : régénérer les clés Supabase et Alpha Vantage, exposées dans une ancienne conversation.

## 5. Pièges rencontrés (gagner du temps)

- `gh pr create` échoue (GraphQL indisponible) → utiliser l'API REST : `gh api repos/Mephisto116631/thesee-streamlit/pulls -f title=… -f head=… -f base=main -f body=…`.
- Le crochet de fin de session signale à tort des commits non poussés (clone superficiel) : `git fetch origin <branche>:refs/remotes/origin/<branche>` puis comparer `git rev-parse HEAD origin/<branche>`.
- Ne pas utiliser `pkill -f` avec un motif présent dans sa propre commande (tue le shell). Ne pas chaîner des `sleep` : utiliser un moniteur (boucle `until`).
- Le calcul n'est pas faisable depuis ce conteneur (Yahoo bloqué) : tout se lance par GitHub Actions. Les tests synthétiques tournent en local (`python3 -m pytest -q tests/test_examen_risque.py tests/test_inference.py`, ≈ 2 minutes pour `test_examen_risque`).
- Les données Yahoo bougent légèrement entre deux runs (3ᵉ-4ᵉ décimale de QLIKE) : deux lots d'un même essai ne sont pas identiques à l'octet.
- **Correction (20/11/2026)** : sur une PR, le filtre `paths` regarde **tout le diff de la PR**, pas seulement le dernier commit. Tant que la PR touche un fichier de `paths`, **chaque** push (même `docs/` seul) relance le laboratoire et annule le run en file. Attendre la fin d'un run avant de pousser quoi que ce soit sur la branche.
- Archive : l'ancienne branche est sauvegardée sous `archive/test-modele-relatif` (même commit `f5eef85`) ; la branche `test-modele-relatif` peut être supprimée depuis l'interface GitHub (l'outil de l'assistant ne peut pas supprimer de branche).
- Préférences de l'utilisateur sur les essais : description méthodique et scientifique de ce qui est fait, règles écrites avant, conclusions tirables en cas d'échec ; réponses courtes.

## 6. Fichiers clés

| Fichier | Rôle |
|---|---|
| `docs/METHODE.md` | Journal de la méthode : §§ 4.8-4.13 (protocoles), 6-9 (résultats), 4.12 (règles v2) |
| `examen_risque.py` | Banc d'essai : HAR, GARCH, EWMA, QLIKE, Diebold-Mariano, `walk_forward_niveau`, `walk_forward_echelle`, `comparer_niveau`, `comparer_echelle`, `comparer_multi` |
| `inference.py` | EWC, MDE, Holm, maximum attendu de t |
| `experiences.py` | Registre des essais (`EXPERIENCES_EXAMEN`) et `lancer_examen` |
| `modele_horizon.py`, `modele_risque.py` | IA de rang (XGBoost prudent, ensemble, CNN), cibles de risque |
| `.github/workflows/experiences.yml` | Lancement du laboratoire |
| `tests/test_examen_risque.py`, `tests/test_inference.py` | Tests synthétiques |
