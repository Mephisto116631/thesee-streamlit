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
import { univers as universFiable, useFiabiliteVol } from "../fiabilite";
import { ChoixSourceVol } from "./Portfolio";

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
  const fiab = useFiabiliteVol();
  const u = universFiable((reco.data?.univers_facteurs ?? reco.data?.univers ?? undefined) as Univers | undefined, fiab);
  const apercu = useMemo(() => (u ? frontiere(u, p, 10) : []), [u, p.tauxSansRisque, p.primeRisque, p.poidsHistorique, p.poidsMax, p.nMaxLignes, p.poidsMin, p.sourceVol, fiab.probant]);
  const bt = useData(api.backtestVol);
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

      <Card title="Ce que changent tes réglages" class="tint-accent">
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

      <Card title="Comment j'estime la rentabilité des titres ?" repliable ouvert={false}>
        <Champ p={p} k="tauxSansRisque" label="Taux sans risque" min={0} max={10} pas={0.05}
          aide="Rendement d'un placement sans risque en dollars (bons du Trésor US). Sert de base à tous les rendements attendus." />
        <Champ p={p} k="primeRisque" label="Prime de risque actions" min={0} max={12} pas={0.25}
          aide="Supplément annuel attendu des actions au-dessus du taux sans risque, pour un titre qui bouge comme le marché (bêta 1). Historiquement 4 à 6 %." />
        <Champ p={p} k="poidsHistorique" label="Part de l'historique" min={0} max={100} pas={5} decimales={0}
          aide="Poids du rendement des 3 dernières années dans l'estimation (le reste vient du modèle CAPM). Les titres étant choisis parce qu'ils ont monté, une part élevée rend les estimations trop optimistes." />
      </Card>

      <Card title="Comment je construis le portefeuille ?" repliable ouvert={false}>
        <Champ p={p} k="poidsMax" label="Plafond par titre" min={5} max={100} pas={1} decimales={0}
          aide="Part maximale d'un seul titre. Plus bas = plus diversifié, mais rentabilité maximale plus faible." />
        <Champ p={p} k="nMaxLignes" label="Nombre maximal de lignes" pctAff={false} min={1} max={40} pas={1}
          aide="Au-delà, trop de petits ordres pour un petit capital (frais, suivi)." />
        <Champ p={p} k="poidsMin" label="Poids minimal d'une ligne" min={0} max={20} pas={0.5} decimales={1}
          aide="Les lignes plus petites sont supprimées et le portefeuille est ré-optimisé sans elles." />
      </Card>

      <Card title="Comment je mesure le risque ?" repliable ouvert={false}>
        <ChoixSourceVol volIA={p.sourceVol === "ia" && Boolean(u?.vol_ia?.length)} dispo={Boolean(u?.vol_ia?.length)} fiab={fiab}
          libelleIA="Prévue par l'IA" />
        <p class="hint">L'IA de risque prévoit la volatilité des 6 prochains mois de chaque titre (corrélations : 3 ans d'historique).
          Elle n'est proposée que si son dernier test est probant ; elle est re-testée chaque mois et suivie en conditions réelles.</p>
        {fiab.probant && bt.data?.diagnostics?.variantes && (
          <>
            <h3 class="h3">Ce qu'aurait donné chaque choix (backtest {bt.data.diagnostics.n_mois} mois depuis 2013)</h3>
            <table class="table small">
              <thead><tr><th>Volatilité</th><th>Risque réel</th><th>Rendement / an</th><th>Rendement / risque</th></tr></thead>
              <tbody>{([["hist_3a", "Historique 3 ans"], ["naif_3m", "3 derniers mois"], ["ia", "IA"]] as const).map(([k, nom]) => {
                const v = bt.data.diagnostics.variantes[k];
                return v && <tr><td>{nom}</td><td>{pct(v.vol_reelle, 1, false)}</td><td>{pct(v.rendement_annuel, 1, false)}</td>
                  <td><b>{num(v.rendement_annuel / v.vol_reelle, 2)}</b></td></tr>;
              })}</tbody>
            </table>
            <p class="hint">Portefeuille Hold reconstruit chaque mois avec les règles de l'appli, mesuré le mois suivant.
              L'IA donne un portefeuille <b>plus calme</b> ({pct(bt.data.diagnostics.ia_vs_hist_3a?.part_mois_moins_risque, 0, false)} des mois
              moins risqués), mais le rendement baisse presque autant : le rapport rendement / risque reste proche.
              Choisis l'IA si tu préfères la stabilité.</p>
          </>
        )}
      </Card>

      <Card title="Comment je passe mes ordres ?" repliable ouvert={false} right={<button class="link" onClick={() => ecrireParametres(PRESET_TRADE_REPUBLIC)}>Préréglage Trade Republic</button>}>
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

      <Card title="Comment je projette et je suis ?" repliable ouvert={false}>
        <div class="param">
          <span class="param-tete"><span>Niveau de la fourchette</span></span>
          <div class="seg full" role="group" aria-label="Niveau de confiance">
            {[0.8, 0.9, 0.95].map((c) => <button class={p.confiance === c ? "on" : ""} onClick={() => ecrireParametres({ confiance: c })}>{pct(c, 0, false)}</button>)}
          </div>
          <small>Part des scénarios simulés comprise entre « scénario bas » et « scénario haut » dans l'onglet Portefeuille.
            95 % = fourchette plus large, plus prudente.</small>
        </div>
        <Champ p={p} k="seuilReequilibrage" label="Seuil de rééquilibrage" min={10} max={60} pas={1} decimales={0}
          aide="Entre deux révisions, rééquilibrer seulement si une ligne dépasse ce poids à cause de sa hausse." />
        <div class="param">
          <span class="param-tete"><span>Révision du portefeuille conseillé</span></span>
          <div class="seg full" role="group" aria-label="Rythme de révision">
            {([6, 12] as const).map((r) => <button class={(p.rythmeRevision ?? 6) === r ? "on" : ""}
              onClick={() => ecrireParametres({ rythmeRevision: r })}>{r === 6 ? "Tous les 6 mois" : "Tous les ans"}</button>)}
          </div>
          <small>Le portefeuille conseillé ne change qu'à ces dates (janvier, et juillet si 6 mois). Suivre chaque mois la
            recommandation du jour coûtait environ 180 ordres par an, soit 3 à 5 points de rendement en frais (backtest 2006-2026).</small>
        </div>
      </Card>

      <Card title="Quand un indicateur est-il bon ou mauvais ?" repliable ouvert={false}>
        <p class="hint" style={{ marginTop: 0 }}>Seuils qui colorent les indicateurs (rouge / gris / vert). Valeurs en %, sauf multiples (x) et points.</p>
        {Object.entries(RANGES).map(([k, r]) => <LigneBornes k={k} r={r} />)}
      </Card>

      <Card title="Ce que le serveur fixe" repliable ouvert={false}>
        <ul class="liste-fixe">
          <li><b>Candidats</b> : tous les titres du S&P 500 ayant 3 ans d'historique ({u?.symbols.length || "~500"} titres),
            sans tri préalable. L'ancienne présélection par momentum (ce qui a le plus monté) a été retirée : elle n'a pas été probante.</li>
          <li><b>Exclusion</b> : titres en détresse financière (Z-Score Altman &lt; 1,81).</li>
          <li><b>Estimation</b> : 3 ans de cours quotidiens ; covariance Ledoit-Wolf résumée en 20 facteurs + risque propre de chaque titre
            (variance de chaque titre exacte) ; bêta mesuré contre SPY.</li>
          <li><b>Optimisation</b> : même algorithme sur le serveur et le téléphone (gradient projeté accéléré, FISTA).
            Historique des choix : docs/METHODE.md du dépôt.</li>
          <li><b>Projection à l'horizon</b> : rendements composés, écarts selon une loi de Student à 5 degrés (queues épaisses) ; fourchette = 90 % des scénarios.</li>
          <li><b>Données</b> : synchronisation {sync.data ? ilYA(sync.data.finished_at ?? sync.data.started_at) : "—"}
            {reco.data?.updated_at && <> · candidats du {dateFr(reco.data.updated_at)}</>}.</li>
        </ul>
      </Card>

      <Card title="Version et mises à jour" repliable ouvert={false}>
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

      <Card title="Relancer les calculs" repliable ouvert={false}>
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
