// Connexion Google (même méthode que Sysiphe) : Supabase ouvre la page de Google, puis renvoie vers
//   - l'APK : lien com.thesee.app://login-callback?code=… (déclaré dans AndroidManifest.xml par le workflow mobile.yml) ;
//   - la PWA : la page elle-même (?code=…), lue automatiquement par supabase-js au chargement.
// Ces deux adresses doivent figurer dans Supabase › Authentication › URL Configuration › Redirect URLs.

export const RETOUR_GOOGLE = "com.thesee.app://login-callback";

/** Adresse de retour de la PWA : la page actuelle, sans le routage par « # » ni les paramètres. */
export function adresseRetourWeb(loc: { origin: string; pathname: string }): string {
  return loc.origin + loc.pathname;
}

/** Lit le lien de retour de Google dans l'APK : code à échanger contre une session, ou message d'erreur.
 *  null si le lien ne vient pas de la connexion Google. */
export function analyserRetour(url: string): { code?: string; erreur?: string } | null {
  if (!url.startsWith(RETOUR_GOOGLE)) return null;
  const params = new URLSearchParams(url.slice(RETOUR_GOOGLE.length).replace(/^[/?#]+/, "").replace(/#/g, "&"));
  const erreur = params.get("error_description") ?? params.get("error") ?? undefined;
  const code = params.get("code") ?? undefined;
  return erreur ? { erreur } : code ? { code } : { erreur: "Retour de Google sans code de connexion." };
}
