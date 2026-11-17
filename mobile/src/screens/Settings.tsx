import { useEffect, useMemo, useState } from "preact/hooks";
import { api } from "../api";
import { Card, Details, RefreshButton, Stat, useData } from "../components";
import { dateFr, ilYA, num, pct } from "../format";
import { frontiere, type Univers } from "../optim";
import { RANGES, bornesTexte } from "../ranges";
import { ecrireParametres, nbModifies, PARAMETRES_DEFAUT, type Parametres, useParametres } from "../settings";
import { BUILD, estNatif, installer, type MiseAJour, VERSION, verifierMiseAJour } from "../update";

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
  const [maj, setMaj] = useState<{ etat: "idle" | "cherche" | "ok" | "dispo" | "erreur"; info?: MiseAJour; msg?: string }>({ etat: "idle" });

  const verifier = async () => {
    setMaj({ etat: "cherche" });
    try {
      const m = await verifierMiseAJour(true);
      setMaj(m ? { etat: "dispo", info: m } : { etat: "ok" });
    } catch (e: any) { setMaj({ etat: "erreur", msg: e?.message ?? String(e) }); }
  };
  useEffect(() => { /* rien au montage : la vérification auto est faite par l'appli */ }, []);

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

      <Card title="Passage des ordres">
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

      <Card title="Hypothèses du serveur (fixes)">
        <ul class="liste-fixe">
          <li><b>Candidats</b> : les 40 meilleurs titres par momentum 12-1 mois divisé par la volatilité (S&P 500, Nasdaq-100, ETF).</li>
          <li><b>Exclusion</b> : titres en détresse financière (Z-Score Altman &lt; 1,81).</li>
          <li><b>Estimation</b> : 3 ans de cours quotidiens ; covariance Ledoit-Wolf ; bêta mesuré contre SPY.</li>
          <li><b>Projection à l'horizon</b> : modèle log-normal ; fourchette = 90 % des scénarios.</li>
          <li><b>Données</b> : synchronisation {sync.data ? ilYA(sync.data.finished_at ?? sync.data.started_at) : "—"}
            {reco.data?.updated_at && <> · candidats du {dateFr(reco.data.updated_at)}</>}.</li>
        </ul>
        <Details summary="Fourchettes de lecture des indicateurs">
          <table class="table small">
            <tbody>{Object.entries(RANGES).map(([k, r]) => {
              const t = bornesTexte(k);
              return <tr><td>{r.label}</td><td class="muted">{r.zones.map((z, i) => `${z.nom} ${t[i]}`).join(" · ")}</td></tr>;
            })}</tbody>
          </table>
        </Details>
      </Card>

      <Card title="Application">
        <div class="stats">
          <Stat label="Version installée" value={VERSION} sub={estNatif() ? "application Android" : "version web"} />
        </div>
        <button class="more" onClick={verifier} disabled={maj.etat === "cherche"}>
          {maj.etat === "cherche" ? "Recherche…" : "Vérifier les mises à jour"}
        </button>
        {maj.etat === "ok" && <p class="hint">Tu as la dernière version.</p>}
        {maj.etat === "erreur" && <div class="note warn">Vérification impossible : {maj.msg}</div>}
        {maj.etat === "dispo" && maj.info && (
          <div class="note">Version {maj.info.version} disponible ({dateFr(maj.info.date)}).
            <button class="more" onClick={() => installer(maj.info!)}>Télécharger et installer</button></div>
        )}
        <p class="hint">L'appli vérifie seule au démarrage (toutes les 6 h au plus). Build {BUILD}.</p>
        <button class="link" onClick={() => { if (confirm("Remettre toutes les hypothèses par défaut ?")) ecrireParametres(null); }}>
          Remettre toutes les hypothèses par défaut</button>
      </Card>
    </div>
  );
}
