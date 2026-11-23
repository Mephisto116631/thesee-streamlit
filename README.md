# Thésée — Terminal quantamental

```
GitHub Actions (cron)  ──écrit──▶  Supabase  ◀──lit──  Appli Android (APK) / PWA
  calculs : prix, comptes SEC,        tables prêtes        lecture seule,
  Z-Score, modèles IA, portefeuille   à afficher           aucun calcul lourd
                                          ▲
                                          └──lit── App Streamlit (conservée)
```

| Dossier / fichier | Rôle |
|---|---|
| `cron_sync.py` | Point d'entrée du cron : synchro incrémentale, modèles, publication |
| `data_pipeline.py`, `fred.py`, `universe.py` | Collecte (Yahoo depuis 2005, Alpha Vantage, FRED) et ancien modèle XGBoost 1 jour (conservé, désactivé) |
| `publish.py` | Tables pour l'appli : `titres_snapshot`, `sector_medians`, `model_runs`, `market_overview`, `portefeuille_recommande`, `suivi_volatilite` |
| `portefeuille.py` | Portefeuille conseillé : Markowitz sur tout le S&P 500, covariance factorielle, même optimiseur que l'appli |
| `docs/METHODE.md` | **Journal de la méthode** : chaque choix, ses hypothèses, ses tests et leurs résultats |
| `modele_risque.py` | **IA de volatilité à 6 mois** (seul modèle probant), bilan en conditions réelles |
| `modele_horizon.py` | Modèles de rendement 1 mois / 6 mois / 1 an (en test, non probants) |
| `fondamentaux_sec.py` | Comptes officiels SEC (EDGAR) : facteurs du laboratoire et valorisation de l'appli (PER, ROE…) |
| `experiences.py`, `backtest_risque.py`, `modele_regime.py`, `modele_cnn.py` | **Laboratoire** : essais de variantes, jugés avec un seuil corrigé du nombre d'essais |
| `data/sp500_historique.csv` | Composition historique du S&P 500 (pas de biais du survivant) |
| `ranges.json` | **Fourchettes d'interprétation** (RSI, ROE, Z-Score…), partagées par le cron et l'appli |
| `supabase_schema.sql` | Schéma complet + sécurité RLS (lecture seule pour la clé publique) |
| `mobile/` | Appli mobile (Preact + Capacitor) → APK Android et PWA |
| `app.py`, `pages/` | App Streamlit (lecture seule désormais) |

## Mise en route (une seule fois)

1. **Supabase** → SQL Editor → exécuter `supabase_schema.sql` (idempotent).
2. **GitHub → Settings → Secrets and variables → Actions** :
   - `SUPABASE_URL`, `ALPHA_VANTAGE_KEY`, `FRED_API_KEY` (déjà présents)
   - `SUPABASE_KEY` = clé **service_role** (Supabase → Settings → API). Depuis RLS, la clé anon ne peut plus écrire.
   - `SUPABASE_ANON_KEY` = clé **anon** (embarquée dans l'appli, lecture seule)
   - `SEC_USER_AGENT` = « Nom adresse@exemple.com » : la SEC (Securities and Exchange Commission) exige un contact ;
     n'est envoyé qu'aux serveurs sec.gov
   - Signature de l'APK (recommandé, sinon chaque mise à jour oblige à désinstaller l'appli) :
     ```bash
     keytool -genkeypair -keystore thesee.jks -alias thesee -keyalg RSA -keysize 2048 -validity 10000
     base64 -w0 thesee.jks   # -> secret ANDROID_KEYSTORE_BASE64
     ```
     + `ANDROID_KEYSTORE_PASSWORD` et `ANDROID_KEY_ALIAS` (= `thesee`). Garder `thesee.jks` en lieu sûr.
3. **Actions** → « Sync Thésée — Supabase » → *Enable workflow* (si désactivé) puis *Run workflow*.
4. **Settings → Pages** → Source : *GitHub Actions* (pour la version ordinateur).
5. **Actions** → « Appli mobile — APK + PWA » → *Run workflow*.

