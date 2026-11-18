import { useCallback, useState } from "preact/hooks";
import { api, getFavoris, toggleFavori } from "../api";
import { Card, ChartBox, cssVar, HelpButton, Loading, RangeBar, Stat, useData, ZoneBadge } from "../components";
import { dateFr, num, pct, prix, signClass } from "../format";

const FONDA = ["roe", "margin", "ev_ebitda", "debt_eq"] as const;

export function Stock({ symbol, go }: { symbol: string; go: (h: string) => void }) {
  const snap = useData(api.snapshot);
  const med = useData(api.medians);
  const prices = useData(() => api.prices([symbol]), [symbol]);
  const sig = useData(() => api.signal(symbol), [symbol]);
  const models = useData(api.models);
  const [fav, setFav] = useState(getFavoris().includes(symbol));

  const s = snap.data?.find((x) => x.symbol === symbol);
  const m = med.data?.find((x) => x.secteur === s?.secteur);
  const model = models.data?.find((x) => x.kind === (s?.is_etf ? "etf" : "actions"));
  const pts = (prices.data ?? []).filter((p) => p.symbol === symbol);

  const chartCfg = useCallback(() => {
    const closes = pts.map((p) => p.close);
    const ma50 = closes.map((_, i) => i < 49 ? null : closes.slice(i - 49, i + 1).reduce((a, b) => a + b, 0) / 50);
    const n = Math.min(pts.length, 252);
    return {
      type: "line",
      data: {
        labels: pts.slice(-n).map((p) => dateFr(p.date)),
        datasets: [
          { label: "Cours", data: closes.slice(-n), borderColor: cssVar("--accent"), borderWidth: 2, pointRadius: 0, tension: 0.1 },
          { label: "Moyenne 50 j", data: ma50.slice(-n), borderColor: cssVar("--muted"), borderWidth: 1.5, borderDash: [4, 3], pointRadius: 0 },
        ],
      },
    };
  }, [pts.length, symbol]);

  if (snap.loading && !s) return <div class="screen"><Loading /></div>;
  if (!s) return <div class="screen"><button class="back" onClick={() => history.back()}>‹ Retour</button><div class="note">Titre {symbol} introuvable dans les données publiées.</div></div>;

  const pos52 = s.high_52w && s.low_52w && s.high_52w > s.low_52w ? (s.close - s.low_52w) / (s.high_52w - s.low_52w) : null;
  const aFonda = FONDA.some((k) => s[k] !== null && s[k] !== undefined);
  const facteurs = sig.data?.facteurs ?? [];
  const maxImpact = Math.max(1e-9, ...facteurs.map((f) => Math.abs(f.impact)));

  return (
    <div class="screen">
      <header class="screen-head">
        <button class="back" onClick={() => history.back()} aria-label="Retour">‹</button>
        <div class="grow">
          <h1>{s.symbol} <button class="fav" onClick={() => setFav(toggleFavori(symbol).includes(symbol))} aria-label="Favori">{fav ? "★" : "☆"}</button></h1>
          <p class="sub">{s.nom} · {s.secteur}</p>
        </div>
        <HelpButton keys={["rsi_14", "chg_20d", "volatility", "pct_vs_ma50", "roe", "margin", "ev_ebitda", "debt_eq", "z_score", "proba_hausse"]}
          intro={<p>Chaque jauge montre la valeur du titre (trait vertical) dans sa fourchette d'interprétation, et la <b>médiane du secteur</b> (◆) pour comparer aux pairs.</p>} />
      </header>

      <div class="price-head">
        <span class="big">{prix(s.close)}</span>
        <span class={`chg ${signClass(s.chg_1d)}`}>{pct(s.chg_1d)}</span>
        <span class="muted">clôture du {dateFr(s.date)}</span>
      </div>

      <Card title="Cours sur 1 an">
        {pts.length ? <ChartBox config={chartCfg} label={`Cours de ${symbol} sur un an`} /> : <Loading />}
        <div class="stats">
          <Stat label="1 semaine" value={pct(s.chg_5d)} cls={signClass(s.chg_5d)} tone={sgnTone(s.chg_5d)} />
          <Stat label="1 mois" value={pct(s.chg_20d)} cls={signClass(s.chg_20d)} tone={sgnTone(s.chg_20d)} />
          <Stat label="1 an" value={pct(s.chg_1y)} cls={signClass(s.chg_1y)} tone={sgnTone(s.chg_1y)} />
        </div>
        {pos52 !== null && (
          <div class="range52">
            <div class="r52-track"><div class="r52-cursor" style={{ left: `${pos52 * 100}%` }} /></div>
            <div class="r52-legend"><span>Plus bas 1 an<br /><b>{prix(s.low_52w)}</b></span><span>Plus haut 1 an<br /><b>{prix(s.high_52w)}</b></span></div>
          </div>
        )}
      </Card>

      <Card title="Technique">
        <RangeBar k="chg_20d" v={s.chg_20d} median={m?.chg_20d} />
        <RangeBar k="rsi_14" v={s.rsi_14} median={m?.rsi_14} />
        <RangeBar k="pct_vs_ma50" v={s.pct_vs_ma50} />
        <RangeBar k="volatility" v={s.volatility} median={m?.volatility} />
      </Card>

      {!s.is_etf && (
        <Card title="Fondamentaux">
          {aFonda ? FONDA.map((k) => <RangeBar k={k} v={s[k]} median={m?.[k]} />) : (
            <p class="hint">Fondamentaux non suivis pour ce titre : l'API gratuite Alpha Vantage limite le suivi à une liste de titres « core » (modifiable dans <code>utils.py</code>).</p>
          )}
        </Card>
      )}

      {!s.is_etf && (s.z_score !== null || s.rating_sp) && (
        <Card title="Crédit & bilan">
          {s.z_score !== null && <RangeBar k="z_score" v={s.z_score} />}
          {s.rating_sp && <p>Note S&P : <b>{s.rating_sp}</b> {isIG(s.rating_sp) ? <span class="badge good">Investment Grade</span> : <span class="badge bad">High Yield</span>}</p>}
        </Card>
      )}

      <Card title="Signal IA (jour suivant)">
        {model && model.verdict !== "signal" && (
          <div class="note warn">Fiabilité du modèle : <ZoneBadge k="gain_pts" v={model.gain_pts} /> — à lire comme une indication, pas comme une recommandation.</div>
        )}
        <RangeBar k="proba_hausse" v={sig.data?.proba_hausse ?? s.proba_hausse} />
        {facteurs.length > 0 && (
          <>
            <h3 class="h3">Ce qui influence le signal</h3>
            <ul class="factors">
              {facteurs.map((f) => (
                <li>
                  <div class="f-label">{f.label} <small class="muted">({num(f.valeur, 3)})</small></div>
                  <div class="f-bar"><div class={`f-fill ${f.impact >= 0 ? "pos" : "neg"}`}
                    style={{ width: `${(Math.abs(f.impact) / maxImpact) * 50}%`, [f.impact >= 0 ? "left" : "right"]: "50%" }} /></div>
                  <div class={`f-txt ${f.impact >= 0 ? "up" : "down"}`}>{f.impact >= 0 ? "pousse à la hausse" : "pousse à la baisse"}</div>
                </li>
              ))}
            </ul>
            <p class="hint">Contributions SHAP : de combien chaque facteur déplace la prédiction par rapport à la moyenne.</p>
          </>
        )}
        <button class="link" onClick={() => go("#/risque/ia")}>Comment le modèle est évalué ›</button>
      </Card>
    </div>
  );
}

const sgnTone = (v: number | null | undefined) => (v == null ? "" : v > 0 ? "good" : v < 0 ? "bad" : "");

export function isIG(r: string) {
  return ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-"].includes(r);
}
