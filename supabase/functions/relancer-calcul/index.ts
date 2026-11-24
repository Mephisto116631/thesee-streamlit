// Edge Function « relancer-calcul » : déclenche la synchronisation / le
// ré-entraînement des modèles (workflow GitHub sync.yml) depuis l'appli.
//
// Le jeton GitHub reste ici (secret GH_DISPATCH_TOKEN), jamais dans l'APK.
// Garde-fous :
//   - réservé à un utilisateur CONNECTÉ (compte de l'onglet Positions) : la clé anon est publique
//     (embarquée dans la PWA), elle ne suffit pas ;
//   - si le secret RELANCE_EMAILS est défini (adresses séparées par des virgules), seuls ces comptes
//     peuvent relancer ;
//   - pas de relance si un calcul tourne déjà ou a démarré il y a moins de 10 minutes.
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const DEPOT = "Mephisto116631/thesee-streamlit";
const WORKFLOW = "sync.yml";
const DELAI_MIN_MS = 10 * 60 * 1000;

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json(405, { ok: false, message: "Méthode non autorisée." });

  const jeton = Deno.env.get("GH_DISPATCH_TOKEN");
  if (!jeton) {
    return json(503, { ok: false, message: "Relance non configurée : secret GH_DISPATCH_TOKEN absent dans Supabase." });
  }

  const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

  // Utilisateur connecté obligatoire : le jeton de session arrive dans l'en-tête Authorization
  const session = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
  const { data: auth } = session ? await sb.auth.getUser(session) : { data: { user: null } };
  const utilisateur = auth?.user;
  if (!utilisateur) {
    return json(401, { ok: false, message: "Connecte-toi (onglet Positions) pour relancer le calcul." });
  }
  const autorises = (Deno.env.get("RELANCE_EMAILS") ?? "").split(",").map((e) => e.trim().toLowerCase()).filter(Boolean);
  if (autorises.length && !autorises.includes((utilisateur.email ?? "").toLowerCase())) {
    return json(403, { ok: false, message: "Ce compte n'est pas autorisé à relancer le calcul." });
  }

  // Dernier passage : évite les relances en rafale
  const { data: dernier } = await sb.from("sync_log").select("status, started_at")
    .order("started_at", { ascending: false }).limit(1).maybeSingle();
  if (dernier) {
    const age = Date.now() - new Date(dernier.started_at).getTime();
    if (dernier.status === "running" && age < 45 * 60 * 1000) {
      return json(409, { ok: false, message: "Un calcul est déjà en cours." });
    }
    if (age < DELAI_MIN_MS) {
      const reste = Math.ceil((DELAI_MIN_MS - age) / 60000);
      return json(429, { ok: false, message: `Dernier calcul lancé il y a moins de 10 minutes : réessaie dans ${reste} min.` });
    }
  }

  const r = await fetch(`https://api.github.com/repos/${DEPOT}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${jeton}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "thesee-relance",
    },
    body: JSON.stringify({ ref: "main" }),
  });
  if (r.status === 204) {
    return json(202, { ok: true, message: "Calcul lancé : environ 3 à 8 minutes. Les données se mettront à jour toutes seules." });
  }
  const detail = await r.text();
  return json(502, { ok: false, message: `GitHub a refusé la relance (${r.status}).`, detail: detail.slice(0, 300) });
});
