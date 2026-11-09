# Thésée — Documentation technique

Terminal quantamental (prix + fondamentaux + crédit + modèles XGBoost) sur un univers S&P 500 + Nasdaq-100 + ETFs.
Stack : **Streamlit** (UI) · **Supabase / PostgreSQL** (stockage) · **GitHub Actions** (CRON : tout le calcul lourd).

> Aucune sortie de Thésée ne constitue un conseil en investissement.

---

## 1. Principe d'architecture

```
 Yahoo (yfinance)   Alpha Vantage   FRED
        │                │            │
        └────────┬───────┴────────────┘
                 ▼
     GitHub Actions (cron_sync.py)          ← seul endroit qui télécharge et entraîne
       prix → fondamentaux → Z-Score → features
       → 3 modèles XGBoost → SHAP du jour → snapshot
                 ▼
          Supabase (PostgreSQL)
                 ▼
     App Streamlit (lecture seule, cache 10 min)
```

Règles :
- **L'app ne télécharge rien et n'entraîne rien.** Elle lit des résultats pré-calculés (quelques requêtes légères).
- **Le CRON écrit tout.** Il réutilise `data_pipeline.py`, `db.py`, `fred.py`, `universe.py` tels quels, en remplaçant le module `streamlit` par `_st_shim.py`.
- Raison de cette séparation : Streamlit Cloud a un CPU partagé et bridé (« app throttled ») ; l'entraînement dans l'app + `select("*")` plafonné à 1 000 lignes provoquaient des lenteurs et des re-téléchargements massifs.

---

## 2. Arborescence

| Fichier | Rôle |
|---|---|
| `app.py` | Page d'accueil : date des données, dernière synchro, 4 métriques |
| `pages/1_Screener.py` | Recherche/filtre ticker, indice, secteur ; indicateurs (depuis `snapshot`) |
| `pages/2_Portefeuille.py` | Équipondéré / Markowitz, Monte-Carlo 252 j ; prix lus à la demande pour les seuls titres choisis |
| `pages/3_Audit_IA.py` | Diagnostic du modèle actions (jour) + modèle relatif + SHAP du dernier jour + comparaison des seuils |
| `pages/4_Credit_Bilan.py` | Z-Score d'Altman, ratings S&P, spreads HY/IG |
| `pages/5_Audit_ETF.py` | Diagnostic du modèle ETF + SHAP |
| `pages/6_Guide.py` | Guide utilisateur (onglets Démarrage / Indicateurs / Modèles IA / Crédit & Bilan / Données & architecture) |
| `data_pipeline.py` | ETL, features, entraînement, publication, accès lecture pour l'app |
| `db.py` | Accès Supabase (upsert, fetch paginé, JSON safe) |
| `universe.py` | Univers de tickers (CSV GitHub / Wikipedia / repli statique) + ETFs et indices de référence |
| `fred.py` | Spreads de crédit FRED (HY `BAMLH0A0HYM2`, IG `BAMLC0A0CM`) |
| `utils.py` | Listes d'actifs « core », secteurs, noms, ratings, listes de features |
| `glossaire.py` | Fiches pédagogiques + boutons ℹ️ |
| `theme.py` | Palettes (nuit, bloomberg, obsidienne, custom), CSS injecté |
| `cron_sync.py` | Point d'entrée du CRON |
| `_st_shim.py` | Faux module `streamlit` pour exécuter le pipeline hors serveur |
| `supabase_schema.sql`, `migration_002_zscore_fred.sql`, `migration_003_modeles.sql` | Schéma SQL |
| `.github/workflows/sync.yml` | Workflow GitHub Actions |
| `.streamlit/config.toml` | Thème sombre natif (`base="dark"`, primaire `#e3a63b`) |
| `.streamlit/secrets.toml.example` | Modèle de secrets |
| `requirements.txt`, `runtime.txt` | Dépendances ; Python 3.11 visé |

---

## 3. Base de données (Supabase)

