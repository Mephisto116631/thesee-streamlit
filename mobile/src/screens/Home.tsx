import { api } from "../api";
import { Card, HelpButton, Loading, OfflineNote, RangeBar, Stat, toneOf, useData, ZoneBadge, RefreshButton } from "../components";
import { dateFr, ilYA, num, pct, prix, signClass } from "../format";

const VERDICT_TXT: Record<string, string> = {
  aucun: "ne fait pas mieux qu'une règle naïve : ses signaux sont à ignorer pour l'instant.",
  bruit: "fait à peine mieux qu'une règle naïve : avantage non significatif.",
  signal: "bat la règle naïve de plus de 2 points sur la période de test.",
};

export function Home({ go }: { go: (h: string) => void }) {
  const ov = useData(api.overview);
  const sync = useData(api.lastSync);
  const snap = useData(api.snapshot);
  const models = useData(api.models);

  const o = ov.data;
  const actions = (snap.data ?? []).filter((s) => !s.is_etf && s.chg_1d !== null);
  const top = [...actions].sort((a, b) => (b.chg_1d ?? 0) - (a.chg_1d ?? 0));
  const gagnants = top.slice(0, 5), perdants = top.slice(-5).reverse();
  const mActions = models.data?.find((m) => m.kind === "actions");
  const s = sync.data;

  return (
    <div class="screen">
      <header class="screen-head">
        <div>
          <h1>Thésée</h1>
          <p class="sub">
            {s ? <>Données {s.status === "error" ? "⚠️ dernière synchro en erreur" : "à jour"} · {ilYA(s.finished_at ?? s.started_at)}</> : "—"}
            {o?.date && <> · séance du {dateFr(o.date)}</>}
          </p>
        </div>
        <RefreshButton />
        <HelpButton keys={["vix", "spread_pct", "pct_vs_ma50", "gain_pts"]}
          intro={<p>L'accueil résume l'<b>humeur du marché</b> : volatilité attendue (VIX), coût du crédit (spreads), proportion de titres en tendance haussière, et fiabilité du modèle IA.</p>} />
      </header>
      <OfflineNote res={ov.res} />

      {ov.loading && !o ? <Loading /> : !o ? <div class="note">Aucune donnée publiée : lance le workflow « Sync Thésée » sur GitHub.</div> : (
        <>
          <Card title="Régime de marché">
            <RangeBar k="vix" v={o.vix} />
            <div class="stats">
              <Stat label="Titres > MM50" value={`${Math.round(o.pct_above_ma50 ?? 0)} %`} sub="tendance court terme" tone={breadth(o.pct_above_ma50)} />
              <Stat label="Titres > MM200" value={`${Math.round(o.pct_above_ma200 ?? 0)} %`} sub="tendance long terme" tone={breadth(o.pct_above_ma200)} />
              <Stat label="Hausse / baisse" value={<><span class="up">{o.n_hausse_1d}</span> / <span class="down">{o.n_baisse_1d}</span></>} sub="sur la séance" />
            </div>
            <p class="hint">Repère : plus de 60 % des titres au-dessus de leur MM200 = marché large en tendance haussière ; moins de 40 % = marché fragile.</p>
          </Card>

          <Card title="Crédit (spreads)" right={<button class="link" onClick={() => go("#/risque")}>Détails ›</button>}>
            <div class="stats">
              <Stat label="High Yield" value={`${Math.round(o.hy_spread_bp ?? 0)} pb`} tone={toneOf("spread_pct", o.hy_pct_10y)}
                sub={<><ZoneBadge k="spread_pct" v={o.hy_pct_10y} /> {Math.round(o.hy_pct_10y ?? 0)}e percentile 10 ans</>} />
              <Stat label="Investment Grade" value={`${Math.round(o.ig_spread_bp ?? 0)} pb`} tone={toneOf("spread_pct", o.ig_pct_10y)}
                sub={<><ZoneBadge k="spread_pct" v={o.ig_pct_10y} /> {Math.round(o.ig_pct_10y ?? 0)}e percentile</>} />
            </div>
            <p class="hint">Fourchette 10 ans HY : {Math.round(o.hy_min_10y ?? 0)} – {Math.round(o.hy_max_10y ?? 0)} pb (médiane {Math.round(o.hy_med_10y ?? 0)}).</p>
          </Card>
        </>
      )}

      {mActions && (
        <Card class={`edge-${mActions.verdict === "signal" ? "good" : mActions.verdict === "bruit" ? "neutral" : "bad"}`} title="Modèle IA" right={<button class="link" onClick={() => go("#/risque/ia")}>Détails ›</button>}>
          <p class="verdict">
            <ZoneBadge k="gain_pts" v={mActions.gain_pts} /> Le modèle ({num(mActions.accuracy, 1)} % de bonnes directions vs {num(mActions.baseline, 1)} % pour la règle naïve) {VERDICT_TXT[mActions.verdict]}
          </p>
        </Card>
      )}

      {actions.length > 0 && (
        <Card title="Plus fortes variations du jour">
          <div class="movers">
            <div>{gagnants.map((x) => <Mover s={x} go={go} />)}</div>
            <div>{perdants.map((x) => <Mover s={x} go={go} />)}</div>
          </div>
        </Card>
      )}
      <p class="foot">Lecture seule · aucune donnée n'est envoyée depuis ce téléphone · Les performances passées ne préjugent pas des performances futures.</p>
    </div>
  );
}

// Repère de largeur de marché : > 60 % haussier, < 40 % fragile
const breadth = (v: number | null) => (v == null ? "" : v > 60 ? "good" : v < 40 ? "bad" : "neutral");

function Mover({ s, go }: { s: { symbol: string; close: number; chg_1d: number | null }; go: (h: string) => void }) {
  return (
    <button class={`mover ${(s.chg_1d ?? 0) >= 0 ? "row-up" : "row-down"}`} onClick={() => go(`#/titre/${s.symbol}`)}>
      <b>{s.symbol}</b><span class="muted">{prix(s.close)}</span><span class={signClass(s.chg_1d)}>{pct(s.chg_1d)}</span>
    </button>
  );
}
