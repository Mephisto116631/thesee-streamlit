import { useCallback, useEffect, useState } from "preact/hooks";
import { api, getFavoris, lirePositions, type Position, type SectorMedian, type Snapshot, toggleFavori, utilisateurCourant } from "../api";
import { Card, ChartBox, cssVar, HelpButton, Loading, RangeBar, Stat, useData, Verifier } from "../components";
import { dateFr, num, pct, prix, signClass } from "../format";
import { BadgeTeste, usePortefeuilleCible } from "./Portfolio";
import { libelleSource, useFiabiliteVol } from "../fiabilite";
import { coursVC, enPerte, per } from "../valorisation";

const FONDA = ["roe", "margin", "ev_ebitda", "debt_eq"] as const;

export function Stock({ symbol, go }: { symbol: string; go: (h: string) => void }) {
  const snap = useData(api.snapshot);
  const med = useData(api.medians);
  const prices = useData(() => api.prices([symbol]), [symbol]);
  const [fav, setFav] = useState(getFavoris().includes(symbol));
  const fiab = useFiabiliteVol();

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
  // Prévision de l'IA montrée seulement si son dernier test est probant
  const volIA = fiab.probant ? s.vol_ia ?? null : null;

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
          {volIA != null && <Stat label={<>Risque prévu ({libelleSource(fiab.source)}) <BadgeTeste /></>} value={pct(volIA, 0, false)} sub="6 prochains mois"
            tone={s.volatility == null ? "" : volIA < s.volatility ? "good" : "bad"} />}
        </div>
        <p class="hint">La volatilité dit de combien le cours s'écarte en général sur un an.
          {fiab.probant ? " L'IA de risque prévoit mieux le risque à venir que la simple volatilité passée (testée sur 2013-2026, re-testée chaque mois)."
            : fiab.connu ? " La prévision de l'IA n'est pas affichée : son dernier test n'est pas probant." : ""}</p>
        <Verifier href="#/risque/ia" label="Voir comment l'IA de risque est testée" />
      </Card>

      <Card title="Indicateurs techniques" repliable ouvert={false}>
        <RangeBar k="chg_20d" v={s.chg_20d} median={m?.chg_20d} />
        <RangeBar k="rsi_14" v={s.rsi_14} median={m?.rsi_14} />
        <RangeBar k="pct_vs_ma50" v={s.pct_vs_ma50} />
        <RangeBar k="volatility" v={s.volatility} median={m?.volatility} />
      </Card>

      {!s.is_etf && (
        <Card title="Est-il cher, rentable, solide ?" repliable id="valorisation">
          {s.comptes_date ? <Valorisation s={s} m={m} /> : aFonda ? (
            <>
              {FONDA.map((k) => <RangeBar k={k} v={s[k]} median={m?.[k]} />)}
              <p class="hint">Source : Alpha Vantage (comptes officiels SEC non disponibles pour ce titre).</p>
            </>
          ) : (
            <p class="hint">Non disponible : pas de comptes officiels SEC pour ce titre (entreprise étrangère, ou comptes non encore publiés).</p>
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

type Sens = "prix" | "haut" | "bas";
/** Une ligne : valeur du titre, médiane du secteur, et un mot de comparaison. */
function LigneValo({ nom, aide, v, med, fmt, sens }: {
  nom: string; aide: string; v: number | null | undefined; med: number | null | undefined; fmt: (x: number) => string; sens: Sens;
}) {
  let mot = "", ton = "";
  if (v != null && med != null && Math.abs(med) > 1e-9) {
    const r = v / med;
    const plus = r > 1.2, moins = r < 0.8;
    if (sens === "prix") { mot = plus ? "plus cher" : moins ? "moins cher" : "comme le secteur"; }
    else if (sens === "haut") { mot = plus ? "mieux" : moins ? "moins bien" : "comme le secteur"; ton = plus ? "up" : moins ? "down" : ""; }
    else { mot = plus ? "plus élevé" : moins ? "plus faible" : "comme le secteur"; ton = plus ? "down" : moins ? "up" : ""; }
  }
  return (
    <tr>
      <td><b>{nom}</b><br /><small class="muted">{aide}</small></td>
      <td class="nowrap"><b>{v == null ? "n.d." : fmt(v)}</b></td>
      <td class="nowrap">{med == null ? "n.d." : fmt(med)}</td>
      <td class={ton}>{mot}</td>
    </tr>
  );
}

/** Valorisation d'après les comptes officiels déposés à la SEC : des faits, pas une prévision. */
function Valorisation({ s, m }: { s: Snapshot; m: SectorMedian | undefined }) {
  const x = (d: number) => `${num(d, 1)}`;
  const p = (d: number) => pct(d, 0, false);
  return (
    <>
      <table class="table small valo">
        <thead><tr><th></th><th>Ce titre</th><th>Secteur<br /><small>médiane</small></th><th></th></tr></thead>
        <tbody>
          {enPerte(s) ? (
            <tr><td><b>PER</b><br /><small class="muted">cours / bénéfice par action</small></td><td colSpan={3}>en perte sur le dernier exercice</td></tr>
          ) : <LigneValo nom="PER" aide="cours / bénéfice par action (années de bénéfice payées)" v={per(s)} med={m?.per} fmt={x} sens="prix" />}
          <LigneValo nom="Cours / valeur comptable" aide="prix payé pour 1 $ de fonds propres" v={coursVC(s)} med={m?.cours_vc} fmt={x} sens="prix" />
          <LigneValo nom="ROE" aide="Return on Equity : bénéfice / fonds propres" v={s.roe_sec} med={m?.roe_sec} fmt={p} sens="haut" />
          <LigneValo nom="Rentabilité brute" aide="marge brute / actifs" v={s.rentabilite_brute} med={m?.rentabilite_brute} fmt={p} sens="haut" />
          <LigneValo nom="Endettement" aide="part des actifs financée par la dette" v={s.endettement} med={m?.endettement} fmt={p} sens="bas" />
          <LigneValo nom="Bénéfice encaissé" aide="trésorerie d'exploitation / bénéfice" v={s.part_encaissee} med={m?.part_encaissee} fmt={p} sens="haut" />
        </tbody>
      </table>
      <p class="hint">Comptes officiels annuels déposés à la SEC (Securities and Exchange Commission), publiés le <b>{dateFr(s.comptes_date!)}</b> ;
        PER et cours / valeur comptable au cours du jour. « n.d. » : non disponible.</p>
      <div class="note">Pour <b>comprendre</b> le titre, pas pour choisir : au laboratoire, ces ratios n'ont pas prédit la performance
        sur 2012-2026 (les titres « pas chers » ont même fait un peu moins bien).</div>
    </>
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
