import { useCallback, useMemo, useState } from "preact/hooks";
import { api, getFavoris } from "../api";
import { Card, ChartBox, cssVar, Details, HelpButton, Loading, RangeBar, Stat, toneOf, useData } from "../components";
import { ilYA, num, pct, signClass } from "../format";
import { monteCarlo, portfolioStats, returnsMatrix, RF, weights } from "../portfolio";

type Mode = "reco" | "markowitz" | "equal";
const KEY = "thesee:portefeuille:v2"; // v2 : capital 200 € et portefeuille recommandé par défaut
const load = (): { syms: string[]; capital: number; mode: Mode } => {
  try { const s = JSON.parse(localStorage.getItem(KEY) ?? "null"); if (s?.mode) return s; } catch { /* ignore */ }
  const f = getFavoris();
  return { syms: f.length >= 2 ? f.slice(0, 8) : ["AAPL", "MSFT", "NVDA"], capital: 200, mode: "reco" };
};
const MODES: { k: Mode; label: string }[] = [
  { k: "reco", label: "Recommandé" }, { k: "markowitz", label: "Markowitz" }, { k: "equal", label: "Équipondéré" },
];

export function Portfolio() {
  const init = load();
  const [mesTitres, setSyms] = useState<string[]>(init.syms);
  const [capital, setCapital] = useState<number>(init.capital);
  const [mode, setMode] = useState<Mode>(init.mode);
  const reco = useData(api.portefeuilleReco);
  const recoW = new Map((reco.data?.lignes ?? []).map((l) => [l.symbol, l.poids]));
  const syms = mode === "reco" && recoW.size ? [...recoW.keys()] : mesTitres;
  const [q, setQ] = useState("");
  const save = (s: string[], c: number, m: string) => { try { localStorage.setItem(KEY, JSON.stringify({ syms: s, capital: c, mode: m })); } catch { /* ignore */ } };

  const snap = useData(api.snapshot);
  const prices = useData(() => api.prices(syms), [syms.join(",")]);

  const calc = useMemo(() => {
    if (!prices.data?.length || syms.length < 1) return null;
    const { syms: ok, R } = returnsMatrix(prices.data, syms);
    if (R.length < 30) return null;
    let w: number[];
    if (mode === "reco" && recoW.size) {
      const raw = ok.map((s) => recoW.get(s) ?? 0);
      const tot = raw.reduce((a, b) => a + b, 0) || 1;
      w = raw.map((v) => v / tot); // poids publiés par le cron (renormalisés si un cours manque)
    } else {
      w = weights(R, mode === "reco" ? "markowitz" : mode);
    }
    const st = portfolioStats(R, w);
    const mc = monteCarlo(st.returns, capital);
    return { ok, w, st, mc };
  }, [prices.data, mode, capital, syms.join(","), reco.data?.updated_at]);

  const suggestions = q.trim().length >= 1
    ? (snap.data ?? []).filter((s) => !syms.includes(s.symbol) && (s.symbol.includes(q.toUpperCase()) || (s.nom ?? "").toUpperCase().includes(q.toUpperCase()))).slice(0, 6)
    : [];
  const add = (s: string) => { const n = [...mesTitres, s].slice(0, 15); setSyms(n); setQ(""); save(n, capital, mode); };
  const remove = (s: string) => { const n = mesTitres.filter((x) => x !== s); setSyms(n); save(n, capital, mode); };
  const choisirMode = (m: Mode) => {
    // Passer du recommandé à Markowitz/équipondéré : on part des titres recommandés
    const base = mode === "reco" && m !== "reco" && recoW.size ? [...recoW.keys()] : mesTitres;
    setSyms(base); setMode(m); save(base, capital, m);
  };

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
        <div><h1>Portefeuille</h1><p class="sub">{num(capital, 0)} € · simulation sur 1 an d'historique</p></div>
        <HelpButton keys={["sharpe", "max_drawdown", "volatility"]} intro={<>
          <p><b>Recommandé</b> : portefeuille Markowitz calculé par le serveur sur tout l'univers (présélection par momentum, 20 % max par ligne). <b>Équipondéré</b> : même montant sur chaque titre. <b>Markowitz</b> : poids qui maximisent le rendement par unité de risque (portefeuille « tangent », taux sans risque {pct(RF, 2, false)}), sans vente à découvert, 20 % max par ligne.</p>
          <p>Avec un petit capital (200 €), certaines lignes font quelques euros : il faut un courtier qui accepte les <b>fractions d'actions</b>.</p>
          <p><b>Monte-Carlo</b> : 1 000 trajectoires d'un an tirées au hasard parmi les rendements quotidiens passés du portefeuille. La zone colorée contient 90 % des scénarios.</p>
          <p>⚠️ Basé sur 1 an de données passées : Markowitz a tendance à sur-pondérer les titres qui ont le plus monté récemment.</p>
        </>} />
      </header>

      <Card title="Composition" class="tint-accent">
        <div class="seg full" role="group" aria-label="Méthode">
          {MODES.map((m) => <button class={mode === m.k ? "on" : ""} onClick={() => choisirMode(m.k)}>{m.label}</button>)}
        </div>
        {mode === "reco" ? (
          reco.data ? (
            <>
              <p class="hint" style={{ marginTop: 0 }}>
                Portefeuille <b>Markowitz</b> calculé chaque jour par le serveur sur tout l'univers
                ({reco.data.lignes.length} lignes, mis à jour {ilYA(reco.data.updated_at)}).
                Pour le modifier, passe en mode Markowitz : il sera repris comme point de départ.
              </p>
              <Details summary="Méthode">{reco.data.methode}</Details>
            </>
          ) : reco.loading ? <Loading /> : (
            <div class="note">Portefeuille recommandé pas encore publié : il apparaîtra après la prochaine synchro.</div>
          )
        ) : (
          <>
            <div class="chips wrap">
              {syms.map((s) => <button class="chip on" onClick={() => remove(s)} aria-label={`Retirer ${s}`}>{s} ✕</button>)}
            </div>
            <input type="search" placeholder="Ajouter un titre…" value={q} onInput={(e) => setQ((e.target as HTMLInputElement).value)} aria-label="Ajouter un titre" />
            {suggestions.length > 0 && <ul class="suggest">{suggestions.map((s) => <li><button onClick={() => add(s.symbol)}><b>{s.symbol}</b> <span class="muted">{s.nom}</span></button></li>)}</ul>}
          </>
        )}
        <label class="field" style={{ marginTop: 10 }}>Capital à investir (€)
          <input type="number" inputMode="numeric" min={50} step={50} value={capital}
            onChange={(e) => { const c = Math.max(50, Number((e.target as HTMLInputElement).value) || 200); setCapital(c); save(mesTitres, c, mode); }} />
        </label>
      </Card>

      {prices.loading && !calc ? <Loading label="Chargement des cours…" /> : !calc ? (
        <div class="note">Ajoute au moins un titre avec un historique suffisant.</div>
      ) : (
        <>
          <Card title="Répartition">
            <table class="table">
              <thead><tr><th>Titre</th><th>Poids</th><th>Montant</th></tr></thead>
              <tbody>{calc.ok.map((s, i) => ({ s, w: calc.w[i] })).sort((a, b) => b.w - a.w).map(({ s, w }) => (
                <tr><td><b>{s}</b>{recoW.size && mode === "reco" && <><br /><small class="muted">{reco.data?.lignes.find((l) => l.symbol === s)?.secteur ?? ""}</small></>}</td>
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
    </div>
  );
}