### Tables
| Table | Clé | Contenu |
|---|---|---|
| `market_data` | `(symbol, date)` | OHLCV de l'univers élargi |
| `macro_data` | `(symbol, date)` | OHLCV VIX, SPY |
| `fonda_data` | `symbol` | roe, ev_ebitda, debt_eq, margin, `last_updated` |
| `zscore_data` | `symbol` | Z-Score d'Altman et composantes |
| `credit_spreads` | `(serie_id, date)` | Spreads FRED |
| `ratings_sp` | `symbol` | Ratings S&P (manuels) |
| `user_settings` | — | Réglages utilisateur |
| `model_results` | `model` | Payload jsonb d'un modèle (`jour`, `relatif`, `etf`, `meta`) + `updated_at` |
| `shap_latest` | `(model, symbol)` | SHAP du dernier jour (jsonb) |
| `screener_snapshot` | `symbol` | Dernière ligne de features par titre (jsonb) |

Vue `market_data_status` (`security_invoker = true`) : `symbol, max_date, n` — sert à la synchro incrémentale.

### Sécurité
- RLS activé sur les nouvelles tables, **sans politique** : accès uniquement par la clé secrète (service role) côté serveur/CRON.
- Le linter signale des alertes INFO (« RLS sans politique ») et un WARN sur `rls_auto_enable()` : pré-existants, attendus.

### Particularités PostgREST
- Plafond de **1 000 lignes** par réponse → toute lecture massive passe par `db._fetch_all` (pagination `.range()`, `PAGE_SIZE=1000`).
- `db._json_safe` convertit numpy / NaN / Inf en JSON valide avant écriture.
- Projet gratuit : **mis en pause après inactivité** (statut `INACTIVE`) → à restaurer depuis le dashboard avant tout.

---

## 4. Pipeline de données (`data_pipeline.py`)

### Synchro (réservée au CRON)
- `sync_market_data(tickers)` : télécharge Yahoo par lots de 100, **en mémoire**, n'écrit en base que les lignes `>= max_date_en_base − 7 j` (ou l'historique complet pour un titre absent).
- `sync_macro_data` : VIX, SPY.
- `sync_fonda_data` / `sync_altman_zscore` : Alpha Vantage, TTL 7 jours, `sleep(13)` entre appels (quota gratuit). Limité aux titres « core » (12).
- `fred.get_spreads_hy_ig()` : spreads HY/IG, incrémental.
- `_refresh_alpha_autorise()` : Alpha Vantage ne s'exécute que si `THESEE_CRON=1`.

