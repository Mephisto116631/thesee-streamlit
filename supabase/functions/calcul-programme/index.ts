// Edge Function « calcul-programme » : lance sync.yml aux heures prévues (tâche planifiée Supabase,
// supabase_schema.sql V16). Les tâches planifiées de GitHub démarraient 7 à 9 heures en retard.
//
// À déployer SANS vérification JWT (la base n'a pas de session utilisateur). Protection : l'en-tête
// x-jeton-calcul doit contenir le secret aléatoire gardé dans Supabase Vault, connu de la base seule.
// Le jeton GitHub (secret GH_DISPATCH_TOKEN) est le même que pour « relancer-calcul ».
import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "npm:@supabase/supabase-js@2";

const DEPOT = "Mephisto116631/thesee-streamlit";
const WORKFLOW = "sync.yml";
const DELAI_MIN_MS = 10 * 60 * 1000;

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return json(405, { ok: false, message: "Méthode non autorisée." });

  const recu = req.headers.get("x-jeton-calcul") ?? "";
  if (!recu) return json(401, { ok: false, message: "Non autorisé." });

  const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const { data: valide, error } = await sb.rpc("verifier_jeton_calcul", { jeton: recu });
  if (error) return json(500, { ok: false, message: "Vérification du jeton impossible." });
  if (valide !== true) return json(401, { ok: false, message: "Non autorisé." });

  const jeton = Deno.env.get("GH_DISPATCH_TOKEN");
  if (!jeton) return json(503, { ok: false, message: "Secret GH_DISPATCH_TOKEN absent dans Supabase." });

  // Même garde-fou que « relancer-calcul » : pas deux calculs en même temps ni en rafale
  const { data: dernier } = await sb.from("sync_log").select("status, started_at")
    .order("started_at", { ascending: false }).limit(1).maybeSingle();
  if (dernier) {
    const age = Date.now() - new Date(dernier.started_at).getTime();
    if (dernier.status === "running" && age < 45 * 60 * 1000) {
      return json(409, { ok: false, message: "Un calcul est déjà en cours." });
    }
    if (age < DELAI_MIN_MS) {
      return json(429, { ok: false, message: "Dernier calcul lancé il y a moins de 10 minutes." });
    }
  }

  const r = await fetch(`https://api.github.com/repos/${DEPOT}/actions/workflows/${WORKFLOW}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${jeton}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "thesee-calcul-programme",
    },
    body: JSON.stringify({ ref: "main" }),
  });
  if (r.status === 204) return json(202, { ok: true, message: "Calcul lancé." });
  const detail = await r.text();
  return json(502, { ok: false, message: `GitHub a refusé le lancement (${r.status}).`, detail: detail.slice(0, 300) });
});
