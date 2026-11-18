import { useCallback, useState } from "preact/hooks";
import { api, type ModelRun } from "../api";
import { Card, ChartBox, cssVar, Details, HelpButton, Loading, OfflineNote, RangeBar, Stat, toneOf, useData, ZoneBadge, RefreshButton } from "../components";
import { dateFr, ilYA, num, pct, signClass } from "../format";
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
        <Card title="Spreads aujourd'hui vs 10 ans">
          <div class="stats">
            <Stat label="High Yield" value={`${Math.round(o.hy_spread_bp ?? 0)} pb`} sub={`fourchette ${Math.round(o.hy_min_10y ?? 0)}–${Math.round(o.hy_max_10y ?? 0)}`} />
            <Stat label="Investment Grade" value={`${Math.round(o.ig_spread_bp ?? 0)} pb`} sub={`fourchette ${Math.round(o.ig_min_10y ?? 0)}–${Math.round(o.ig_max_10y ?? 0)}`} />
          </div>
          <RangeBar k="spread_pct" v={o.hy_pct_10y} median={50} medianLabel="médiane 10 ans" />
        </Card>
      )}
      <Card title="Historique 3 ans (source FRED)">
        {sp.loading && !sp.data?.length ? <Loading /> : sp.data?.length ? <ChartBox config={cfg} height={230} label="Spreads de crédit High Yield et Investment Grade sur 3 ans" /> : <p class="hint">Pas de données FRED (clé FRED_API_KEY absente du cron ?).</p>}
      </Card>
      <Card title="Santé financière des titres suivis">
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
      <Card title="Verdict" class={`edge-${v.ton}`} right={<small class="muted">entraîné {ilYA(m.trained_at)}</small>}>
        <p class="verdict"><span class={`badge ${v.ton}`}>{v.nom}</span> {v.txt}</p>
        {d.source === "momentum" ? (
          <div class="note">Classement utilisé : <b>momentum 12-1 mois</b> (les titres qui ont le plus monté sur un an, hors dernier mois).
            Le modèle IA a fait moins bien que cette règle simple en test : l'appli s'en passe.</div>
        ) : d.source === "modele" ? <div class="note">Classement utilisé : <b>modèle IA</b> (meilleur que le momentum seul en test).</div> : null}
        <div class="stats">
          <Stat label="IC modèle IA" value={num(d.ic_moyen, 3)} sub="0 = hasard · > 0,03 = utile" tone={d.source === "modele" ? v.ton : "neutral"} />
          <Stat label="IC momentum" value={num(d.ic_momentum, 3)} sub={`t = ${num(d.t_momentum, 1)}`} tone={d.source === "momentum" ? v.ton : "neutral"} />
          <Stat label="Fiabilité IA (t)" value={num(d.t_stat, 1)} sub="> 2 = net" tone={(d.t_stat ?? 0) > 2 ? "good" : "neutral"} />
        </div>
        <p class="hint">L'<b>IC</b> (coefficient d'information) mesure, date par date, si les titres classés en tête ont réellement fait mieux
          que les autres sur les {d.horizon_jours} jours de bourse suivants (corrélation de rang, de −1 à +1). En gestion, un IC de 0,05 stable est déjà bon.</p>
      </Card>

      {q.length === 5 && (
        <Card title="Performance relative par quintile (modèle IA)">
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

      <Card title="Ce qui compte pour le modèle">
        <ul class="imp">{imp.map((x) => (
          <li><span>{x.label}</span><div class="wbar"><div style={{ width: `${(x.importance / maxImp) * 100}%` }} /></div><b class="imp-val">{pct(x.importance / totImp, 0, false)}</b></li>
        ))}</ul>
      </Card>

      <Card>
        <Details summary="Détails de l'évaluation">
          <table class="table small">
            <thead><tr><th>Période de test</th><th>IC</th><th>Dates</th></tr></thead>
            <tbody>{(d.fenetres ?? []).map((f: any) => <tr><td>{dateFr(f.debut)} → {dateFr(f.fin)}</td><td class={signClass(f.ic)}>{num(f.ic, 3)}</td><td>{f.n_dates}</td></tr>)}</tbody>
          </table>
          <p class="hint">Validation « walk-forward » : le modèle est entraîné sur le passé puis testé sur la période suivante,
            avec un écart de {d.horizon_jours} jours de bourse entre les deux pour qu'il ne voie jamais le futur. {d.n_dates_test} dates testées,
            soit environ {num(d.n_effectif, 0)} observations indépendantes (les périodes de {d.horizon_jours} jours de bourse se chevauchent).</p>
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
