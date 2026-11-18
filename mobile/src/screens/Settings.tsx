import { useEffect, useMemo, useState } from "preact/hooks";
import { api } from "../api";
import { Card, Details, RefreshButton, Stat, useData } from "../components";
import { dateFr, ilYA, num, pct } from "../format";
import { frontiere, type Univers } from "../optim";
import { bornesDefaut, definirBornes, type Range, RANGES } from "../ranges";
import { Relance } from "./Relance";
import { ecrireParametres, nbModifies, PARAMETRES_DEFAUT, type Parametres, PRESET_TRADE_REPUBLIC, useParametres } from "../settings";
import { BUILD, definirTelechargementAuto, estNatif, mo, tailleCache, telechargementAuto, VERSION, verifierMiseAJour, viderCache } from "../update";
import { proposerMiseAJour } from "./MiseAJourDialogue";

/** Champ numérique : la valeur stockée est une fraction, affichée en % si `pctAff`. */
function Champ({ label, aide, k, p, pctAff = true, min, max, pas, decimales = 2 }: {
  label: string; aide: string; k: keyof Parametres; p: Parametres; pctAff?: boolean;
  min: number; max: number; pas: number; decimales?: number;
}) {
  const v = p[k] as number;
  const aff = pctAff ? Math.round(v * 100 * 10 ** decimales) / 10 ** decimales : v;
  const defaut = PARAMETRES_DEFAUT[k] as number;
  const modifie = v !== defaut;
  return (
    <label class={`param ${modifie ? "modifie" : ""}`}>
      <span class="param-tete">
        <span>{label}</span>
        <span class="param-saisie">
          <input type="number" inputMode="decimal" min={min} max={max} step={pas} value={aff}
            onChange={(e) => {
              const brut = Number((e.target as HTMLInputElement).value);
              if (!Number.isFinite(brut)) return;
              const borne = Math.min(max, Math.max(min, brut));
              ecrireParametres({ [k]: pctAff ? borne / 100 : Math.round(borne) } as Partial<Parametres>);
            }} />
          {pctAff ? "%" : ""}
        </span>
      </span>
      <small>{aide} {modifie && <button type="button" class="link petit" onClick={() => ecrireParametres({ [k]: defaut } as Partial<Parametres>)}>
        (défaut : {pctAff ? `${num(defaut * 100, decimales)} %` : defaut})</button>}</small>
    </label>
  );
}

