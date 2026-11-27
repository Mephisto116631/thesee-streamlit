import { useCallback, useMemo, useRef, useState } from "preact/hooks";
import { api } from "../api";
import { ChartBox, cssVar, Loading, Stat, useData } from "../components";
import { num, pct } from "../format";
import { monteCarlo, portfolioStats, probaAuDessus, returnsMatrix } from "../portfolio";

type Point = { jour: number; valeur: number; proba: number };

/** « dans 7 mois », « dans 2,5 ans » : jour de bourse d (0 = demain) */
export function echeance(d: number): string {
  const mois = (d + 1) / 21;
  return mois < 24 ? `dans ${Math.max(1, Math.round(mois))} mois` : `dans ${num(mois / 12, 1)} ans`;
}

/**
 * Simulation Monte-Carlo d'un portefeuille donné : 1 000 trajectoires sur l'horizon,
 * en tirant au hasard parmi ses rendements quotidiens réels de l'année passée.
 * Complète la projection « log-normale » : elle reprend les vraies queues de
 * distribution (krachs, journées extrêmes) au lieu d'une loi théorique.
 */
export function MonteCarlo({ lignes, capital, annees, volCible, source, rendement }: {
  lignes: { symbol: string; poids: number }[]; capital: number; annees: number;
  volCible?: number; source?: string;   // volatilité du portefeuille choisie (historique ou IA)
  rendement?: number;                    // rentabilité de long terme (hypothèse), comme la projection ; pas celle de l'an passé
}) {
  const syms = lignes.map((l) => l.symbol);
  const prices = useData(() => api.prices(syms), [syms.join(",")]);
  const jours = Math.max(21, Math.min(1260, Math.round(annees * 252)));

  const calc = useMemo(() => {
    if (!prices.data?.length) return null;
    const { syms: ok, R } = returnsMatrix(prices.data, syms);
    if (R.length < 60) return null;
    const poids = new Map(lignes.map((l) => [l.symbol, l.poids]));
    const brut = ok.map((s) => poids.get(s) ?? 0);
    const tot = brut.reduce((a, b) => a + b, 0) || 1;
    const st = portfolioStats(R, brut.map((w) => w / tot));
    // Mise à l'échelle : les journées tirées gardent leur forme (krachs, queues épaisses) mais
    // leur amplitude correspond à la volatilité retenue pour le portefeuille.
    const moy = st.returns.reduce((a, b) => a + b, 0) / st.returns.length;
    const et = Math.sqrt(st.returns.reduce((a, b) => a + (b - moy) ** 2, 0) / st.returns.length);
    const k = volCible && et > 0 ? volCible / Math.sqrt(252) / et : 1;
    // Tendance : la même hypothèse de rentabilité de long terme que la projection, et non la moyenne de l'an passé
    // (une bonne année passée ne prévoit pas la suivante : aucun modèle testé ne prévoit les rendements).
    const tendance = rendement != null ? (1 + rendement) ** (1 / 252) - 1 : moy;
    const jours_ = st.returns.map((r) => tendance + (r - moy) * k);
    return { mc: monteCarlo(jours_, capital, jours, 1000), nJours: R.length, k };
  }, [prices.data, capital, jours, syms.join(","), volCible, rendement]);

  // Point choisi au doigt : la ligne pointillée et la probabilité de dépasser cette valeur à cette date
  const [sel, setSel] = useState<Point | null>(null);
  const selRef = useRef<Point | null>(null);

  const cfg = useCallback(() => {
    const mc = calc!.mc;
    const viseur = {
      id: "viseur",
      afterDraw(chart: any) {
        const p = selRef.current;
        if (!p) return;
        const { ctx, chartArea: a, scales } = chart;
        const x = scales.x.getPixelForValue(p.jour), y = scales.y.getPixelForValue(p.valeur);
        ctx.save();
        ctx.strokeStyle = cssVar("--muted"); ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(x, a.top); ctx.lineTo(x, a.bottom); ctx.moveTo(a.left, y); ctx.lineTo(a.right, y); ctx.stroke();
        ctx.setLineDash([]); ctx.fillStyle = cssVar("--accent");
        ctx.beginPath(); ctx.arc(x, y, 4, 0, 2 * Math.PI); ctx.fill();
        ctx.restore();
      },
    };
    // Doigt posé ou qui glisse (et souris) : écouteurs « pointer » directs, plus fiables qu'onHover pour un simple toucher
    const choisir = (chart: any, ev: PointerEvent) => {
      const r = chart.canvas.getBoundingClientRect(), a = chart.chartArea;
      // Un doigt un peu à côté de la zone tracée vise le bord le plus proche
      const x = Math.max(a.left, Math.min(a.right, ev.clientX - r.left));
      const y = Math.max(a.top, Math.min(a.bottom, ev.clientY - r.top));
      const jour = Math.max(0, Math.min(mc.grille.length - 1, Math.round(chart.scales.x.getValueForPixel(x))));
      const valeur = chart.scales.y.getValueForPixel(y);
      const p = { jour, valeur, proba: probaAuDessus(mc.grille, jour, valeur) };
      selRef.current = p;
      setSel(p);
      chart.draw();
    };
    const toucher = {
      id: "toucher",
      afterInit(chart: any) {
        const f = (ev: PointerEvent) => choisir(chart, ev);
        chart.canvas.addEventListener("pointerdown", f);
        chart.canvas.addEventListener("pointermove", f);
        chart.$toucher = f;
      },
      beforeDestroy(chart: any) {
        chart.canvas.removeEventListener("pointerdown", chart.$toucher);
        chart.canvas.removeEventListener("pointermove", chart.$toucher);
      },
    };
    const pas = jours > 300 ? 252 : 21;
    const labels = mc.p50.map((_, i) => (i % pas === 0 ? (pas === 252 ? `A${i / 252}` : `M${i / 21}`) : ""));
    return {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "Défavorable (5 %)", data: mc.p5, borderColor: cssVar("--down"), borderWidth: 1, pointRadius: 0 },
          { label: "Favorable (95 %)", data: mc.p95, borderColor: cssVar("--up"), borderWidth: 1, pointRadius: 0, backgroundColor: cssVar("--band"), fill: "-1" },
          { label: "Médiane", data: mc.p50, borderColor: cssVar("--accent"), borderWidth: 2, pointRadius: 0 },
        ],
      },
      options: {
        plugins: { legend: { position: "bottom", labels: { color: cssVar("--muted"), boxWidth: 12 } }, tooltip: { enabled: false } },
      },
      plugins: [viseur, toucher],
    };
  }, [calc]);

  if (prices.loading && !calc) return <Loading label="Chargement des cours…" />;
  if (!calc) return <p class="hint">Historique insuffisant pour simuler ce portefeuille.</p>;
  const { mc } = calc;
  return (
    <>
      <ChartBox config={cfg} height={230} interactif label="Éventail des trajectoires simulées du portefeuille ; toucher un point affiche la probabilité de dépasser cette valeur à cette date" />
      {sel ? (
        <p class="verdict">
          {echeance(sel.jour).replace(/^d/, "D")}, plus de <b>{num(sel.valeur, 0)} €</b> ({pct(sel.valeur / capital - 1, 0)} par rapport à la mise) :{" "}
          <b class={sel.proba < 0.5 ? "down" : "up"}>{probaTexte(sel.proba)}</b> des trajectoires, moins : {probaTexte(1 - sel.proba)}
        </p>
      ) : (
        <p class="hint">Passe le doigt sur le graphique : à chaque date et chaque montant, la probabilité d'avoir plus.</p>
      )}
      <div class="stats">
        <Stat label="Défavorable (5 %)" value={`${num(mc.final5, 0)} €`} tone={mc.final5 < capital ? "bad" : "good"} />
        <Stat label="Médiane" value={`${num(mc.final50, 0)} €`} tone={mc.final50 >= capital ? "good" : "bad"} />
        <Stat label="Favorable (95 %)" value={`${num(mc.final95, 0)} €`} tone="good" />
      </div>
      <p class="verdict">Probabilité de finir en perte : <b class={mc.probPerte > 0.3 ? "down" : ""}>{pct(mc.probPerte, 0, false)}</b></p>
      <p class="hint">1 000 trajectoires de {jours} jours de bourse, tirées au hasard parmi les {calc.nJours} rendements quotidiens réels
        de l'année passée{volCible ? <>, ramenés à la volatilité du portefeuille ({pct(volCible, 0, false)}, {source ?? "historique"})</> : null}
        {rendement != null && <>, autour de la rentabilité de long terme ({pct(rendement, 1, false)}/an, hypothèse)</>}.
        On garde la <b>forme</b> des journées réelles (krachs, séries de baisses), pas leur tendance : il ne prédit pas le marché, il montre l'éventail des résultats possibles.
        Les probabilités affichées dépendent de cette hypothèse de rentabilité ; leur <b>dispersion</b> vient du risque, qui, lui, se prévoit.</p>
    </>
  );
}

/** « 64 % » ; en dehors des centiles simulés : « < 1 % », « > 99 % » */
export function probaTexte(p: number): string {
  if (!Number.isFinite(p)) return "—";
  if (p < 0.01) return "< 1 %";
  if (p > 0.99) return "> 99 %";
  return pct(p, 0, false);
}
