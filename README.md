# Thésée — Terminal quantamental

```
GitHub Actions (cron)  ──écrit──▶  Supabase  ◀──lit──  Appli Android (APK) / PWA
  calculs : prix, fondamentaux,       tables prêtes        lecture seule,
  Z-Score, modèles IA, signaux        à afficher           aucun calcul lourd
                                          ▲
                                          └──lit── App Streamlit (conservée)
```

| Dossier / fichier | Rôle |
|---|---|
| `cron_sync.py` | Point d'entrée du cron : synchro incrémentale, modèles, publication |
| `data_pipeline.py`, `fred.py`, `universe.py` | Collecte (Yahoo, Alpha Vantage, FRED) et modèles XGBoost |
| `publish.py` | Tables pour l'appli : `titres_snapshot`, `sector_medians`, `signals`, `model_runs`, `market_overview` |
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

Le cron tourne 3 fois par jour ouvré (ouverture, mi-séance, clôture US). Un job *keepalive*
empêche GitHub de désactiver le workflow après 60 jours sans commit.
