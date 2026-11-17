import { useCallback, useState } from "preact/hooks";
import { api, type ModelRun } from "../api";
import { Card, ChartBox, cssVar, Details, HelpButton, Loading, OfflineNote, RangeBar, Stat, toneOf, useData, ZoneBadge } from "../components";
import { dateFr, ilYA, num } from "../format";
import { isIG } from "./Stock";

export function Risk({ tab, go }: { tab: "credit" | "ia"; go: (h: string) => void }) {
  return (
    <div class="screen">
      <header class="screen-head">
        <div><h1>Risque & IA</h1></div>
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

function Models() {
  const models = useData(api.models);
  const [kind, setKind] = useState<"actions" | "etf">("actions");
  const m = models.data?.find((x) => x.kind === kind);
  return (
    <>
      <OfflineNote res={models.res} />
      <div class="seg" role="group" aria-label="Modèle">
        <button class={kind === "actions" ? "on" : ""} onClick={() => setKind("actions")}>Actions</button>
        <button class={kind === "etf" ? "on" : ""} onClick={() => setKind("etf")}>ETF</button>
      </div>
      {models.loading && !m ? <Loading /> : !m ? <div class="note">Modèle non publié.</div> : <ModelView m={m} />}
    </>
  );
}

function ModelView({ m }: { m: ModelRun }) {
  const d = m.diagnostics ?? {};
  const imp = m.importance ?? [];
  const maxImp = Math.max(1e-9, ...imp.map((x) => x.importance));
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
          <li><span>{x.label}</span><div class="wbar"><div style={{ width: `${(x.importance / maxImp) * 100}%` }} /></div></li>
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
