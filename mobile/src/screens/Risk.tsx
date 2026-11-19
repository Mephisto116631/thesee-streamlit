import { useCallback, useState } from "preact/hooks";
import { api, type ModelRun } from "../api";
import { BarreSeuil, Card, ChartBox, cssVar, Details, HelpButton, Loading, OfflineNote, RangeBar, Stat, toneOf, useData, ZoneBadge, RefreshButton } from "../components";
import { corr, dateFr, ilYA, num, pb, pct, signClass } from "../format";
import { Relance } from "./Relance";
import { isIG } from "./Stock";

export function Risk({ tab, go }: { tab: "credit" | "ia"; go: (h: string) => void }) {
  return (
    <div class="screen">
      <header class="screen-head">
        <div><h1>Risque & IA</h1></div>
        <RefreshButton />
        <HelpButton keys={tab === "credit" ? ["spread_pct", "z_score"] : ["gain_pts", "proba_hausse"]}
          intro={tab === "credit"
            ? <p>Le <b>spread</b> est la prime (en points de base, 100 pb = 1 %) exigée au-dessus des emprunts d'État pour prêter aux entreprises. HY = High Yield (notes ≤ BB+), IG = Investment Grade (notes ≥ BBB-).</p>
            : <p>Le modèle XGBoost prédit si le prochain <b>mouvement significatif</b> (&gt; 0,3 %) sera une hausse ou une baisse. Sa qualité est mesurée sur une période qu'il n'a jamais vue, et comparée à une <b>règle naïve</b> qui répond toujours la direction la plus fréquente.</p>} />
      </header>
      <div class="seg full" role="tablist">
        <button role="tab" aria-selected={tab === "credit"} class={tab === "credit" ? "on" : ""} onClick={() => go("#/risque")}>Crédit</button>
        <button role="tab" aria-selected={tab === "ia"} class={tab === "ia" ? "on" : ""} onClick={() => go("#/risque/ia")}>Modèle IA</button>
      </div>
      {tab === "credit" ? <Credit go={go} /> : <Models />}
    </div>
  );
}

