import { useCallback, useMemo, useState } from "preact/hooks";
import { api, getFavoris } from "../api";
import { Card, ChartBox, cssVar, Loading, RangeBar, Stat, toneOf, useData } from "../components";
import { num, pct, signClass } from "../format";
import { PlanAchat } from "./PlanAchat";
import { monteCarlo, portfolioStats, returnsMatrix, weights } from "../portfolio";

type Mode = "markowitz" | "equal";
const KEY = "thesee:mestitres:v1";
const load = (depart: string[]): { syms: string[]; mode: Mode } => {
  try { const s = JSON.parse(localStorage.getItem(KEY) ?? "null"); if (s?.syms?.length) return s; } catch { /* ignore */ }
  const f = getFavoris();
  return { syms: depart.length ? depart : f.length >= 2 ? f.slice(0, 8) : ["AAPL", "MSFT", "NVDA"], mode: "markowitz" };
};

/** Onglet « Mes titres » : je choisis les titres, l'appli calcule les poids. */
export function MesTitres({ capital, depart, eurusd }: { capital: number; depart: string[]; eurusd: number | null }) {
  const init = load(depart);
  const [syms, setSyms] = useState<string[]>(init.syms);
  const [mode, setMode] = useState<Mode>(init.mode);
  const [q, setQ] = useState("");
  const save = (s: string[], m: Mode) => { try { localStorage.setItem(KEY, JSON.stringify({ syms: s, mode: m })); } catch { /* ignore */ } };

  const snap = useData(api.snapshot);
  const prices = useData(() => api.prices(syms), [syms.join(",")]);

  const calc = useMemo(() => {
    if (!prices.data?.length || syms.length < 1) return null;
    const { syms: ok, R } = returnsMatrix(prices.data, syms);
    if (R.length < 30) return null;
    const w = weights(R, mode);
    const st = portfolioStats(R, w);
    const mc = monteCarlo(st.returns, capital);
    return { ok, w, st, mc };
  }, [prices.data, mode, capital, syms.join(",")]);

  const suggestions = q.trim().length >= 1
    ? (snap.data ?? []).filter((s) => !syms.includes(s.symbol) && (s.symbol.includes(q.toUpperCase()) || (s.nom ?? "").toUpperCase().includes(q.toUpperCase()))).slice(0, 6)
    : [];
  const add = (s: string) => { const n = [...syms, s].slice(0, 15); setSyms(n); setQ(""); save(n, mode); };
  const remove = (s: string) => { const n = syms.filter((x) => x !== s); setSyms(n); save(n, mode); };
  const reprendre = () => { if (depart.length) { setSyms(depart); save(depart, mode); } };

  const mcCfg = useCallback(() => {
    const mc = calc!.mc;
    const labels = mc.p50.map((_, i) => (i % 21 === 0 ? `M${i / 21}` : ""));
    const accent = cssVar("--accent"), band = cssVar("--band");
    return {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "Scénario défavorable (5 %)", data: mc.p5, borderColor: cssVar("--down"), borderWidth: 1, pointRadius: 0 },
          { label: "Scénario favorable (95 %)", data: mc.p95, borderColor: cssVar("--up"), borderWidth: 1, pointRadius: 0, backgroundColor: band, fill: "-1" },
          { label: "Médiane", data: mc.p50, borderColor: accent, borderWidth: 2, pointRadius: 0 },
        ],
      },
      options: { plugins: { legend: { position: "bottom" } } },
    };
  }, [calc]);

  return (
    <>
      <Card title="Mes titres">
        <div class="seg full" role="group" aria-label="Méthode">
          <button class={mode === "markowitz" ? "on" : ""} onClick={() => { setMode("markowitz"); save(syms, "markowitz"); }}>Markowitz</button>
          <button class={mode === "equal" ? "on" : ""} onClick={() => { setMode("equal"); save(syms, "equal"); }}>Équipondéré</button>
        </div>
        <div class="chips wrap">
          {syms.map((s) => <button class="chip on" onClick={() => remove(s)} aria-label={`Retirer ${s}`}>{s} ✕</button>)}
        </div>
        <input type="search" placeholder="Ajouter un titre…" value={q} onInput={(e) => setQ((e.target as HTMLInputElement).value)} aria-label="Ajouter un titre" />
        {suggestions.length > 0 && <ul class="suggest">{suggestions.map((s) => <li><button onClick={() => add(s.symbol)}><b>{s.symbol}</b> <span class="muted">{s.nom}</span></button></li>)}</ul>}
        {depart.length > 0 && <button class="link" onClick={reprendre}>↺ Repartir des titres de l'onglet Objectif</button>}
      </Card>

      {prices.loading && !calc ? <Loading label="Chargement des cours…" /> : !calc ? (
        <div class="note">Ajoute au moins un titre avec un historique suffisant.</div>
      ) : (
        <>
          <Card title="Répartition">
            <table class="table">
              <thead><tr><th>Titre</th><th>Poids</th><th>Montant</th></tr></thead>
              <tbody>{calc.ok.map((s, i) => ({ s, w: calc.w[i] })).sort((a, b) => b.w - a.w).map(({ s, w }) => (
                <tr><td><b>{s}</b></td>
                  <td><div class="wbar"><div style={{ width: `${(w / Math.max(...calc.w)) * 100}%` }} /></div>{pct(w, 1, false)}</td><td><b>{num(w * capital, w * capital < 100 ? 2 : 0)} €</b></td></tr>
              ))}</tbody>
            </table>
          </Card>

          <Card title="Risque / rendement (1 an passé)">
            <div class="stats">
              <Stat label="Rendement annualisé" value={pct(calc.st.annReturn)} cls={signClass(calc.st.annReturn)} tone={calc.st.annReturn >= 0 ? "good" : "bad"} />
              <Stat label="Volatilité" value={pct(calc.st.annVol, 1, false)} tone={toneOf("volatility", calc.st.annVol)} />
            </div>
            <RangeBar k="sharpe" v={calc.st.sharpe} />
            <RangeBar k="max_drawdown" v={calc.st.maxDrawdown} />
            <RangeBar k="volatility" v={calc.st.annVol} />
          </Card>

          <PlanAchat capital={capital} lignes={calc.ok.map((s, i) => ({ symbol: s, poids: calc.w[i] }))}
            prix={Object.fromEntries((snap.data ?? []).map((x) => [x.symbol, x.close]))} eurusd={eurusd} annees={1} />

          <Card title="Simulation Monte-Carlo à 1 an">
            <ChartBox config={mcCfg} height={240} label="Éventail des trajectoires simulées du portefeuille sur un an" />
            <div class="stats">
              <Stat label="Défavorable (5 %)" value={`${num(calc.mc.final5, 0)} €`} cls="down" tone="bad" />
              <Stat label="Médiane" value={`${num(calc.mc.final50, 0)} €`} tone={calc.mc.final50 >= capital ? "good" : "bad"} />
              <Stat label="Favorable (95 %)" value={`${num(calc.mc.final95, 0)} €`} cls="up" tone="good" />
            </div>
            <p class="verdict">Probabilité de finir l'année <b>en perte</b> : <b class={calc.mc.probPerte > 0.3 ? "down" : ""}>{pct(calc.mc.probPerte, 0, false)}</b></p>
          </Card>
        </>
      )}
    </>
  );
}
