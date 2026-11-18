import { useCallback, useMemo } from "preact/hooks";
import { api } from "../api";
import { ChartBox, cssVar, Loading, Stat, useData } from "../components";
import { num, pct } from "../format";
import { monteCarlo, portfolioStats, returnsMatrix } from "../portfolio";

/**
 * Simulation Monte-Carlo d'un portefeuille donné : 1 000 trajectoires sur l'horizon,
 * en tirant au hasard parmi ses rendements quotidiens réels de l'année passée.
 * Complète la projection « log-normale » : elle reprend les vraies queues de
 * distribution (krachs, journées extrêmes) au lieu d'une loi théorique.
 */
export function MonteCarlo({ lignes, capital, annees }: { lignes: { symbol: string; poids: number }[]; capital: number; annees: number }) {
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
    return { mc: monteCarlo(st.returns, capital, jours, 1000), nJours: R.length };
  }, [prices.data, capital, jours, syms.join(",")]);

  const cfg = useCallback(() => {
    const mc = calc!.mc;
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
      options: { plugins: { legend: { position: "bottom" } } },
    };
  }, [calc]);

  if (prices.loading && !calc) return <Loading label="Chargement des cours…" />;
  if (!calc) return <p class="hint">Historique insuffisant pour simuler ce portefeuille.</p>;
  const { mc } = calc;
  return (
    <>
      <ChartBox config={cfg} height={230} label="Éventail des trajectoires simulées du portefeuille" />
      <div class="stats">
        <Stat label="Défavorable (5 %)" value={`${num(mc.final5, 0)} €`} tone={mc.final5 < capital ? "bad" : "good"} />
        <Stat label="Médiane" value={`${num(mc.final50, 0)} €`} tone={mc.final50 >= capital ? "good" : "bad"} />
        <Stat label="Favorable (95 %)" value={`${num(mc.final95, 0)} €`} tone="good" />
      </div>
      <p class="verdict">Probabilité de finir en perte : <b class={mc.probPerte > 0.3 ? "down" : ""}>{pct(mc.probPerte, 0, false)}</b></p>
      <p class="hint">1 000 trajectoires de {jours} jours de bourse, tirées au hasard parmi les {calc.nJours} rendements quotidiens réels
        de l'année passée. Plus réaliste pour les journées extrêmes que la projection théorique, mais suppose que l'année à venir
        ressemble à la dernière.</p>
    </>
  );
}
