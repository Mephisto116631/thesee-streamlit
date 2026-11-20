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
| HAR-X : HAR + VIX × β² | § 4.14 (+ additif puissance) | § 11 | **protocole écrit, code à faire** |

Constat transversal : avec n effectif ≈ 36 à 126 jours, le MDE est ≈ 0,05 à 0,16 de QLIKE, bien au-dessus des écarts discutés (0,003 à 0,014). Les essais disent « pas de gain détectable », pas « pas de gain ». Le panel de titres est **déjà** inclus (l'écart de perte est moyenné par date, estimateur de type Driscoll-Kraay) : pas de gain de puissance de ce côté.

Décision en vigueur : **l'hybride (ordre des titres par l'IA, niveau par HAR) reste en place.**

## 4. À faire ensuite (par ordre)

1. **Lire le résultat de l'essai multi-horizon** (run lancé sur la PR #28 après le commit « examen_multi_horizon »), puis écrire le **§ 10 de `METHODE.md`** (même gabarit que §§ 8 et 9 : tableau des règles, constats, lecture selon la grille du § 4.13, décision, limites), commiter et pousser. Requête :

```sql
select lot, verdict, ic as ecart_aspa, t_stat, diagnostics
from experiences where nom = 'examen_multi_horizon' order by lot desc limit 1;
```

   Clés de `diagnostics` : `aspa` (écart, erreur_type, t, nu, p_bilatere, ic95, ic90, n_effectif, mde_80, ecart_sur_mde), `par_horizon` (idem par horizon), `holm`, `blocs_negatifs`, `blocs`, `crises`, `ic`, `placebo`, `regles` (`1_piste`, `2_fuite_probable`, `3_B_pire`, `4_equivalence`), `peut_conclure_equivalence`.
   Vérifier d'abord que le run est terminé (`gh run list -R Mephisto116631/thesee-streamlit -w "Laboratoire — essais du modèle" -L 3`) et qu'il n'y a pas d'erreur `[LABO][ERREUR]` dans ses journaux.
2. Si **piste** : écrire (avant tout code) un protocole à 126 jours avec réplication sur des données non utilisées (par ex. S&P MidCap 400 via `universe.get_sp400_tickers`, `ex.autre_marche`). Une publication exige : p corrigé < 0,5 % (t ≈ 3), effet ≥ minimum économique déclaré, réplication à t ≥ 2 (§ 4.12, règle 7).
3. Si **sans pouvoir de conclure** : ne pas relâcher les seuils. Pistes restantes : compléter avec le test uniforme de Quaedvlieg (bootstrap par blocs, non implémenté), ou valider par simulation la puissance (MDE) avant tout nouvel essai.
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