### Features (`build_features`, `build_features_etf`)
Techniques : `daily_return, mom_5j, mom_20j, mom_60j, mom_12_1` (`close.shift(21)/close.shift(252)-1`), `pct_vs_ma50, macd_diff, volatility, vol_relative, rsi_14`.
Contexte : `vix_regime`, `rsi_rank_sec`. Fondamentaux : `roe, margin, ev_ebitda, debt_eq`.
ETF : `tracking_vs_ref` (écart à l'indice de référence, cf. `ETF_INDICE_REFERENCE`), `dollar_volume_relatif`.

Cibles :
- `target_next_return` → hausse demain (modèles jour et ETF), avec zone neutre.
- `target_fwd_5j` → rendement à 5 jours.
- `target_rel_5j` = rendement 5 j − **médiane du jour** (modèle relatif).
- Colonnes `*_cs` : rang percentile par date des features de `CS_BASE`.

`garder_sans_cible=True` conserve le dernier jour (sans cible) pour le snapshot et le SHAP.

### Modèles
| Modèle | Cible | Features |
|---|---|---|
| Actions (jour) | Hausse demain, hors zone neutre (±0,3 % par défaut) | `FEATURES_DEFAUT` |
| Actions (relatif) | Bat la médiane de l'univers à 5 j | `FEATURES_RELATIF` = `CS_BASE_cs` + `vix_regime` |
| ETF | Hausse demain, hors zone neutre | `FEATURES_ETF` |

`train_ia(_df_hash, df, seuil_neutre, features, cible, avec_wf)` :
- **Split temporel par date** (80/20, une seule date de coupure) — `_split_temporel_par_date`.
- **Embargo de 5 jours** pour la cible à 5 jours.
- Métriques : accuracy, baseline naïve, ROC-AUC, **log loss** (vs référence), Brier, calibration, importance des variables.
- **IC** (corrélation de rang par date → moyenne, écart-type, **t-stat**) via `_ic_par_date`.
- `walk_forward_validation` : 5 fenêtres pour juger la stabilité.
- `comparer_seuils_neutres` : compare plusieurs zones neutres (`avec_wf=False`).
- `calculer_shap_derniere_ligne` : SHAP du dernier jour pour chaque titre.

### Publication
`get_all_data()` (CRON) enchaîne 6 étapes : prix → macro → fondamentaux → Z-Score → features + 3 modèles + comparaison de seuils → `publier_resultats` (écrit `model_results`, `shap_latest`, `screener_snapshot`, `meta`).

### Lecture (app)
- `get_app_data()` (cache 600 s) : `snapshot`, `snapshot_actions`, `snapshot_etf`, `fonda_data_clean`, `zscore_df`, `ratings_df`, `model_result`, `model_result_relatif`, `model_result_etf`, `importance_df`, `importance_df_etf`, `meta`.
- `get_prix_historique(tickers, jours=1100)` (cache 3600 s) : prix à la demande.
- `get_shap_symbols(model)`, `get_shap(model, symbol)` (cache 600 s).

---

## 5. CRON (GitHub Actions)

`.github/workflows/sync.yml` : Python 3.11, timeout 60 min, exécute `python cron_sync.py`.
Horaires (UTC) : **14:00, 17:00, 20:30, lundi–vendredi** + `workflow_dispatch` (lancement manuel).

Secrets requis (Settings → Secrets and variables → Actions) :
`SUPABASE_URL`, `SUPABASE_KEY` (clé **secrète / service role**), `ALPHA_VANTAGE_KEY`, `FRED_API_KEY`.

`cron_sync.py` : pose `THESEE_CRON=1`, injecte le shim, charge l'univers, lance `dp.get_all_data`, puis FRED. Log final : nombre de tickers, fondamentaux, Z-Scores, accuracy, **IC du modèle relatif**.

### Pièges connus
- Les workflows programmés **ne tournent que depuis la branche par défaut** (`main`). Une modification sur une autre branche n'est effective qu'après fusion.
- Un workflow programmé d'un dépôt public passe en **`disabled_inactivity` après 60 jours sans commit** sur la branche par défaut → le réactiver (Actions → workflow → *Enable workflow*). Prévention possible : commit automatique mensuel (keepalive).
- Premier run long : historique complet de l'univers + Alpha Vantage (13 s/appel).

---

## 6. Déploiement Streamlit Cloud

- Repo public `Mephisto116631/thesee-streamlit`, branche `main`, fichier `app.py`.
- Redéploiement automatique à chaque push (tout push relance l'app).
- Secrets de l'app (Settings → Secrets), format de `.streamlit/secrets.toml.example` : `SUPABASE_URL`, `SUPABASE_KEY`, `ALPHA_VANTAGE_KEY`, `FRED_API_KEY`.
- L'app lit via `db._get_secret` (secrets Streamlit, sinon variables d'environnement).
- Python effectif observé : 3.14 malgré `runtime.txt` (3.11) — garder les dépendances compatibles.
- `use_container_width` est déprécié (à migrer vers `width='stretch'`).

---

## 7. Thème et UI

- `theme.py` : palettes `nuit`, `bloomberg`, `obsidienne` + palette personnalisée ; sélecteur dans la sidebar ; `build_css` génère le CSS (barres de progression, onglets, métriques, popovers).
- `.streamlit/config.toml` fixe le thème natif sombre pour éviter le flash au chargement.
- `glossaire.py` : dictionnaire `FICHES` ; `info_button(cle)` ouvre un popover ℹ️, `render_fiche(cle)` affiche une fiche. Utilisé dans les pages et dans le Guide.

---

## 8. Lecture des résultats (repères)

- Écart accuracy − baseline : ≤ 0 = rien d'exploitable ; 0–2 pts = bruit ; 2–5 pts stables = plausible ; > 8 pts = suspect (fuite d'information).
- IC réaliste sur données quotidiennes : 0,01–0,03. Regarder le **t-stat** et la **stabilité** entre fenêtres, pas seulement la moyenne.
- Constats de la phase de test : IC de l'ordre de 0,01–0,02 et instable ; effet le plus robuste = momentum 12-1 mois ; volume relatif au t le plus élevé ; retournement court terme négatif.
- Le résultat réel du modèle relatif sur Supabase reste à observer après le premier run complet du CRON.

