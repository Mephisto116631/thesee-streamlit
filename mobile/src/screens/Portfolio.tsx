import { useCallback, useMemo, useState } from "preact/hooks";
import { api } from "../api";
import { BarreSeuil, Card, ChartBox, cssVar, HelpButton, Info, Loading, OfflineNote, RefreshButton, ReglagesButton, Stat, toneOf, useData, Verifier } from "../components";
import { frontiere as calculerFrontiere, sousUnivers, variance, type Univers } from "../optim";
import { ecrireParametres, nbModifies, useParametres } from "../settings";
import { dateFr, ilYA, num, pct, ratioPct } from "../format";
import { choisirPoint, choisirPointRisque, HORIZON_DEFAUT, HORIZONS, planAchat, projection } from "../strategy";
import { libelleSource, univers as universFiable, useFiabiliteVol, type FiabiliteVol } from "../fiabilite";
import { choisirRevision, prochaineRevision } from "../revision";
import { MonteCarlo } from "./MonteCarlo";
import { PlanAchat } from "./PlanAchat";

const KEY = "thesee:objectif:v1";
// Hold : horizons de 6 mois et plus (en dessous, c'est le mode court terme)
const HORIZONS_HOLD = HORIZONS.filter((x) => x.annees >= 0.5);
export interface Etat {
  capital: number; cible: number; horizon: string; mode: "rendement" | "risque"; volMax: number;
  exclus: string[]; imposes: string[];   // ajustements de l'utilisateur parmi les candidats
}
const DEFAUT: Etat = { capital: 200, cible: 0.08, horizon: HORIZON_DEFAUT, mode: "rendement", volMax: 0.15, exclus: [], imposes: [] };
const charger = (): Etat => {
  try { return { ...DEFAUT, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") }; } catch { return DEFAUT; }
};

/** Objectif de l'utilisateur et portefeuille conseillé qui en découle : partagé par l'accueil,
 *  le portefeuille et les positions (l'objectif est gardé sur le téléphone). */
export function usePortefeuilleCible() {
  const [e, setE] = useState<Etat>(charger());
  const maj = (p: Partial<Etat>) => {
    const n = { ...e, ...p };
    setE(n);
    try { localStorage.setItem(KEY, JSON.stringify(n)); } catch { /* ignore */ }
  };
  const reco = useData(api.portefeuilleReco);
  const ov = useData(api.overview);
  const snap = useData(api.snapshot);

  const h = HORIZONS_HOLD.find((x) => x.k === e.horizon) ?? HORIZONS_HOLD.find((x) => x.k === "1a")!;
  const params = useParametres();
  // La prévision IA n'entre dans le calcul que si son dernier test est probant
  const fiab = useFiabiliteVol();
  // Univers figé à la dernière révision de mon rythme (6 ou 12 mois) ; sinon celui du jour
  const revs = useData(api.revisions);
  const revision = choisirRevision(revs.data, params.rythmeRevision ?? 6);
  const u = universFiable((revision?.univers_facteurs ?? reco.data?.univers_facteurs ?? reco.data?.univers ?? undefined) as Univers | undefined, fiab);
  // Marge de sécurité du mode « Je limite le risque », apprise sur le passé par le laboratoire
  const runs = useData(api.models);
  const margeRun = runs.data?.find((r) => r.kind === "marge_risque");
  const marge = Math.min(1.5, Math.max(0.5, Number(margeRun?.diagnostics?.marge) || 1));
  // Frontière recalculée sur le téléphone avec les hypothèses de la page Paramètres
  // (repli : celle du serveur si l'univers n'est pas encore publié).
  // Titres exclus / imposés par l'utilisateur : même optimiseur, sur le sous-univers
  const frontiere = useMemo(() => (u ? calculerFrontiere(sousUnivers(u, e.exclus), { ...params, imposes: e.imposes }) : reco.data?.frontiere ?? []),
    [u, revision?.date, reco.data?.frontiere, params.tauxSansRisque, params.primeRisque, params.poidsHistorique, params.poidsMax, params.nMaxLignes,
      params.poidsMin, params.sourceVol, fiab.probant, e.exclus.join(","), e.imposes.join(",")]);
  const modifies = nbModifies(params);
  const choix = e.mode === "risque" ? choisirPointRisque(frontiere, e.volMax * marge) : choisirPoint(frontiere, e.cible);
  const volIA = params.sourceVol === "ia" && Boolean(u?.vol_ia?.length);
  const volHistDe = new Map((u?.symbols ?? []).map((sy, i) => [sy, Math.sqrt(Math.max(variance(u!, i), 0))]));
  const volIADe = new Map((u?.symbols ?? []).map((sy, i) => [sy, u?.vol_ia?.[i] ?? null]));
  const lignes = choix?.point.lignes ?? [];
  // Meilleure rentabilité de long terme possible pour le risque du portefeuille choisi (frontière)
  const maxAuRisque = choix ? Math.max(...frontiere.filter((f) => f.volatilite <= choix.point.volatilite + 0.0025).map((f) => f.rendement)) : null;
  const revisionInfo = { date: revision?.date ?? null, prochaine: prochaineRevision(params.rythmeRevision ?? 6) };
  const margeInfo = { m: marge, part: margeRun?.diagnostics?.part_respectee as number | undefined,
    depuis: margeRun?.diagnostics?.depuis as string | undefined, connue: Boolean(margeRun) };
  return { e, maj, reco, ov, snap, h, params, u, frontiere, modifies, choix, volIA, volHistDe, volIADe, lignes, fiab, maxAuRisque,
    revisionInfo, margeInfo };
}

export function Portfolio() {
  const { e, maj, reco, ov, snap, h, params, u, frontiere, modifies, choix, volIA, volHistDe, volIADe, lignes, fiab, maxAuRisque,
    revisionInfo, margeInfo } = usePortefeuilleCible();
  const nomPrev = `prévu (${libelleSource(fiab.source)})`;
  const prix: Record<string, number | null | undefined> = {
    ...Object.fromEntries(Object.entries(reco.data?.titres ?? {}).map(([k, v]) => [k, v.prix])),
    ...Object.fromEntries((snap.data ?? []).map((x) => [x.symbol, x.close])),
  };
  const proj = choix ? projection(e.capital, choix.point.rendement, choix.point.volatilite, h.annees, e.cible, params.confiance) : null;
  const fx = ov.data?.eurusd ?? 1.08;
  const frais = choix ? planAchat(e.capital, lignes, prix, fx, { fraisOrdre: params.fraisOrdre, fraisChange: params.fraisChange,
    fractions: params.fractions, margeLimite: params.margeLimite, tranches: 1, frequence: "mois" }) : null;
  const queue = pct((1 - params.confiance) / 2, 0, false);
  const ajuste = e.exclus.length + e.imposes.length;

  return (
    <div class="screen">
      <header class="screen-head">
        <div><h1>Portefeuille</h1><p class="sub">{num(e.capital, 0)} € · horizon {h.label}{ajuste ? ` · ${ajuste} ajustement(s)` : ""}</p></div>
        <HelpButton keys={["sharpe", "volatility", "max_drawdown"]} intro={<>
          <p><b>Objectif</b> : tu fixes soit la rentabilité visée, soit le risque maximal. L'appli choisit, parmi les ~500 titres du S&P 500,
            le meilleur compromis (frontière efficiente de Markowitz, 20 % max par titre).</p>
          <p><b>Risque</b> : la volatilité de chaque titre, mesurée sur 3 ans ou prévue par l'IA. La prévision de l'IA n'est proposée
            que si son dernier test est probant (re-test chaque mois).</p>
          <p><b>Rentabilité de long terme (hypothèse)</b> : ce n'est pas une prévision (aucun modèle testé ne prévoit les rendements),
            mais la récompense moyenne du risque sur longue période, selon le modèle CAPM (Capital Asset Pricing Model : taux sans
            risque + bêta × prime de risque). Réglable dans les Paramètres.</p>
          <p><b>Ajuster les titres</b> : exclus ou impose des titres ; le calcul reste exactement le même.</p>
        </>} />
        <RefreshButton />
        <ReglagesButton />
      </header>
      {modifies > 0 && <div class="note">Calculé avec {modifies} hypothèse(s) personnalisée(s) — <a href="#/parametres">voir les Paramètres</a>.</div>}
      <OfflineNote res={reco.res} />

      {/* 1. Objectif : ce que je fixe */}
      <Card title="Mon objectif" class="tint-accent" repliable>
        <div class="stats">
          <label class="field" style={{ flex: 1 }}>Montant (€)
            <input type="number" inputMode="numeric" min={50} step={50} value={e.capital}
              onChange={(ev) => maj({ capital: Math.max(50, Number((ev.target as HTMLInputElement).value) || 200) })} />
          </label>
        </div>
        <div class="field" style={{ marginTop: 8 }}>Durée de placement
          <div class="chips wrap" role="group" aria-label="Horizon">
            {HORIZONS_HOLD.map((x) => <button class={`chip ${e.horizon === x.k ? "on" : ""}`} onClick={() => maj({ horizon: x.k })}>{x.label}</button>)}
          </div>
        </div>
        <div class="seg full" role="group" aria-label="Ce que je fixe" style={{ marginTop: 10 }}>
          <button class={e.mode === "rendement" ? "on" : ""} onClick={() => maj({ mode: "rendement" })}>Je vise une rentabilité</button>
          <button class={e.mode === "risque" ? "on" : ""} onClick={() => maj({ mode: "risque" })}>Je limite le risque</button>
        </div>
        {e.mode === "rendement" ? (
          <div class="field">
            <span>Rentabilité visée : <b class="accent">{pct(e.cible, 0, false)} par an</b></span>
            <input type="range" min={0.02} max={0.3} step={0.01} value={e.cible} aria-label="Rentabilité visée par an"
              onInput={(ev) => maj({ cible: Number((ev.target as HTMLInputElement).value) })} />
            <div class="range-labels"><span>2 %</span><span>8 % ≈ actions long terme</span><span>30 %</span></div>
          </div>
        ) : (
          <div class="field">
            <span>Risque maximal : <b class="accent">{pct(e.volMax, 0, false)} de volatilité par an</b></span>
            <input type="range" min={0.08} max={0.35} step={0.01} value={e.volMax} aria-label="Volatilité maximale par an"
              onInput={(ev) => maj({ volMax: Number((ev.target as HTMLInputElement).value) })} />
            <div class="range-labels"><span>8 % calme</span><span>≈ 18 % S&P 500</span><span>35 % agité</span></div>
            {margeInfo.connue ? (
              <p class="hint">Visé : <b>{pct(e.volMax * margeInfo.m, 1, false)}</b> pour tenir ta limite de {pct(e.volMax, 0, false)}
                {margeInfo.part != null && <> · respectée {pct(margeInfo.part, 0, false)} des semestres depuis {String(margeInfo.depuis ?? "").slice(0, 4)}</>}.
                <Info>Le risque réel dépasse souvent le risque prévu. L'appli vise donc un peu en dessous de ta limite : la marge est
                  apprise sur le passé seulement, pour tenir la limite au moins 70 % des semestres.</Info></p>
            ) : <p class="hint">Par le passé, cette limite a souvent été dépassée : le risque réel varie plus que prévu.</p>}
          </div>
        )}
        <ChoixSourceVol volIA={volIA} dispo={Boolean(u?.vol_ia?.length)} fiab={fiab} />
        {fiab.probant && <BacktestVol />}
      </Card>

      {reco.loading && !reco.data ? <Loading /> : !choix ? (
        <div class="note">Le portefeuille sera disponible après la prochaine synchronisation du serveur.</div>
      ) : (
        <>
          {/* 2. Synthèse : la réponse en un coup d'œil */}
          <Card title="Mon portefeuille en un coup d'œil" class={`edge-${choix.atteignable ? "good" : "bad"}`} id="synthese">
            {!choix.atteignable && (
              <div class="note warn">{e.mode === "risque"
                ? <>Aucun portefeuille n'est aussi calme avec ces titres : le plus calme possible est à <b>{pct(choix.point.volatilite, 0, false)}</b>.</>
                : <>{pct(e.cible, 0, false)} par an n'est pas atteignable (20 % max par titre) : maximum <b>{pct(choix.max, 1, false)}</b>. Portefeuille affiché : le plus rentable.</>}</div>
            )}
            <div class="stats">
              <Stat label="Titres" value={String(lignes.length)} sub={`${num(e.capital, 0)} € investis`} />
              <Stat label={<>Rentabilité de long terme<Info>Hypothèse, pas une prévision : la récompense moyenne du risque sur longue
                période (modèle CAPM, Capital Asset Pricing Model : taux sans risque + bêta × prime de risque). Aucun modèle testé ne
                prévoit les rendements de façon fiable. Réglable dans les Paramètres.</Info></>}
                value={`${pct(choix.point.rendement, 1, false)}/an`} sub="hypothèse" />
              <Stat label="Rendement / risque" value={<>{ratioPct(choix.point.rendement, choix.point.volatilite)}<Info>
                Pour 1 point de volatilité supporté, {num(choix.point.rendement / choix.point.volatilite, 2)} point de rentabilité de long terme par an (hypothèse).
                Plus c'est haut, mieux le risque est payé.</Info></>} />
            </div>
            <JaugeRisque vol={choix.point.volatilite} source={volIA ? nomPrev : "historique 3 ans"} teste={volIA} />
            {maxAuRisque != null && (
              <p class="hint">Avec ce risque ({pct(choix.point.volatilite, 0, false)} {volIA ? "prévu" : "mesuré"}), la rentabilité de long terme
                maximale est <b>{pct(maxAuRisque, 1, false)}/an</b> (hypothèse).
                {e.mode === "rendement" && <> Pour fixer d'abord le risque et viser ce maximum, choisis « Je limite le risque ».</>}</p>
            )}
            {proj && (
              <>
                <h3 class="h3">Dans {h.label}, tes {num(e.capital, 0)} € deviendraient</h3>
                <div class="stats">
                  <Stat label={`Mauvais cas (${queue})`} value={`${num(proj.bas, 0)} €`} tone={proj.bas < e.capital ? "bad" : "good"} />
                  <Stat label="Cas médian" value={`${num(proj.median, 0)} €`} tone={proj.median >= e.capital ? "good" : "bad"} />
                  <Stat label={`Bon cas (${queue})`} value={`${num(proj.haut, 0)} €`} tone="good" />
                </div>
                <div class="barre-proba"><span>Risque de finir en perte</span><b class={proj.probPerte > 0.3 ? "down" : ""}>{pct(proj.probPerte, 0, false)}</b></div>
                <div class="jauge-simple"><div style={{ width: `${Math.min(100, proj.probPerte * 100)}%` }} /></div>
                <p class="hint">La largeur de la fourchette vient du risque ({volIA ? `${nomPrev}, testé` : "mesuré sur 3 ans"}) ;
                  son centre vient de l'hypothèse de rentabilité de long terme.</p>
              </>
            )}
            <p class="hint">{revisionInfo.date ? <>Portefeuille révisé le <b>{dateFr(revisionInfo.date)}</b>
              {" "}· prochaine révision le <b>{dateFr(revisionInfo.prochaine.toISOString())}</b></> : <>Prochaine révision le <b>{dateFr(revisionInfo.prochaine.toISOString())}</b></>}
              {" "}(tous les {params.rythmeRevision ?? 6} mois, réglable dans les Paramètres). Entre deux révisions, on garde les titres.</p>
            {frais && <p class="hint">Frais à l'achat : <b>{num(frais.totalFrais, 2)} €</b> ({pct(frais.partFrais, 2, false)}) pour {frais.nbOrdres} ordres.</p>}
            <Verifier href="#/parametres/calculs/risque" />
          </Card>

          {/* 3. Les titres */}
          <Card title={`Les ${lignes.length} titres`} repliable id="titres">
            <table class="table">
              <thead><tr><th>Titre</th><th>Part</th><th>Risque<br /><small>{u?.vol_ia ? "3 ans · IA" : "3 ans"}</small></th><th>Montant</th></tr></thead>
              <tbody>{lignes.map((l) => {
                const t = reco.data?.titres?.[l.symbol];
                const maxP = Math.max(...lignes.map((x) => x.poids));
                const vi = volIADe.get(l.symbol), vh = volHistDe.get(l.symbol);
                return (
                  <tr>
                    <td><a href={`#/titre/${l.symbol}`}><b>{l.symbol}</b></a>{e.imposes.includes(l.symbol) && <small class="accent"> imposé</small>}
                      <br /><small class="muted">{t?.nom ?? ""}</small></td>
                    <td><div class="wbar"><div style={{ width: `${(l.poids / maxP) * 100}%` }} /></div>{pct(l.poids, 1, false)}</td>
                    <td class="nowrap">{pct(vh, 0, false)}{vi != null && <> · <b class={(vi ?? 0) > (vh ?? 0) ? "down" : "up"}>{pct(vi, 0, false)}</b></>}</td>
                    <td><b>{num(l.poids * e.capital, 2)} €</b></td>
                  </tr>
                );
              })}</tbody>
            </table>
            <p class="hint">Risque = volatilité annuelle.{u?.vol_ia ? <> La seconde valeur est la prévision de l'IA pour les 6 prochains mois
              (verte si plus calme que l'historique), <BadgeTeste />.</> : ""} Touche un titre pour sa fiche.</p>
            <h3 class="h3">Tous les compromis possibles</h3>
            <Frontiere frontiere={frontiere} choisi={choix.point.rendement} cible={e.cible} />
            <p class="hint">Chaque point est le meilleur portefeuille pour un niveau de risque (frontière efficiente). Le point orange est le tien.</p>
            <Verifier href="#/parametres/calculs/rendement" />
          </Card>

          {/* 4. Ajuster */}
          {u && <AjusterTitres u={u} e={e} maj={maj} retenus={lignes.map((l) => l.symbol)} volHistDe={volHistDe} />}

          {/* 5. Simulation */}
          <Card title={`Simulation sur ${h.label}`} repliable ouvert={false}>
            <MonteCarlo lignes={lignes} capital={e.capital} annees={h.annees} volCible={choix.point.volatilite}
              source={volIA ? "prévue par l'IA" : "historique 3 ans"} />
            <Verifier href="#/parametres/calculs/projection" />
          </Card>

          {/* 6. Passer à l'action */}
          <PlanAchat capital={e.capital} lignes={lignes} prix={prix} eurusd={ov.data?.eurusd ?? null} annees={h.annees} />

          <Card title="Réglages du calcul" repliable ouvert={false}>
            <p class="hint" style={{ marginTop: 0 }}>Les réglages qui changent ce portefeuille. Tous les autres sont dans les <a href="#/parametres">Paramètres</a>.</p>
            <ReglageNombre label="Plafond par titre" valeur={params.poidsMax} min={0.05} max={1} pas={0.01} pctAff onChange={(v) => ecrireParametres({ poidsMax: v })} />
            <ReglageNombre label="Nombre maximal de titres" valeur={params.nMaxLignes} min={1} max={40} pas={1} onChange={(v) => ecrireParametres({ nMaxLignes: v })} />
            <ReglageNombre label="Frais par ordre (€)" valeur={params.fraisOrdre} min={0} max={10} pas={0.5} onChange={(v) => ecrireParametres({ fraisOrdre: v })} />
            <p class="hint">Mis à jour {ilYA(reco.data?.updated_at)} · {reco.data?.methode}</p>
          </Card>
        </>
      )}
    </div>
  );
}

/** Badge « testée ✓ » : renvoie à la preuve (Analyse › Modèles IA). */
export function BadgeTeste({ texte = "testée" }: { texte?: string }) {
  return <a class="badge-teste" href="#/risque/ia" title="Voir la preuve">{texte} ✓</a>;
}

/** Choix de la volatilité : la prévision de l'IA n'est proposée que si elle est prouvée. */
export function ChoixSourceVol({ volIA, dispo, fiab, libelleIA }: {
  volIA: boolean; dispo: boolean; fiab: FiabiliteVol; libelleIA?: string;
}) {
  if (!fiab.probant) {
    return fiab.connu ? (
      <p class="hint">Risque mesuré sur <b>3 ans d'historique</b>. La prévision de l'IA est retirée : son dernier test
        (<a href="#/risque/ia">voir</a>) n'est pas probant.</p>
    ) : <p class="hint">Risque mesuré sur <b>3 ans d'historique</b>.</p>;
  }
  return (
    <div class="field" style={{ marginTop: 6 }}>Risque mesuré avec
      <div class="seg full" role="group" aria-label="Source de volatilité">
        <button class={!volIA ? "on" : ""} onClick={() => ecrireParametres({ sourceVol: "historique" })}>Historique 3 ans</button>
        <button class={volIA ? "on" : ""} disabled={!dispo} onClick={() => ecrireParametres({ sourceVol: "ia" })}>{libelleIA ?? `Prévision ${libelleSource(fiab.source)}`}</button>
      </div>
      <small class="muted">{fiab.source === "hybride" ? "Prévision sur 6 mois : ordre des titres par l'IA, niveau par HAR" : fiab.source === "har" ? "Prévision HAR sur 6 mois" : "Prévision de l'IA sur 6 mois"} <BadgeTeste />{!dispo && " · disponible après la prochaine synchronisation"}</small>
    </div>
  );
}

/** Jauge visuelle du risque : calme ↔ agité, avec le repère du S&P 500 (~18 %). */
function JaugeRisque({ vol, source, teste }: { vol: number; source: string; teste?: boolean }) {
  const pos = (v: number) => `${Math.max(0, Math.min(100, ((v - 0.05) / 0.35) * 100))}%`;
  const mot = vol < 0.12 ? "calme" : vol < 0.2 ? "comme le marché" : vol < 0.28 ? "agité" : "très agité";
  return (
    <div style={{ marginTop: 10 }}>
      <div class="barre-proba"><span>Risque : <b>{pct(vol, 0, false)}</b> de volatilité par an ({source}{teste && <>, <BadgeTeste texte="testé" /></>})</span><b>{mot}</b></div>
      <div class="jauge"><span class="curseur" style={{ left: pos(vol) }} /><span class="spx" style={{ left: pos(0.18) }}>S&P 500</span></div>
      <div class="jauge-labels"><span>calme</span><span>agité</span></div>
    </div>
  );
}

/** Ajuster les titres : exclure ou imposer parmi les candidats ; même calcul derrière. */
function AjusterTitres({ u, e, maj, retenus, volHistDe }: {
  u: Univers; e: Etat; maj: (p: Partial<Etat>) => void; retenus: string[]; volHistDe: Map<string, number>;
}) {
  const reco = useData(api.portefeuilleReco);
  const etat = (s: string) => (e.exclus.includes(s) ? "exclu" : e.imposes.includes(s) ? "impose" : "auto");
  const regler = (s: string, v: "exclu" | "auto" | "impose") => maj({
    exclus: v === "exclu" ? [...e.exclus.filter((x) => x !== s), s] : e.exclus.filter((x) => x !== s),
    imposes: v === "impose" ? [...e.imposes.filter((x) => x !== s), s] : e.imposes.filter((x) => x !== s),
  });
  const [q, setQ] = useState("");
  // ~500 titres : on montre ceux ajustés et retenus, puis le résultat de la recherche
  const ajustes = [...e.exclus, ...e.imposes];
  const qq = q.trim().toUpperCase();
  const trouves = qq ? u.symbols.filter((s) => s.includes(qq) || (reco.data?.titres?.[s]?.nom ?? "").toUpperCase().includes(qq)).slice(0, 30) : [];
  const liste = [...new Set([...ajustes, ...retenus, ...trouves])].filter((s) => u.symbols.includes(s) || e.exclus.includes(s));
  return (
    <Card title="Ajuster les titres" repliable ouvert={false} class="ajuster">
      <p class="hint" style={{ marginTop: 0 }}>Exclus un titre que tu ne veux pas, ou impose un titre que tu veux garder, parmi les
        {" "}{u.symbols.length} titres du S&P 500. Le portefeuille est recalculé avec exactement la même méthode et tes réglages.</p>
      <input type="search" placeholder="Chercher un titre (ex. KO, Coca-Cola)" value={q} aria-label="Chercher un titre"
        onInput={(ev) => setQ((ev.target as HTMLInputElement).value)} />
      {(e.exclus.length > 0 || e.imposes.length > 0) && <button class="link" onClick={() => maj({ exclus: [], imposes: [] })}>↺ Revenir au conseil</button>}
      <ul>{liste.map((s) => {
        const t = reco.data?.titres?.[s];
        const v = etat(s);
        return (
          <li><span class="nom"><b>{s}</b>{retenus.includes(s) && <small class="accent"> · retenu</small>}
            <small>{t?.nom ?? ""}{volHistDe.has(s) ? ` · risque ${pct(volHistDe.get(s), 0, false)}` : ""}</small></span>
            <span class="tri" role="group" aria-label={`Réglage ${s}`}>
              <button class={v === "exclu" ? "on" : ""} onClick={() => regler(s, "exclu")}>Exclure</button>
              <button class={v === "auto" ? "on" : ""} onClick={() => regler(s, "auto")}>Auto</button>
              <button class={v === "impose" ? "on" : ""} onClick={() => regler(s, "impose")}>Imposer</button>
            </span></li>
        );
      })}</ul>
      {qq && !trouves.length && <p class="hint">Aucun titre du S&P 500 ne correspond.</p>}
    </Card>
  );
}

/** Backtest de la volatilité IA, à côté du choix (replié). */
function BacktestVol() {
  const bt = useData(api.backtestVol);
  const v = bt.data?.diagnostics?.variantes;
  if (!v) return null;
  return (
    <details class="details">
      <summary>Qu'aurait donné chaque choix depuis 2013 ?</summary>
      <div class="details-body">
        <table class="table small">
          <thead><tr><th>Risque mesuré</th><th>Risque réel</th><th>Rentab. / an</th><th>Rend. / risque</th></tr></thead>
          <tbody>{([["hist_3a", "Historique 3 ans"], ["ia", "Prévision IA"]] as const).map(([k, nom]) => v[k] && (
            <tr><td>{nom}</td><td>{pct(v[k].vol_reelle, 1, false)}</td><td>{pct(v[k].rendement_annuel, 1, false)}</td>
              <td><b>{ratioPct(v[k].rendement_annuel, v[k].vol_reelle)}</b></td></tr>
          ))}</tbody>
        </table>
        <p class="hint">Portefeuille reconstruit chaque mois sur {bt.data.diagnostics.n_mois} mois. L'IA donne un portefeuille plus calme
          ({pct(bt.data.diagnostics.ia_vs_hist_3a?.part_mois_moins_risque, 0, false)} des mois), pour un rendement un peu plus faible.</p>
        <BarreSeuil t={-(bt.data.diagnostics.ia_vs_hist_3a?.t ?? 0)} seuil={2.5} />
      </div>
    </details>
  );
}

function ReglageNombre({ label, valeur, min, max, pas, pctAff, onChange }: {
  label: string; valeur: number; min: number; max: number; pas: number; pctAff?: boolean; onChange: (v: number) => void;
}) {
  return (
    <label class="field" style={{ marginTop: 8 }}>
      <span>{label} : <b>{pctAff ? pct(valeur, 0, false) : num(valeur, pas < 1 ? 1 : 0)}</b></span>
      <input type="range" min={min} max={max} step={pas} value={valeur} onInput={(ev) => onChange(Number((ev.target as HTMLInputElement).value))} />
    </label>
  );
}

/** Frontière efficiente : risque (x) / rentabilité attendue (y), point choisi en évidence. */
function Frontiere({ frontiere, choisi, cible }: { frontiere: { rendement: number; volatilite: number }[]; choisi: number; cible: number }) {
  const cfg = useCallback(() => {
    const pts = [...frontiere].sort((a, b) => a.volatilite - b.volatilite);
    const accent = cssVar("--accent");
    return {
      type: "line",
      data: {
        datasets: [
          { label: "Frontière efficiente", data: pts.map((p) => ({ x: p.volatilite * 100, y: p.rendement * 100 })),
            borderColor: cssVar("--info"), borderWidth: 2, pointRadius: 2, tension: 0.3 },
          { label: "Ton portefeuille", data: pts.filter((p) => Math.abs(p.rendement - choisi) < 1e-9).map((p) => ({ x: p.volatilite * 100, y: p.rendement * 100 })),
            borderColor: accent, backgroundColor: accent, pointRadius: 7, showLine: false },
          { label: "Objectif", data: [{ x: pts[0].volatilite * 100, y: cible * 100 }, { x: pts[pts.length - 1].volatilite * 100, y: cible * 100 }],
            borderColor: cssVar("--muted"), borderDash: [4, 3], borderWidth: 1, pointRadius: 0 },
        ],
      },
      options: {
        plugins: { legend: { position: "bottom" } },
        scales: {
          x: { type: "linear", title: { display: true, text: "Risque (volatilité %/an)", color: cssVar("--muted") } },
          y: { title: { display: true, text: "Rentabilité de long terme %/an (hypothèse)", color: cssVar("--muted") } },
        },
      },
    };
  }, [frontiere, choisi, cible]);
  if (frontiere.length < 2) return null;
  return <ChartBox config={cfg} height={220} label="Frontière efficiente : rentabilité attendue selon le risque" />;
}