function Credit({ go }: { go: (h: string) => void }) {
  const ov = useData(api.overview);
  const sp = useData(api.spreads);
  const snap = useData(api.snapshot);
  const o = ov.data;

  const cfg = useCallback(() => {
    const hy = (sp.data ?? []).filter((p) => p.serie_id === "BAMLH0A0HYM2");
    const igMap = new Map((sp.data ?? []).filter((p) => p.serie_id === "BAMLC0A0CM").map((p) => [p.date, p.valeur]));
    return {
      type: "line",
      data: {
        labels: hy.map((p) => dateFr(p.date)),
        datasets: [
          { label: "High Yield (pb)", data: hy.map((p) => p.valeur * 100), borderColor: cssVar("--down"), borderWidth: 1.5, pointRadius: 0 },
          { label: "Investment Grade (pb)", data: hy.map((p) => (igMap.get(p.date) ?? NaN) * 100), borderColor: cssVar("--info"), borderWidth: 1.5, pointRadius: 0 },
        ],
      },
      options: { plugins: { legend: { position: "bottom" } } },
    };
  }, [sp.data]);

  const z = (snap.data ?? []).filter((s) => s.z_score !== null || s.rating_sp).sort((a, b) => (a.z_score ?? 99) - (b.z_score ?? 99));

  return (
    <>
      <OfflineNote res={ov.res} />
      {o && (
        <Card title="Combien coûte d'emprunter pour les entreprises ?">
          <div class="stats">
            <Stat label="High Yield" value={pb(o.hy_spread_bp)} sub={`fourchette 10 ans ${pb(o.hy_min_10y)} – ${pb(o.hy_max_10y)}`} />
            <Stat label="Investment Grade" value={pb(o.ig_spread_bp)} sub={`fourchette 10 ans ${pb(o.ig_min_10y)} – ${pb(o.ig_max_10y)}`} />
          </div>
          <RangeBar k="spread_pct" v={o.hy_pct_10y} median={50} medianLabel="médiane 10 ans" />
        </Card>
      )}
      <Card title="Historique 3 ans (source FRED)" repliable ouvert={false}>
        {sp.loading && !sp.data?.length ? <Loading /> : sp.data?.length ? <ChartBox config={cfg} height={230} label="Spreads de crédit High Yield et Investment Grade sur 3 ans" /> : <p class="hint">Pas de données FRED (clé FRED_API_KEY absente du cron ?).</p>}
      </Card>
      <Card title="Santé financière des titres suivis" repliable ouvert={false}>
        {!z.length ? <p class="hint">Aucun Z-Score publié.</p> : (
          <table class="table">
            <thead><tr><th>Titre</th><th>Z-Score</th><th>Note S&P</th></tr></thead>
            <tbody>{z.map((s) => (
              <tr onClick={() => go(`#/titre/${s.symbol}`)} class="clickable">
                <td><b>{s.symbol}</b></td>
                <td>{num(s.z_score, 2)} <ZoneBadge k="z_score" v={s.z_score} /></td>
                <td>{s.rating_sp ?? "—"} {s.rating_sp && <small class={isIG(s.rating_sp) ? "up" : "down"}>{isIG(s.rating_sp) ? "IG" : "HY"}</small>}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
        <p class="hint">Z-Score &gt; 2,99 sain · 1,81–2,99 zone grise · &lt; 1,81 détresse. Peu pertinent pour les banques (JPM, V, MA).</p>
      </Card>
    </>
  );
}

type Choix = "court" | "6m" | "1a" | "jour";
const CHOIX: { k: Choix; label: string }[] = [
  { k: "6m", label: "6 mois" }, { k: "1a", label: "1 an" }, { k: "court", label: "1 mois" }, { k: "jour", label: "1 jour (ancien)" },
];

function Models() {
  const models = useData(api.models);
  const [choix, setChoix] = useState<Choix>("6m");
  const [kind, setKind] = useState<"actions" | "etf">("actions");
  const mh = models.data?.find((x) => x.kind === `horizon_${choix}`);
  const m = models.data?.find((x) => x.kind === kind);
  return (
    <>
      <OfflineNote res={models.res} />
      <div class="chips wrap" role="group" aria-label="Horizon du modèle">
        {CHOIX.map((c) => <button class={`chip ${choix === c.k ? "on" : ""}`} onClick={() => setChoix(c.k)}>{c.label}</button>)}
      </div>
      {choix === "jour" ? (
        <>
          <div class="note">Ancien modèle : devine la direction du lendemain. À 1 jour, les marchés sont proches du hasard ; gardé pour comparaison.</div>
          <div class="seg" role="group" aria-label="Modèle">
            <button class={kind === "actions" ? "on" : ""} onClick={() => setKind("actions")}>Actions</button>
            <button class={kind === "etf" ? "on" : ""} onClick={() => setKind("etf")}>ETF</button>
          </div>
          {models.loading && !m ? <Loading /> : !m ? <div class="note">Modèle non publié.</div> : <ModelView m={m} />}
        </>
      ) : models.loading && !mh ? <Loading /> : !mh ? (
        <div class="note">Modèle {CHOIX.find((c) => c.k === choix)?.label} pas encore entraîné : relance le calcul ci-dessous.</div>
      ) : <HorizonView m={mh} />}
      <Laboratoire />
      <Card title="Relancer">
        <Relance />
      </Card>
    </>
  );
}

const VERDICT_H: Record<string, { ton: string; nom: string; txt: string }> = {
  signal: { ton: "good", nom: "Signal", txt: "Le classement utilisé a été nettement et régulièrement lié aux performances réelles en test." },
  bruit: { ton: "neutral", nom: "Faible", txt: "Léger lien avec la réalité, pas assez net pour être fiable : à prendre comme un indice, pas une décision." },
  aucun: { ton: "bad", nom: "Aucun avantage", txt: "Pas de lien mesurable entre le classement et les performances réelles : ne pas s'en servir." },
};

const LIBELLES_CONFIG: Record<string, string> = {
  xgb_prudent: "XGB prudent", xgb_standard: "XGB standard", xgb_riche: "XGB riche", lineaire: "Linéaire",
};
// Sens de lecture des facteurs surveillés : [valeur élevée, valeur faible]
const SENS: Record<string, [string, string, string]> = {
  vol_3m: ["Volatilité 3 mois", "les plus volatils", "les plus calmes"],
  vol_idio: ["Volatilité propre (hors marché)", "les plus agités", "les plus réguliers"],
  liquidite: ["Taille (montants échangés)", "les plus grandes valeurs", "les plus petites valeurs"],
  beta_1a: ["Bêta (sensibilité au marché)", "les plus sensibles au marché", "les moins sensibles"],
  max_1m: ["Effet « loterie »", "ceux qui ont fait un gros bond d'un jour", "ceux sans gros bond"],
};
const sens = (f: string, x: number | null | undefined, seuil: number) =>
  x == null || Math.abs(x) < seuil ? "ni l'un ni l'autre" : x > 0 ? SENS[f][1] : SENS[f][2];

const SOURCES: Record<string, string> = {
  modele: "modèle IA (XGBoost, « eXtreme Gradient Boosting » : une suite d'arbres de décision qui corrigent chacun les erreurs des précédents)",
  momentum: "momentum 12-1 mois (ce qui a le plus monté sur un an, hors dernier mois)",
  multifacteurs: "score multi-facteurs (momentum + faible volatilité + proximité du plus haut 1 an)",
};

/** Modèle « horizon » : classement relatif des titres, évalué par l'IC. */
function HorizonView({ m }: { m: ModelRun }) {
  const d = m.diagnostics ?? {};
  const v = VERDICT_H[m.verdict] ?? VERDICT_H.aucun;
  const imp = m.importance ?? [];
  const maxImp = Math.max(1e-9, ...imp.map((x) => x.importance));
  const totImp = Math.max(1e-9, imp.reduce((a, x) => a + x.importance, 0));
  const q: number[] = d.rendement_par_quintile ?? [];
  const maxQ = Math.max(1e-9, ...q.map((x) => Math.abs(x ?? 0)));
  return (
    <>
      <Card title="Le modèle est-il fiable ?" class={`edge-${v.ton}`} right={<small class="muted">entraîné {ilYA(m.trained_at)}</small>}>
        <p class="verdict"><span class={`badge ${v.ton}`}>{v.nom}</span> {v.txt}</p>
        <div class="note">Classement utilisé : <b>{SOURCES[d.source as string] ?? "modèle IA"}</b>.
          {d.source !== "modele" && " Le modèle IA (XGBoost) a fait moins bien en test : il reste entraîné à chaque calcul et reprendra la main s'il devient meilleur."}
          {d.debut_test && <> Testé depuis {dateFr(d.debut_test)} (données depuis {dateFr(d.debut_donnees)}) : environ {num(d.n_effectif, 0)} périodes indépendantes.</>}
          {d.seuil_t != null && <> « Signal » exige t &gt; {num(d.seuil_t, 1)} (seuil relevé : peu de périodes et meilleur de 3 classements).</>}
          <BarreSeuil t={d.source === "momentum" ? d.t_momentum : d.source === "multifacteurs" ? d.t_multifacteurs : d.t_stat} seuil={d.seuil_t} />
          {d.config_libelle && <> Réglage du modèle IA : {d.config_libelle}, choisi sur le passé uniquement.</>}</div>
        <div class="stats">
          <Stat label="IC modèle IA" value={corr(d.ic_moyen)} sub={`t = ${num(d.t_stat, 1)}`} tone={d.source === "modele" ? v.ton : "neutral"} />
          <Stat label="IC momentum" value={corr(d.ic_momentum)} sub={`t = ${num(d.t_momentum, 1)}`} tone={d.source === "momentum" ? v.ton : "neutral"} />
          <Stat label="IC multi-facteurs" value={corr(d.ic_multifacteurs)} sub={`t = ${num(d.t_multifacteurs, 1)}`} tone={d.source === "multifacteurs" ? v.ton : "neutral"} />
        </div>
        <p class="hint">L'<b>IC</b> (« Information Coefficient », coefficient d'information) mesure, date par date, si les titres classés en tête ont réellement fait mieux
          que les autres sur les {d.horizon_jours} jours de bourse suivants (corrélation de rang, de −100 % à +100 %). En gestion, un IC de 5 % stable est déjà bon.
          Le <b>t</b> (statistique de Student) dit si l'IC moyen se distingue du hasard : plus il est grand, moins le résultat
          peut être un coup de chance.</p>
      </Card>

      {q.length === 5 && (
        <Card title="Les titres les mieux classés ont-ils fait mieux ?" repliable ouvert={false} id="quintiles">
          <ul class="imp">{q.map((x, i) => (
            <li><span>{["Q1 (les moins bien classés)", "Q2", "Q3", "Q4", "Q5 (les mieux classés)"][i]}</span>
              <div class="qbar"><div class={x >= 0 ? "pos" : "neg"} style={{ width: `${(Math.abs(x) / maxQ) * 50}%`, [x >= 0 ? "left" : "right"]: "50%" }} /></div>
              <b class={signClass(x)}>{pct(x, 1)}</b></li>
          ))}</ul>
          <p class="hint">Rendement moyen par rapport à la médiane, sur {d.horizon_jours} jours de bourse, en période de test.
            Écart Q5 − Q1 : <b>{pct(d.spread_quintiles, 1)}</b>. Les titres du top quintile ont battu la médiane
            {d.taux_reussite_top != null && <> dans <b>{pct(d.taux_reussite_top, 0, false)}</b> des cas</>}.</p>
        </Card>
      )}

      <Card title="Ce qui compte pour le modèle" repliable ouvert={false}>
        <ul class="imp">{imp.map((x) => (
          <li><span>{x.label}</span><div class="wbar"><div style={{ width: `${(x.importance / maxImp) * 100}%` }} /></div><b class="imp-val">{pct(x.importance / totImp, 0, false)}</b></li>
        ))}</ul>
      </Card>

      {d.controles && (
        <Card title="Contrôles anti-biais" repliable ouvert={false}>
          <table class="table small">
            <thead><tr><th>Facteur</th><th>Le modèle favorise</th><th>En réalité, ont fait mieux</th></tr></thead>
            <tbody>{Object.keys(SENS).filter((f) => d.controles.facteurs?.[f]).map((f) => {
              const c = d.controles.facteurs[f];
              return <tr><td>{SENS[f][0]}</td>
                <td>{sens(f, c.modele, 0.05)} <small class="muted">({corr(c.modele, 0)})</small></td>
                <td>{sens(f, c.realite, 0.01)} <small class="muted">(IC {corr(c.realite)})</small></td></tr>;
            })}</tbody>
          </table>
          <div class="stats">
            <Stat label="IC chez les grandes valeurs" value={corr(d.controles.ic_grandes)} tone={(d.controles.ic_grandes ?? 0) > 0.02 ? "good" : "neutral"} />
            <Stat label="IC chez les petites valeurs" value={corr(d.controles.ic_petites)} tone="neutral" />
          </div>
          <p class="hint">Les cours des entreprises disparues (faillites) manquent : ce sont surtout des petites valeurs très volatiles.
            Si le modèle favorise les titres <b>petits et volatils</b> et ne marche que chez les petites valeurs, son résultat est suspect.
            S'il marche aussi chez les <b>grandes valeurs</b> (moitié la plus échangée, rarement disparue par faillite), il est plus crédible.
            Colonne « modèle » : corrélation entre le score et le facteur (de −100 % à +100 %).</p>
        </Card>
      )}

      <Card>
        <Details summary="Détails de l'évaluation">
          <table class="table small">
            <thead><tr><th>Période de test</th><th>IC</th><th>Dates</th><th>Réglage</th></tr></thead>
            <tbody>{(d.fenetres ?? []).map((f: any) => <tr><td>{dateFr(f.debut)} → {dateFr(f.fin)}</td><td class={signClass(f.ic)}>{corr(f.ic)}</td><td>{f.n_dates}</td><td class="muted">{LIBELLES_CONFIG[f.config] ?? "—"}</td></tr>)}</tbody>
          </table>
          <p class="hint">Validation « walk-forward » : le modèle est entraîné sur le passé puis testé sur la période suivante,
            avec un écart de {d.horizon_jours} jours de bourse entre les deux pour qu'il ne voie jamais le futur. {d.n_dates_test} dates testées,
            soit environ {num(d.n_effectif, 0)} observations indépendantes (les périodes de {d.horizon_jours} jours de bourse se chevauchent).
            {d.composition_historique
              ? <> À chaque date, seuls les titres réellement dans le S&P 500 (« Standard & Poor's 500 », les 500 grandes entreprises américaines) ce jour-là sont pris en compte (~{num(d.titres_par_date, 0)} par date). Les titres disparus depuis (faillites, rachats) n'ont plus de cours chez Yahoo : les résultats restent un peu optimistes.</>
              : <> Univers = composition actuelle de l'indice : les titres disparus ou entrés depuis faussent le test (biais du survivant), les résultats sont donc optimistes.</>}</p>
        </Details>
      </Card>
    </>
  );
}

function ModelView({ m }: { m: ModelRun }) {
  const d = m.diagnostics ?? {};
  const imp = m.importance ?? [];
  const maxImp = Math.max(1e-9, ...imp.map((x) => x.importance));
  const totImp = Math.max(1e-9, imp.reduce((a, x) => a + x.importance, 0));
  const wf = d.walk_forward;
  return (
    <>
      <Card title="Verdict" right={<small class="muted">entraîné {ilYA(m.trained_at)}</small>}>
        <RangeBar k="gain_pts" v={m.gain_pts} />
        <div class="stats">
          <Stat label="Modèle" value={`${num(m.accuracy, 1)} %`} sub="bonnes directions" tone={toneOf("gain_pts", m.gain_pts)} />
          <Stat label="Règle naïve" value={`${num(m.baseline, 1)} %`} sub="toujours la plus fréquente" tone="neutral" />
          {wf?.accuracy_moyenne != null && <Stat label="Stabilité" value={`${num(wf.accuracy_moyenne, 1)} ± ${num(wf.accuracy_ecart_type, 1)}`} sub={`${wf.fenetres.length} périodes`} />}
        </div>
        <p class="hint">Un modèle de marché qui dépasse durablement 52-53 % est déjà rare : les marchés sont proches du hasard à 1 jour.</p>
      </Card>

      <Card title="Facteurs les plus utilisés">
        <ul class="imp">{imp.slice(0, 10).map((x) => (
          <li><span>{x.label}</span><div class="wbar"><div style={{ width: `${(x.importance / maxImp) * 100}%` }} /></div><b class="imp-val">{pct(x.importance / totImp, 0, false)}</b></li>
        ))}</ul>
      </Card>

      <Card>
        <Details summary="Détails pour data scientist">
          {d.confusion_matrix && (
            <>
              <h3 class="h3">Matrice de confusion ({d.n_test} observations de test)</h3>
              <table class="table small">
                <thead><tr><th></th><th>Prédit baisse</th><th>Prédit hausse</th></tr></thead>
                <tbody>
                  <tr><th>Réel baisse</th><td>{d.confusion_matrix[0][0]}</td><td>{d.confusion_matrix[0][1]}</td></tr>
                  <tr><th>Réel hausse</th><td>{d.confusion_matrix[1][0]}</td><td>{d.confusion_matrix[1][1]}</td></tr>
                </tbody>
              </table>
            </>
          )}
          <div class="stats">
            <Stat label="Précision" value={`${num(d.precision, 1)} %`} />
            <Stat label="Rappel" value={`${num(d.recall, 1)} %`} />
            <Stat label="ROC AUC" value={d.roc_auc != null ? `${num(d.roc_auc, 1)} %` : "—"} sub="50 % = hasard" />
            <Stat label="Log loss" value={num(d.logloss_modele, 4)} sub={`naïf : ${num(d.logloss_baseline, 4)}`} />
            <Stat label="Brier" value={num(d.brier_score, 3)} sub="0,25 = pile ou face" />
          </div>
          {d.perf_par_regime?.length > 0 && (
            <>
              <h3 class="h3">Par régime de marché</h3>
              <table class="table small"><tbody>{d.perf_par_regime.map((r: any) => <tr><td>{r.regime}</td><td>{num(r.accuracy, 1)} %</td><td class="muted">{r.n_observations} obs.</td></tr>)}</tbody></table>
            </>
          )}
          {wf?.fenetres?.length > 0 && (
            <>
              <h3 class="h3">Walk-forward (périodes successives)</h3>
              <table class="table small"><tbody>{wf.fenetres.map((f: any) => <tr><td>{dateFr(f.date_debut)} → {dateFr(f.date_fin)}</td><td>{num(f.accuracy, 1)} %</td></tr>)}</tbody></table>
            </>
          )}
          {d.calibration_bins?.length > 0 && (
            <>
              <h3 class="h3">Calibration</h3>
              <table class="table small">
                <thead><tr><th>Proba prédite</th><th>Moyenne</th><th>Réel</th></tr></thead>
                <tbody>{d.calibration_bins.map((c: any) => <tr><td>{c.tranche}</td><td>{num(c.proba_moyenne_predite, 1)} %</td><td>{num(c.taux_reel_observe, 1)} %</td></tr>)}</tbody>
              </table>
            </>
          )}
          <p class="hint">Zone neutre : {d.n_exclus_zone_neutre ?? "—"} mouvements &lt; {d.seuil_neutre != null ? num(d.seuil_neutre * 100, 1) : "—"} % exclus. Train {d.n_train} / test {d.n_test}.</p>
        </Details>
      </Card>
    </>
  );
}

const NOMS_LABO: Record<string, string> = {
  reference: "Modèle publié", alpha: "Sans effet marché (alpha)", alpha_secteur: "Alpha par secteur",
  alpha_secteur_sans_taille: "Alpha par secteur, sans la taille", fondamentaux: "Cours + comptes des entreprises",
  fondamentaux_seuls: "Comptes des entreprises seuls", risque_volatilite: "IA de risque : volatilité",
  risque_perte_max: "IA de risque : perte maximale", backtest_volatilite_sharpe_max: "Portefeuille avec la volatilité IA",
  backtest_volatilite_variance_min: "Portefeuille le plus calme avec la volatilité IA",
};

/** Laboratoire : variantes du modèle essayées sans toucher aux scores publiés (experiences.py). */
function Laboratoire() {
  const ex = useData(api.experiences);
  const lignes = ex.data ?? [];
  if (!lignes.length) return null;
  // Dernier résultat de chaque variante × horizon (les lots peuvent ne relancer qu'une partie des essais)
  const vus = new Set<string>();
  const lot = lignes.filter((e) => { const k = `${e.nom}|${e.horizon}`; if (vus.has(k)) return false; vus.add(k); return true; }).reverse();
  const n = Math.max(...lot.filter((e) => !e.nom.startsWith("risque") && !e.nom.startsWith("backtest")).map((e) => e.n_essais ?? 0), 0);
  const hz = (h: string) => (h === "1a" ? "1 an" : h === "6m" ? "6 mois" : h === "1m" ? "chaque mois" : h);
  return (
    <Card title="Laboratoire : les essais" repliable ouvert={false} id="labo">
      {lot.map((e) => (
        <div class="ligne-labo">
          <div class="tete"><b>{NOMS_LABO[e.nom] ?? e.nom}</b>
            {e.verdict === "probant" ? <span class="badge good">probant</span> : <small class="muted">{hz(e.horizon)}</small>}</div>
          <div class="chiffres">
            {e.nom.startsWith("backtest")
              ? <span>Risque réel <b class={signClass(-(e.ic ?? 0))}>{e.ic != null && e.ic > 0 ? "+" : ""}{pct(e.ic, 1, false)}</b> vs méthode actuelle</span>
              : <span>IC <b class={signClass(e.ic)}>{corr(e.ic)}</b>{e.ic_base != null && <> (réf. {corr(e.ic_base)})</>}</span>}
            {e.regimes?.hausse && <span>marché en hausse {corr(e.regimes.hausse.ic)} · en baisse {corr(e.regimes?.baisse?.ic)}</span>}
            {e.verdict === "probant" && <span>{hz(e.horizon)}</span>}
          </div>
          <BarreSeuil t={e.t_stat} seuil={e.seuil_t_global} />
        </div>
      ))}
      <p class="hint">Variantes testées à part : les scores publiés ne changent pas. La barre montre le résultat par rapport au seuil exigé
        (trait vertical) ; ce seuil monte avec le nombre d'essais ({n} pour le rendement), sinon le hasard finit par faire gagner une variante.
        « Alpha » = ce qui reste une fois l'effet du marché retiré. « IA de risque » doit battre la référence, la volatilité des 3 derniers mois.</p>
    </Card>
  );
}