## Installer l'appli

- **Android** : onglet *Releases* du dépôt → dernière « Thésée Android » → `thesee.apk` → ouvrir → autoriser l'installation.
- **Ordinateur** : `https://<utilisateur>.github.io/thesee-streamlit/` (installable comme application depuis Chrome/Edge).

## Développer l'appli en local

```bash
cd mobile
cp .env.example .env.local   # renseigner URL + clé anon
npm install
npm run dev     # http://localhost:5173
npm test
```

## Fréquence de mise à jour

| Quoi | Quand | Workflow |
|---|---|---|
| Cours, indicateurs, portefeuille, volatilité IA | 3 fois par jour ouvré (ouverture, mi-séance, clôture US) | `sync.yml` |
| Comptes officiels SEC (PER, ROE…) | 1 fois par semaine (option « Recharger les comptes SEC » au lancement manuel) | `sync.yml` |
| Prévision IA enregistrée pour le suivi réel | 1 fois par semaine | `sync.yml` |
| Re-test de l'IA de volatilité et de l'hybride IA + HAR | le 2 de chaque mois, et sur chaque PR qui touche aux modèles | `experiences.yml` |
| Révision du portefeuille conseillé (univers figé) | 1er passage de janvier et de juillet ; l'appli suit le rythme choisi (6 ou 12 mois) | `sync.yml` |
| Tests | à chaque PR | `tests.yml`, `mobile.yml` |

Un job *keepalive* empêche GitHub de désactiver les workflows planifiés après 60 jours sans commit.

## Ne montrer que du fiable

Le détail de chaque choix (hypothèses, tests, résultats chiffrés, ce qui a été écarté) est tenu dans
[`docs/METHODE.md`](docs/METHODE.md).

Règle de l'appli : un chiffre ne sert à décider que s'il est **prouvé**, sinon il est présenté comme une **hypothèse**.

- **Volatilité prévue par l'IA (6 mois)** : seul modèle probant (testé sur 2013-2026, sur des années jamais vues ;
  force de la preuve ≈ 240 % du seuil). Sa preuve est entretenue :
  - re-test mensuel au laboratoire ; `publish.py` ne publie la prévision que si le **dernier** test est probant,
    sinon l'appli revient d'elle-même à la volatilité des 3 dernières années ;
  - suivi en conditions réelles : chaque semaine, la prévision de chaque titre est enregistrée (`suivi_volatilite`),
    puis comparée 6 mois plus tard au risque réellement observé (premier bilan : mai 2027).
- **Rentabilité attendue** : hypothèse de long terme (CAPM, Capital Asset Pricing Model : taux sans risque +
  bêta × prime de risque), réglable dans les Paramètres. Aucun modèle de rendement n'a passé le test.
- **Force de la preuve** : t / seuil, en % (100 % = probant). Le seuil suit la loi de Student et est relevé
  pour chaque essai fait (correction de Bonferroni), afin que le hasard ne passe pas.
