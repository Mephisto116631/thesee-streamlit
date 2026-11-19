import { useCallback, useEffect, useState } from "preact/hooks";
import { api, getFavoris, lirePositions, type Position, toggleFavori, utilisateurCourant } from "../api";
import { Card, ChartBox, cssVar, HelpButton, Loading, RangeBar, Stat, useData, Verifier } from "../components";
import { dateFr, num, pct, prix, signClass } from "../format";
import { usePortefeuilleCible } from "./Portfolio";

const FONDA = ["roe", "margin", "ev_ebitda", "debt_eq"] as const;

export function Stock({ symbol, go }: { symbol: string; go: (h: string) => void }) {
  const snap = useData(api.snapshot);
  const med = useData(api.medians);
  const prices = useData(() => api.prices([symbol]), [symbol]);
  const [fav, setFav] = useState(getFavoris().includes(symbol));

  const s = snap.data?.find((x) => x.symbol === symbol);
  const m = med.data?.find((x) => x.secteur === s?.secteur);
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

  return (
    <div class="screen">
      <header class="screen-head">
        <button class="back" onClick={() => history.back()} aria-label="Retour">‹</button>
        <div class="grow">
          <h1>{s.symbol} <button class="fav" onClick={() => setFav(toggleFavori(symbol).includes(symbol))} aria-label="Favori">{fav ? "★" : "☆"}</button></h1>
          <p class="sub">{s.nom} · {s.secteur}</p>
        </div>
        <HelpButton keys={["rsi_14", "chg_20d", "volatility", "pct_vs_ma50", "roe", "margin", "ev_ebitda", "debt_eq", "z_score"]}
          intro={<p>Chaque jauge montre la valeur du titre (trait vertical) dans sa fourchette d'interprétation, et la <b>médiane du secteur</b> (◆) pour comparer aux pairs.</p>} />
      </header>

      <div class="price-head">
        <span class="big">{prix(s.close)}</span>
        <span class={`chg ${signClass(s.chg_1d)}`}>{pct(s.chg_1d)}</span>
        <span class="muted">clôture du {dateFr(s.date)}</span>
      </div>

      <DansMonPortefeuille symbol={symbol} />

      <Card title="Comment évolue son cours ?">
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

      <Card title="Quel risque ?">
        <div class="stats">
          <Stat label="Risque des 3 dernières années" value={pct(s.volatility, 0, false)} sub="volatilité par an" />
          <Stat label="Risque prévu par l'IA" value={s.vol_ia != null ? pct(s.vol_ia, 0, false) : "—"} sub="6 prochains mois"
            tone={s.vol_ia == null || s.volatility == null ? "" : s.vol_ia < s.volatility ? "good" : "bad"} />
        </div>
        <p class="hint">La volatilité dit de combien le cours s'écarte en général sur un an. L'IA de risque, testée sur 2013-2026,
          prévoit mieux le risque à venir que la simple volatilité passée.</p>
        <Verifier href="#/risque/ia" label="Voir comment l'IA de risque est testée" />
      </Card>

      <Card title="Indicateurs techniques" repliable ouvert={false}>
        <RangeBar k="chg_20d" v={s.chg_20d} median={m?.chg_20d} />
        <RangeBar k="rsi_14" v={s.rsi_14} median={m?.rsi_14} />
        <RangeBar k="pct_vs_ma50" v={s.pct_vs_ma50} />
        <RangeBar k="volatility" v={s.volatility} median={m?.volatility} />
      </Card>

      {!s.is_etf && (
        <Card title="Est-il rentable et cher ?" repliable ouvert={false}>
          {aFonda ? FONDA.map((k) => <RangeBar k={k} v={s[k]} median={m?.[k]} />) : (
            <p class="hint">Pas de données de rentabilité pour ce titre : la source gratuite utilisée n'en fournit que pour une douzaine de titres.</p>
          )}
        </Card>
      )}

      {!s.is_etf && (s.z_score !== null || s.rating_sp) && (
        <Card title="Est-il solide financièrement ?" repliable ouvert={false}>
          {s.z_score !== null && <RangeBar k="z_score" v={s.z_score} />}
          {s.rating_sp && <p>Note S&P : <b>{s.rating_sp}</b> {isIG(s.rating_sp) ? <span class="badge good">Investment Grade</span> : <span class="badge bad">High Yield</span>}</p>}
        </Card>
      )}

    </div>
  );
}

const sgnTone = (v: number | null | undefined) => (v == null ? "" : v > 0 ? "good" : v < 0 ? "bad" : "");

export function isIG(r: string) {
  return ["AAA", "AA+", "AA", "AA-", "A+", "A", "A-", "BBB+", "BBB", "BBB-"].includes(r);
}

/** Ce titre dans mon portefeuille conseillé et dans mes positions : tout au même endroit. */
function DansMonPortefeuille({ symbol }: { symbol: string }) {
  const { e, lignes } = usePortefeuilleCible();
  const [mes, setMes] = useState<Position[] | null>(null);
  useEffect(() => { utilisateurCourant().then((u) => { if (u) lirePositions().then((p) => setMes(p.filter((x) => x.symbol === symbol))).catch(() => {}); }); }, [symbol]);
  const conseil = lignes.find((l) => l.symbol === symbol);
  const qte = (mes ?? []).reduce((a, x) => a + x.quantite, 0);
  if (!conseil && !qte) return null;
  return (
    <Card title="Dans mon portefeuille" class="tint-accent">
      <div class="stats">
        <Stat label="Part conseillée" value={conseil ? pct(conseil.poids, 1, false) : "0 %"} sub={conseil ? `${num(conseil.poids * e.capital, 2)} € sur ${num(e.capital, 0)} €` : "pas retenu"} />
        {qte > 0 && <Stat label="Je possède" value={num(qte, 4)} sub="actions" />}
      </div>
      <Verifier href="#/portefeuille" label="Voir le portefeuille" />
    </Card>
  );
}
