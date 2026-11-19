import { useEffect, useMemo, useState } from "preact/hooks";
import {
  ajouterPositions, api, connexion, deconnexion, lirePositions, modifierPosition, type Position,
  supprimerPosition, surChangementSession, utilisateurCourant,
} from "../api";
import { Card, Details, Loading, Stat, useData } from "../components";
import { dateFr, num, pct, signClass } from "../format";
import { useParametres } from "../settings";
import { PlanAchat } from "./PlanAchat";

const EURUSD_SECOURS = 1.08;

/** Onglet « Positions » : ce que je possède, sa valeur, mon gain ou ma perte, et l'écart avec ma cible. */
export function Positions({ cible }: { cible: { symbol: string; poids: number }[] }) {
  const [user, setUser] = useState<{ email: string } | null | undefined>(undefined);
  useEffect(() => {
    utilisateurCourant().then(setUser);
    return surChangementSession(() => utilisateurCourant().then(setUser));
  }, []);
  if (user === undefined) return <Loading />;
  return user ? <MesPositions email={user.email} cible={cible} /> : <Connexion />;
}

function Connexion() {
  const [email, setEmail] = useState("");
  const [mdp, setMdp] = useState("");
  const [msg, setMsg] = useState("");
  const [enCours, setEnCours] = useState(false);
  const go = async (creer: boolean) => {
    setEnCours(true);
    const err = await connexion(email.trim(), mdp, creer);
    setEnCours(false);
    setMsg(err ?? "");
  };
  return (
    <Card title="Mes positions">
      <p class="hint" style={{ marginTop: 0 }}>Connecte-toi pour enregistrer ce que tu possèdes. Tes positions sont stockées dans Supabase
        et visibles uniquement par ton compte (téléphone et ordinateur).</p>
      <label class="field">E-mail<input type="email" autocomplete="email" value={email} onInput={(e) => setEmail((e.target as HTMLInputElement).value)} /></label>
      <label class="field" style={{ marginTop: 8 }}>Mot de passe
        <input type="password" autocomplete="current-password" value={mdp} onInput={(e) => setMdp((e.target as HTMLInputElement).value)} /></label>
      <div class="actions-ordres">
        <button class="more" disabled={enCours || !email || mdp.length < 6} onClick={() => go(false)}>Se connecter</button>
        <button class="more" disabled={enCours || !email || mdp.length < 6} onClick={() => go(true)}>Créer un compte</button>
      </div>
      {msg && <p class="hint accent">{msg}</p>}
      <p class="hint">Mot de passe : 6 caractères minimum. À la création, un e-mail de confirmation est envoyé.</p>
    </Card>
  );
}

