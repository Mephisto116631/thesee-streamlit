import { useCallback, useMemo, useState } from "preact/hooks";
import { api, getFavoris } from "../api";
import { Card, ChartBox, cssVar, HelpButton, Loading, RangeBar, Stat, useData } from "../components";
import { num, pct, signClass } from "../format";
import { monteCarlo, portfolioStats, returnsMatrix, RF, weights } from "../portfolio";

const KEY = "thesee:portefeuille";
const load = () => {
  try { const s = JSON.parse(localStorage.getItem(KEY) ?? "null"); if (s?.syms?.length) return s; } catch { /* ignore */ }
  const f = getFavoris();
  return { syms: f.length >= 2 ? f.slice(0, 8) : ["AAPL", "MSFT", "NVDA"], capital: 10000, mode: "equal" };
};

export function Portfolio() {
  const init = load();
  const [syms, setSyms] = useState<string[]>(init.syms);
  const [capital, setCapital] = useState<number>(init.capital);
  const [mode, setMode] = useState<"equal" | "markowitz">(init.mode);
  const [q, setQ] = useState("");
  const save = (s: string[], c: number, m: string) => { try { localStorage.setItem(KEY, JSON.stringify({ syms: s, capital: c, mode: m })); } catch { /* ignore */ } };

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
  const add = (s: string) => { const n = [...syms, s].slice(0, 15); setSyms(n); setQ(""); save(n, capital, mode); };
  const remove = (s: string) => { const n = syms.filter((x) => x !== s); setSyms(n); save(n, capital, mode); };

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
    <div class="screen">
      <header class="screen-head">
        <div><h1>Portefeuille</h1><p class="sub">Simulation sur 1 an d'historique</p></div>
        <HelpButton keys={["sharpe", "max_drawdown", "volatility"]} intro={<>
          <p><b>Équipondéré</b> : même montant sur chaque titre. <b>Markowitz</b> : poids qui maximisent le rendement par unité de risque (portefeuille « tangent », taux sans risque {pct(RF, 2, false)}), sans vente à découvert.</p>
          <p><b>Monte-Carlo</b> : 1 000 trajectoires d'un an tirées au hasard parmi les rendements quotidiens passés du portefeuille. La zone colorée contient 90 % des scénarios.</p>
          <p>⚠️ Basé sur 1 an de données passées : Markowitz a tendance à sur-pondérer les titres qui ont le plus monté récemment.</p>
        </>} />
      </header>

      <Card title="Composition">
        <div class="chips wrap">
          {syms.map((s) => <button class="chip on" onClick={() => remove(s)} aria-label={`Retirer ${s}`}>{s} ✕</button>)}
        </div>
        <input type="search" placeholder="Ajouter un titre…" value={q} onInput={(e) => setQ((e.target as HTMLInputElement).value)} aria-label="Ajouter un titre" />
        {suggestions.length > 0 && <ul class="suggest">{suggestions.map((s) => <li><button onClick={() => add(s.symbol)}><b>{s.symbol}</b> <span class="muted">{s.nom}</span></button></li>)}</ul>}
        <div class="filter-row">
          <label class="field">Capital (€)
            <input type="number" inputMode="numeric" min={100} step={100} value={capital}
              onChange={(e) => { const c = Math.max(100, Number((e.target as HTMLInputElement).value) || 100); setCapital(c); save(syms, c, mode); }} />
          </label>
          <div class="seg" role="group" aria-label="Méthode">
            <button class={mode === "equal" ? "on" : ""} onClick={() => { setMode("equal"); save(syms, capital, "equal"); }}>Équipondéré</button>
            <button class={mode === "markowitz" ? "on" : ""} onClick={() => { setMode("markowitz"); save(syms, capital, "markowitz"); }}>Markowitz</button>
          </div>
        </div>
      </Card>

      {prices.loading && !calc ? <Loading label="Chargement des cours…" /> : !calc ? (
        <div class="note">Ajoute au moins un titre avec un historique suffisant.</div>
      ) : (
        <>
          <Card title="Répartition">
            <table class="table">
              <thead><tr><th>Titre</th><th>Poids</th><th>Montant</th></tr></thead>
              <tbody>{calc.ok.map((s, i) => ({ s, w: calc.w[i] })).sort((a, b) => b.w - a.w).map(({ s, w }) => (
                <tr><td><b>{s}</b></td><td><div class="wbar"><div style={{ width: `${w * 100}%` }} /></div>{pct(w, 1, false)}</td><td>{num(w * capital, 0)} €</td></tr>
              ))}</tbody>
            </table>
          </Card>

          <Card title="Risque / rendement (1 an passé)">
            <div class="stats">
              <Stat label="Rendement annualisé" value={pct(calc.st.annReturn)} cls={signClass(calc.st.annReturn)} />
              <Stat label="Volatilité" value={pct(calc.st.annVol, 1, false)} />
            </div>
            <RangeBar k="sharpe" v={calc.st.sharpe} />
            <RangeBar k="max_drawdown" v={calc.st.maxDrawdown} />
            <RangeBar k="volatility" v={calc.st.annVol} />
          </Card>

          <Card title="Simulation Monte-Carlo à 1 an">
            <ChartBox config={mcCfg} height={240} label="Éventail des trajectoires simulées du portefeuille sur un an" />
            <div class="stats">
              <Stat label="Défavorable (5 %)" value={`${num(calc.mc.final5, 0)} €`} cls="down" />
              <Stat label="Médiane" value={`${num(calc.mc.final50, 0)} €`} />
              <Stat label="Favorable (95 %)" value={`${num(calc.mc.final95, 0)} €`} cls="up" />
            </div>
            <p class="verdict">Probabilité de finir l'année <b>en perte</b> : <b class={calc.mc.probPerte > 0.3 ? "down" : ""}>{pct(calc.mc.probPerte, 0, false)}</b></p>
          </Card>
        </>
      )}
    </div>
  );
}