---

## 9. Procédures d'exploitation

**Première mise en service / après pause**
1. Supabase : restaurer le projet (statut `INACTIVE` → `ACTIVE`).
2. Appliquer les migrations si absentes (`supabase_schema.sql`, `migration_002_zscore_fred.sql`, `migration_003_modeles.sql`).
3. GitHub : fusionner la branche dans `main`, vérifier les 4 secrets.
4. Actions → *Enable workflow* si désactivé → *Run workflow*.
5. Après le run, recharger l'app (cache 10 min) et lire l'Audit IA.

**Test sans toucher à la prod** : l'app lit uniquement Supabase ; pour tester un changement du pipeline, lancer le workflow manuellement depuis la branche voulue (`workflow_dispatch` permet de choisir la branche).

**Ajouter un ticker « core »** : `utils.py` (liste d'actifs, `dict_secteurs`, `dict_noms`, `ratings_sp`) ; ajouter son rating dans `ratings_sp` (Supabase).

**Ajouter une feature** : `build_features` → ajouter à `FEATURES_DEFAUT` (ou `CS_BASE` pour le relatif) → fiche dans `glossaire.py` → relancer le CRON.

**Changer la fréquence du CRON** : `schedule` dans `sync.yml` (heures en UTC).

---

## 10. Dépannage

| Symptôme | Cause probable | Action |
|---|---|---|
| « Aucun résultat publié » dans l'app | CRON jamais exécuté / Supabase en pause | Restaurer Supabase, lancer le workflow |
| Données figées | Workflow désactivé (`disabled_inactivity`) ou secret invalide | Réactiver, lire les logs Actions |
| Moins de 1 000 lignes lues | Plafond PostgREST | Utiliser `_fetch_all` |
| App « throttled » | Calcul lourd dans l'app | Garder l'app en lecture seule |
| Boucle « 1/12 » Z-Score | Redéploiements répétés relançant Alpha Vantage | Alpha Vantage réservé au CRON (`THESEE_CRON`) |
| `st.toast` erreur d'icône | Icône non-emoji | Utiliser un emoji (✅) |
| Push refusé 403 | App GitHub Claude non installée | Installer l'app sur le repo |
| Nasdaq-100 limité à 20 titres | Source en ligne indisponible → repli statique | Voir `universe.py` |

---

## 11. Limites connues

- Fondamentaux Alpha Vantage = **instantanés actuels** appliqués à tout l'historique (léger look-ahead) ; limités aux 12 titres « core » (quota gratuit).
- **Biais de survie** : l'univers est composé des membres actuels des indices.
- Ratings S&P renseignés manuellement.
- Liste Nasdaq-100 : repli statique de 20 tickers si la source échoue.
- SHAP limité au dernier jour.
- Pas de coûts de transaction ni de backtest long-short.

## 12. Feuille de route

1. Premier run complet du CRON et lecture de l'IC / t-stat / log loss du modèle relatif.
2. Backtest long-short avec coûts de transaction.
3. Source fiable pour le Nasdaq-100 ; correction du biais de survie.
4. Keepalive mensuel du workflow.
5. Amélioration du Screener ; migration `use_container_width` → `width='stretch'`.
6. **Sécurité** : régénérer les clés Supabase et Alpha Vantage exposées pendant les échanges.