function MesPositions({ email, cible }: { email: string; cible: { symbol: string; poids: number }[] }) {
  const p = useParametres();
  const snap = useData(api.snapshot);
  const ov = useData(api.overview);
  const [positions, setPositions] = useState<Position[] | null>(null);
  const [erreur, setErreur] = useState("");
  const [tic, setTic] = useState(0);
  useEffect(() => { lirePositions().then(setPositions).catch((e) => setErreur(e.message)); }, [tic]);
  const recharger = () => setTic((t) => t + 1);

  const fx = ov.data?.eurusd ?? EURUSD_SECOURS;
  const infos = useMemo(() => new Map((snap.data ?? []).map((s) => [s.symbol, s])), [snap.data]);

  if (erreur) return <div class="note warn">Lecture impossible : {erreur}</div>;
  if (!positions || (snap.loading && !snap.data?.length)) return <Loading />;

  // Regroupement par titre (plusieurs achats possibles)
  const parTitre = new Map<string, { quantite: number; investi: number; achats: Position[] }>();
  for (const x of positions) {
    const g = parTitre.get(x.symbol) ?? { quantite: 0, investi: 0, achats: [] };
    g.quantite += x.quantite;
    g.investi += x.quantite * (x.prix_achat_eur ?? 0) + (x.frais_eur ?? 0);
    g.achats.push(x);
    parTitre.set(x.symbol, g);
  }
  const lignes = [...parTitre.entries()].map(([symbol, g]) => {
    const s = infos.get(symbol);
    const coursEur = s ? s.close / fx : null;
    const valeur = coursEur != null ? g.quantite * coursEur : null;
    return { symbol, nom: s?.nom, ...g, coursEur, valeur, pv: valeur != null ? valeur - g.investi : null };
  }).sort((a, b) => (b.valeur ?? 0) - (a.valeur ?? 0));
  const total = lignes.reduce((a, l) => a + (l.valeur ?? 0), 0);
  const investi = lignes.reduce((a, l) => a + l.investi, 0);
  const pv = total - investi;

  // Écart avec le portefeuille cible (onglet Hold)
  const poidsCible = new Map(cible.map((c) => [c.symbol, c.poids]));
  const tousTitres = [...new Set([...lignes.map((l) => l.symbol), ...cible.map((c) => c.symbol)])];
  const ecarts = tousTitres.map((sym) => {
    const actuel = lignes.find((l) => l.symbol === sym)?.valeur ?? 0;
    const w = total > 0 ? actuel / total : 0;
    const wc = poidsCible.get(sym) ?? 0;
    return { sym, w, wc, ajuste: (wc - w) * total };
  }).filter((e) => Math.abs(e.w - e.wc) > 0.005).sort((a, b) => Math.abs(b.ajuste) - Math.abs(a.ajuste));
  const depasse = lignes.filter((l) => total > 0 && (l.valeur ?? 0) / total > p.seuilReequilibrage);
  // Ordres pour revenir à la cible : on prépare directement les achats (mêmes outils que dans Portefeuille)
  const achats = ecarts.filter((e) => e.ajuste > 1);
  const totAchat = achats.reduce((a, e) => a + e.ajuste, 0);
  const prixUsd = Object.fromEntries((snap.data ?? []).map((x) => [x.symbol, x.close]));

  return (
    <>
      <Card title="Mon portefeuille réel" right={<button class="link" onClick={async () => { await deconnexion(); }}>Déconnexion</button>}>
        <p class="hint" style={{ marginTop: 0 }}>{email}</p>
        <div class="stats">
          <Stat label="Valeur actuelle" value={`${num(total, 2)} €`} />
          <Stat label="Investi (frais inclus)" value={`${num(investi, 2)} €`} />
          <Stat label="Gain / perte" value={`${pv >= 0 ? "+" : ""}${num(pv, 2)} €`} sub={investi > 0 ? pct(pv / investi, 1) : ""} cls={signClass(pv)} tone={pv >= 0 ? "good" : "bad"} />
        </div>
        {depasse.length > 0 && <div class="note warn">{depasse.map((l) => l.symbol).join(", ")} dépasse {pct(p.seuilReequilibrage, 0, false)} du portefeuille : pense à rééquilibrer.</div>}
      </Card>

      <Card title={`Positions (${lignes.length})`}>
        {!lignes.length ? <p class="hint">Aucune position. Ajoute un achat ci-dessous, ou utilise « J'ai passé ces ordres » dans le plan d'achat.</p> : (
          <table class="table">
            <thead><tr><th>Titre</th><th>Valeur</th><th>+/−</th></tr></thead>
            <tbody>{lignes.map((l) => (
              <tr>
                <td><b>{l.symbol}</b><br /><small class="muted">{num(l.quantite, 4)} × {l.coursEur != null ? `${num(l.coursEur, 2)} €` : "cours n.d."}</small></td>
                <td>{l.valeur != null ? `${num(l.valeur, 2)} €` : "—"}<br /><small class="muted">{total > 0 && l.valeur != null ? pct(l.valeur / total, 1, false) : ""}</small></td>
                <td class={signClass(l.pv)}>{l.pv != null ? `${l.pv >= 0 ? "+" : ""}${num(l.pv, 2)} €` : "—"}<br />
                  <small>{l.pv != null && l.investi > 0 ? pct(l.pv / l.investi, 1) : ""}</small></td>
              </tr>
            ))}</tbody>
          </table>
        )}
        <p class="hint">Valeur au dernier cours de clôture (dollars convertis au taux du jour, 1 € = {num(fx, 4)} $).</p>
      </Card>

      {cible.length > 0 && total > 0 && (
        <Card title="Pour revenir au portefeuille conseillé">
          {!ecarts.length ? <p class="hint">Ton portefeuille correspond à la cible.</p> : (
            <table class="table small">
              <thead><tr><th>Titre</th><th>Actuel</th><th>Cible</th><th>À ajuster</th></tr></thead>
              <tbody>{ecarts.map((e) => (
                <tr><td><b>{e.sym}</b></td><td>{pct(e.w, 1, false)}</td><td>{pct(e.wc, 1, false)}</td>
                  <td class={e.ajuste >= 0 ? "up" : "down"}>{e.ajuste >= 0 ? `acheter ${num(e.ajuste, 2)} €` : `vendre ${num(-e.ajuste, 2)} €`}</td></tr>
              ))}</tbody>
            </table>
          )}
          <p class="hint">En hold, inutile de suivre chaque changement de la cible : rééquilibre une fois par an, ou si une ligne dépasse
            {" "}{pct(p.seuilReequilibrage, 0, false)}. Les ventes se passent directement dans ton appli de courtier ; les achats sont préparés ci-dessous.</p>
          <a class="verifier" href="#/portefeuille">Voir le portefeuille conseillé ›</a>
        </Card>
      )}
      {cible.length > 0 && total > 0 && achats.length > 0 && (
        <PlanAchat capital={totAchat} lignes={achats.map((e) => ({ symbol: e.sym, poids: e.ajuste / totAchat }))}
          prix={prixUsd} eurusd={ov.data?.eurusd ?? null} annees={1} />
      )}

      <Card>
        <Details summary="Ajouter un achat">
          <AjoutPosition infos={infos} fx={fx} fraisDefaut={p.fraisOrdre} onAjout={recharger} />
        </Details>
        <Details summary="Modifier ou supprimer un achat">
          <ul class="liste-achats">{positions.map((x) => <LigneAchat x={x} onChange={recharger} />)}</ul>
        </Details>
      </Card>
    </>
  );
}