- **Valorisation SEC** : des faits publiés (comptes annuels), pas des prévisions. Une valeur hors bornes
  plausibles, ou impossible à calculer de façon sûre (plusieurs catégories d'actions), est affichée « n.d. »
  plutôt que fausse. Au laboratoire, ces ratios n'ont pas prédit la performance : ils servent à comprendre un titre.

## Relancer le calcul depuis l'appli

Le bouton « Relancer le calcul » (Analyse › Modèles IA, Paramètres) appelle la fonction Supabase
`relancer-calcul` (`supabase/functions/relancer-calcul/`), qui déclenche le workflow
`sync.yml`. Le jeton GitHub reste dans Supabase, jamais dans l'APK :

1. GitHub → Settings → Developer settings → Fine-grained tokens → *Generate new token* :
   accès au seul dépôt `thesee-streamlit`, permission **Actions : Read and write**.
2. Supabase → projet Thésée → Edge Functions → Secrets : ajouter `GH_DISPATCH_TOKEN` = ce jeton.

Garde-fous : refus si un calcul tourne déjà ou a démarré il y a moins de 10 minutes.

## Historique des versions

| PR | Apport |
|---|---|
| #32 | Suivi en conditions réelles du risque du mois (prévisions enregistrées chaque semaine, garde-fou) ; rappels de révision sur le téléphone (APK) ; glossaire dans l'appli (Analyse › Glossaire, et chaque bouton « ? ») |
| #31 | Interface : plus de glissement latéral ni de texte coupé (verdicts et filtres qui passent à la ligne, noms sur deux lignes, tableaux en fiches sur téléphone) |
| #30 | Modèle figé (ordre par l'IA, niveau par HAR) ; carte « Face aux chocs » : crises 2008, 2011, 2015-16, fin 2018, 2020, 2022 rejouées sur le portefeuille (pas une prévision) et risque du mois à venir (HAR + VIX), affiché seulement s'il reste confirmé au re-test mensuel |
| #28, #29 | Laboratoire : XGBoost sur le niveau, HAR × k, multi-horizon, HAR-X (VIX), HAR étendu : rien ne bat HAR à 6 mois de façon prouvable |
| #27 | Prévision hybride (ordre des titres par l'IA, niveau par HAR) ; portefeuille révisé tous les 6 ou 12 mois ; marge de sécurité du mode « Je limite le risque » ; projection à queues épaisses (Student) |
| #26 | Examen approfondi de l'IA de volatilité : EWMA, GARCH, HAR, calibration, crises depuis 2008, placebo, autre marché, backtest avec frais, PBO |
| #25 | Markowitz sur tout le S&P 500 (fin de la présélection par momentum, non prouvée) ; covariance en 20 facteurs ; même optimiseur serveur / appli ; gain de diversification dans la Fiche de calculs ; journal `docs/METHODE.md` |
| #24 | README à jour |
| #23 | Force de la preuve en % du seuil ; ratios SEC fiabilisés (bornes, « n.d. » plutôt qu'un chiffre faux) ; option « Recharger les comptes SEC » |
| #22 | Preuve continue de l'IA de volatilité (re-test mensuel, suivi réel, garde-fou) ; valorisation SEC dans l'appli ; tri PER |
| #21 | Algorithme 4 : CNN (réseau de neurones convolutif) sur la forme des courbes de cours, au laboratoire (non probant) |
| #20 | Algorithme 3 : ensemble XGBoost prudent + linéaire, au laboratoire (non probant) |
| #19 | Algorithmes 1 et 2 : IA de risque avec les comptes SEC, régime de marché depuis 1993 ; finition du vocabulaire et nettoyage (mode court terme et modèle 1 jour retirés) |
| #18 | Lisibilité : carte de synthèse, Markowitz unique et synchronisé, « Ajuster les titres », fiche de calculs avec définitions, cartes repliables, indices en % |
| #17 | Refonte en 4 onglets (Accueil, Portefeuille, Analyse, Positions) |
| #16 | Volatilité IA en option pour le portefeuille, mode « Je limite le risque », Monte-Carlo à la volatilité retenue |
| #15 | Backtest du portefeuille mensuel 2013-2026 avec la volatilité IA |
| #14 | Laboratoire : IA de risque (volatilité et perte maximale futures) |
| #13 | Laboratoire : fondamentaux SEC publiés à chaque date |
| #12 | Laboratoire : variantes testées à part (alpha de Jensen, alpha sectoriel), seuil corrigé du nombre d'essais |
| #11 | Contrôles anti-biais : sens des facteurs volatilité et taille |
| #10 | Verdict honnête (seuil de Student corrigé), facteurs long terme |
| #9 | Historique depuis 2005, composition historique du S&P 500, mise à jour intégrée de l'APK (comme Sisyphe) |
| #8 | Trade Republic (ordres prêts à copier, prix en euros), positions en ligne, Monte-Carlo, barre de progression |