export function Settings() {
  const p = useParametres();
  const reco = useData(api.portefeuilleReco);
  const sync = useData(api.lastSync);
  const u = reco.data?.univers as Univers | undefined;
  const apercu = useMemo(() => (u ? frontiere(u, p, 10) : []), [u, p.tauxSansRisque, p.primeRisque, p.poidsHistorique, p.poidsMax, p.nMaxLignes, p.poidsMin]);
  const impossible = p.poidsMax * p.nMaxLignes < 1 - 1e-9;
  const [maj, setMaj] = useState<{ etat: "idle" | "cherche" | "ok" | "erreur"; msg?: string }>({ etat: "idle" });
  const [auto, setAuto] = useState(telechargementAuto());
  const [cache, setCache] = useState(0);
  useEffect(() => { tailleCache().then(setCache); }, [maj.etat]);

  const verifier = async () => {
    setMaj({ etat: "cherche" });
    try {
      const m = await verifierMiseAJour();
      if (m) { setMaj({ etat: "idle" }); proposerMiseAJour(m); } else setMaj({ etat: "ok" });
    } catch (e: any) { setMaj({ etat: "erreur", msg: e?.message ?? String(e) }); }
  };

  return (
    <div class="screen">
      <header class="screen-head">
        <div><h1>Paramètres</h1><p class="sub">{nbModifies(p) ? `${nbModifies(p)} hypothèse(s) modifiée(s)` : "Hypothèses par défaut"}</p></div>
        <RefreshButton />
      </header>

      <Card title="Effet de tes hypothèses" class="tint-accent">
        {impossible ? (
          <div class="note warn">Plafond par titre × nombre de lignes &lt; 100 % : impossible de construire un portefeuille. Augmente l'un des deux.</div>
        ) : !u ? <p class="hint">Disponible après la prochaine synchronisation du serveur.</p> : apercu.length ? (
          <div class="stats">
            <Stat label="Le moins risqué" value={pct(apercu[0].rendement, 1, false)} sub={`volatilité ${pct(apercu[0].volatilite, 0, false)}`} tone="good" />
            <Stat label="Le plus rentable" value={pct(apercu[apercu.length - 1].rendement, 1, false)} sub={`volatilité ${pct(apercu[apercu.length - 1].volatilite, 0, false)}`} tone="info" />
          </div>
        ) : <p class="hint">Aucun portefeuille possible avec ces réglages.</p>}
        <p class="hint">Rentabilités attendues par an. Elles se recalculent sur le téléphone à chaque changement, l'onglet Portefeuille aussi.</p>
      </Card>

      <Card title="Rentabilité attendue des titres">
        <Champ p={p} k="tauxSansRisque" label="Taux sans risque" min={0} max={10} pas={0.05}
          aide="Rendement d'un placement sans risque en dollars (bons du Trésor US). Sert de base à tous les rendements attendus." />
        <Champ p={p} k="primeRisque" label="Prime de risque actions" min={0} max={12} pas={0.25}
          aide="Supplément annuel attendu des actions au-dessus du taux sans risque, pour un titre qui bouge comme le marché (bêta 1). Historiquement 4 à 6 %." />
        <Champ p={p} k="poidsHistorique" label="Part de l'historique" min={0} max={100} pas={5} decimales={0}
          aide="Poids du rendement des 3 dernières années dans l'estimation (le reste vient du modèle CAPM). Les titres étant choisis parce qu'ils ont monté, une part élevée rend les estimations trop optimistes." />
      </Card>

      <Card title="Construction du portefeuille">
        <Champ p={p} k="poidsMax" label="Plafond par titre" min={5} max={100} pas={1} decimales={0}
          aide="Part maximale d'un seul titre. Plus bas = plus diversifié, mais rentabilité maximale plus faible." />
        <Champ p={p} k="nMaxLignes" label="Nombre maximal de lignes" pctAff={false} min={1} max={40} pas={1}
          aide="Au-delà, trop de petits ordres pour un petit capital (frais, suivi)." />
        <Champ p={p} k="poidsMin" label="Poids minimal d'une ligne" min={0} max={20} pas={0.5} decimales={1}
          aide="Les lignes plus petites sont supprimées et le portefeuille est ré-optimisé sans elles." />
      </Card>

      <Card title="Passage des ordres" right={<button class="link" onClick={() => ecrireParametres(PRESET_TRADE_REPUBLIC)}>Préréglage Trade Republic</button>}>
        <div class="param">
          <span class="param-tete"><span>Devise des prix d'ordre</span></span>
          <div class="seg full" role="group" aria-label="Devise">
            <button class={p.deviseOrdres === "EUR" ? "on" : ""} onClick={() => ecrireParametres({ deviseOrdres: "EUR" })}>Euros (Trade Republic)</button>
            <button class={p.deviseOrdres === "USD" ? "on" : ""} onClick={() => ecrireParametres({ deviseOrdres: "USD" })}>Dollars</button>
          </div>
          <small>Trade Republic cote les actions américaines en euros (bourse Lang &amp; Schwarz) : pas de frais de change séparé,
            1 € de frais par ordre (les plans d'épargne sont gratuits).</small>
        </div>
        <Champ p={p} k="fraisOrdre" label="Frais par ordre (€)" pctAff={false} min={0} max={20} pas={0.5}
          aide="Ce que ton courtier facture à chaque achat. 0 € chez la plupart des courtiers « sans frais »." />
        <Champ p={p} k="fraisChange" label="Frais de change" min={0} max={2} pas={0.05}
          aide="Coût de la conversion euros → dollars (et retour à la revente). Souvent 0 à 0,25 %." />
        <Champ p={p} k="margeLimite" label="Marge du prix limite" min={0} max={3} pas={0.1} decimales={1}
          aide="Prix limite = dernier cours + cette marge. Plus haut = exécution plus sûre, mais tu peux payer un peu plus cher." />
        <label class="toggle">
          <input type="checkbox" checked={p.fractions} onChange={(e) => ecrireParametres({ fractions: (e.target as HTMLInputElement).checked })} />
          Mon courtier accepte les fractions d'actions
        </label>
      </Card>

      <Card title="Projection et suivi">
        <div class="param">
          <span class="param-tete"><span>Niveau de la fourchette</span></span>
          <div class="seg full" role="group" aria-label="Niveau de confiance">
            {[0.8, 0.9, 0.95].map((c) => <button class={p.confiance === c ? "on" : ""} onClick={() => ecrireParametres({ confiance: c })}>{pct(c, 0, false)}</button>)}
          </div>
          <small>Part des scénarios simulés comprise entre « scénario bas » et « scénario haut » dans l'onglet Portefeuille.
            95 % = fourchette plus large, plus prudente.</small>
        </div>
        <Champ p={p} k="seuilReequilibrage" label="Seuil de rééquilibrage" min={10} max={60} pas={1} decimales={0}
          aide="En hold, rééquilibrer (une fois par an) dès qu'une ligne dépasse ce poids à cause de sa hausse." />
      </Card>

      <Card title="Mode court terme">
        <Champ p={p} k="ctNbTitres" label="Nombre de titres" pctAff={false} min={1} max={30} pas={1}
          aide="Les N titres les mieux classés par le modèle 1 mois." />
        <Champ p={p} k="ctScoreMin" label="Score IA minimal" min={50} max={99} pas={1} decimales={0}
          aide="Rang minimal dans le classement du modèle (80 % = parmi les 20 % premiers)." />
        <div class="param">
          <span class="param-tete"><span>Rotation</span></span>
          <div class="seg full" role="group" aria-label="Fréquence de rotation">
            <button class={p.ctRotation === "semaine" ? "on" : ""} onClick={() => ecrireParametres({ ctRotation: "semaine" })}>Chaque semaine</button>
            <button class={p.ctRotation === "mois" ? "on" : ""} onClick={() => ecrireParametres({ ctRotation: "mois" })}>Chaque mois</button>
          </div>
          <small>À quelle fréquence on renouvelle la sélection. Plus souvent = plus de frais et de change.</small>
        </div>
      </Card>

      <Card title="Fourchettes de lecture des indicateurs">
        <p class="hint" style={{ marginTop: 0 }}>Seuils qui colorent les indicateurs (rouge / gris / vert). Valeurs en %, sauf multiples (x) et points.</p>
        {Object.entries(RANGES).map(([k, r]) => <LigneBornes k={k} r={r} />)}
      </Card>

      <Card title="Hypothèses du serveur (fixes)">
        <ul class="liste-fixe">
          <li><b>Candidats</b> : les 40 meilleurs titres par momentum 12-1 mois divisé par la volatilité (S&P 500, Nasdaq-100, ETF).</li>
          <li><b>Exclusion</b> : titres en détresse financière (Z-Score Altman &lt; 1,81).</li>
          <li><b>Estimation</b> : 3 ans de cours quotidiens ; covariance Ledoit-Wolf ; bêta mesuré contre SPY.</li>
          <li><b>Projection à l'horizon</b> : modèle log-normal ; fourchette = 90 % des scénarios.</li>
          <li><b>Données</b> : synchronisation {sync.data ? ilYA(sync.data.finished_at ?? sync.data.started_at) : "—"}
            {reco.data?.updated_at && <> · candidats du {dateFr(reco.data.updated_at)}</>}.</li>
        </ul>
      </Card>

      <Card title="Application">
        <div class="stats">
          <Stat label="Version installée" value={VERSION} sub={estNatif() ? "application Android" : "version web"} />
        </div>
        <button class="more" onClick={verifier} disabled={maj.etat === "cherche"}>
          {maj.etat === "cherche" ? "Recherche…" : "Vérifier les mises à jour"}
        </button>
        {maj.etat === "ok" && <p class="hint">{BUILD === "dev" ? "Build de développement : mise à jour désactivée." : `Thésée est à jour (${VERSION}).`}</p>}
        {maj.etat === "erreur" && <div class="note warn">Vérification impossible : {maj.msg}</div>}
        {estNatif() ? (
          <>
            <label class="toggle">
              <input type="checkbox" checked={auto} onChange={(e) => { const v = (e.target as HTMLInputElement).checked; setAuto(v); definirTelechargementAuto(v); }} />
              Télécharger automatiquement les mises à jour au lancement (installation ensuite en un appui)
            </label>
            <p class="hint">Fichiers de mise à jour : {cache ? mo(cache) : "0 Mo"}
              {cache > 0 && <> — <button class="link" onClick={async () => { await viderCache(); setCache(await tailleCache()); }}>libérer</button></>}</p>
            <p class="hint">L'appli vérifie à chaque lancement et propose la nouvelle version dans une fenêtre. Build {BUILD}.</p>
          </>
        ) : <p class="hint">Version web : elle se met à jour toute seule au rechargement de la page. Build {BUILD}.</p>}
        <button class="link" onClick={() => { if (confirm("Remettre toutes les hypothèses par défaut ?")) ecrireParametres(null); }}>
          Remettre toutes les hypothèses par défaut</button>
      </Card>

      <Card title="Calculs du serveur">
        <Relance />
      </Card>

      <nav class="menu-avance" aria-label="Avancé">
        <a href="#/parametres/calculs">Fiche de calculs détaillée ›</a>
      </nav>
    </div>
  );
}

/** Une ligne de bornes éditables (affichées en % pour les indicateurs en pourcentage). */
function LigneBornes({ k, r }: { k: string; r: Range }) {
  useParametres(); // se redessine quand les bornes changent
  const f = r.unite === "pct" ? 100 : 1;
  const [b1, b2] = r.bornes;
  const def = bornesDefaut(k);
  const modifie = b1 !== def[0] || b2 !== def[1];
  const maj = (i: 0 | 1, v: number) => {
    if (!Number.isFinite(v)) return;
    const nb: [number, number] = [...r.bornes] as [number, number];
    nb[i] = v / f;
    if (nb[0] <= nb[1]) definirBornes(k, nb);
  };
  const u = r.unite === "pct" ? "%" : r.unite === "x" ? "x" : "";
  return (
    <div class={`bornes ${modifie ? "modifie" : ""}`}>
      <span class="bornes-nom">{r.label}</span>
      <span class="bornes-zones">
        <span class={`badge ${r.zones[0].ton}`}>{r.zones[0].nom}</span>
        <input type="number" inputMode="decimal" step="any" value={Math.round(b1 * f * 100) / 100} aria-label={`${r.label} : borne basse`}
          onChange={(e) => maj(0, Number((e.target as HTMLInputElement).value))} />{u}
        <span class={`badge ${r.zones[1].ton}`}>{r.zones[1].nom}</span>
        <input type="number" inputMode="decimal" step="any" value={Math.round(b2 * f * 100) / 100} aria-label={`${r.label} : borne haute`}
          onChange={(e) => maj(1, Number((e.target as HTMLInputElement).value))} />{u}
        <span class={`badge ${r.zones[2].ton}`}>{r.zones[2].nom}</span>
      </span>
      {modifie && <button class="link petit" onClick={() => definirBornes(k, null)}>défaut</button>}
    </div>
  );
}