function AjoutPosition({ infos, fx, fraisDefaut, onAjout }: {
  infos: Map<string, { symbol: string; nom: string; close: number }>; fx: number; fraisDefaut: number; onAjout: () => void;
}) {
  const [symbol, setSymbol] = useState("");
  const [quantite, setQuantite] = useState("");
  const [prix, setPrix] = useState("");
  const [frais, setFrais] = useState(String(fraisDefaut));
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10));
  const [msg, setMsg] = useState("");
  const s = infos.get(symbol.trim().toUpperCase());
  const enregistrer = async () => {
    const q = Number(quantite.replace(",", ".")), px = Number(prix.replace(",", ".")), fr = Number(frais.replace(",", ".")) || 0;
    if (!s || !(q > 0) || !(px >= 0)) { setMsg("Vérifie le ticker, la quantité et le prix."); return; }
    const err = await ajouterPositions([{ symbol: s.symbol, quantite: q, prix_achat_eur: px, frais_eur: fr, date_achat: date, note: null }]);
    if (err) { setMsg(`Erreur : ${err}`); return; }
    setMsg(`${s.symbol} ajouté.`); setQuantite(""); setPrix(""); onAjout();
  };
  return (
    <div class="form-position">
      <label class="field">Ticker<input value={symbol} placeholder="ex. AAPL" onInput={(e) => setSymbol((e.target as HTMLInputElement).value)} /></label>
      {s && <small class="muted">{s.nom} · cours {num(s.close / fx, 2)} €
        <button class="link petit" onClick={() => setPrix(String(Math.round((s.close / fx) * 100) / 100))}> (utiliser)</button></small>}
      <div class="reglages">
        <label class="field">Quantité<input inputMode="decimal" value={quantite} onInput={(e) => setQuantite((e.target as HTMLInputElement).value)} /></label>
        <label class="field">Prix d'achat (€)<input inputMode="decimal" value={prix} onInput={(e) => setPrix((e.target as HTMLInputElement).value)} /></label>
        <label class="field">Frais (€)<input inputMode="decimal" value={frais} onInput={(e) => setFrais((e.target as HTMLInputElement).value)} /></label>
        <label class="field">Date<input type="date" value={date} onInput={(e) => setDate((e.target as HTMLInputElement).value)} /></label>
      </div>
      <button class="more" onClick={enregistrer}>Enregistrer l'achat</button>
      {msg && <p class="hint accent">{msg}</p>}
    </div>
  );
}

function LigneAchat({ x, onChange }: { x: Position; onChange: () => void }) {
  const [edition, setEdition] = useState(false);
  const [q, setQ] = useState(String(x.quantite));
  const [px, setPx] = useState(String(x.prix_achat_eur ?? ""));
  return (
    <li>
      <span><b>{x.symbol}</b> · {num(x.quantite, 4)} à {x.prix_achat_eur != null ? `${num(x.prix_achat_eur, 2)} €` : "?"} · {dateFr(x.date_achat)}</span>
      {edition ? (
        <span class="edition">
          <input inputMode="decimal" value={q} aria-label="Quantité" onInput={(e) => setQ((e.target as HTMLInputElement).value)} />
          <input inputMode="decimal" value={px} aria-label="Prix d'achat" onInput={(e) => setPx((e.target as HTMLInputElement).value)} />
          <button class="link" onClick={async () => {
            await modifierPosition(x.id, { quantite: Number(q.replace(",", ".")), prix_achat_eur: Number(px.replace(",", ".")) });
            setEdition(false); onChange();
          }}>OK</button>
        </span>
      ) : (
        <span>
          <button class="link petit" onClick={() => setEdition(true)}>modifier</button>{" · "}
          <button class="link petit down" onClick={async () => { if (confirm(`Supprimer cet achat de ${x.symbol} ?`)) { await supprimerPosition(x.id); onChange(); } }}>supprimer</button>
        </span>
      )}
    </li>
  );
}
