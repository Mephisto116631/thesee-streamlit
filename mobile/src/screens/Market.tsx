import { useMemo, useState } from "preact/hooks";
import { api, getFavoris, type Snapshot } from "../api";
import { Chip, HelpButton, Loading, OfflineNote, useData, RefreshButton } from "../components";
import { pct, prix, signClass } from "../format";

type Tri = "symbol" | "chg_1d" | "chg_20d" | "chg_1y" | "rsi_14" | "proba_hausse";
const TRIS: { k: Tri; label: string }[] = [
  { k: "symbol", label: "A → Z" }, { k: "chg_1d", label: "Var. jour" }, { k: "chg_20d", label: "1 mois" },
  { k: "chg_1y", label: "1 an" }, { k: "rsi_14", label: "RSI" }, { k: "proba_hausse", label: "Signal IA" },
];

export function Market({ go }: { go: (h: string) => void }) {
  const snap = useData(api.snapshot);
  const [q, setQ] = useState("");
  const [secteur, setSecteur] = useState("Tous");
  const [indice, setIndice] = useState("Tous");
  const [tri, setTri] = useState<Tri>("chg_1d");
  const [favOnly, setFavOnly] = useState(false);
  const favoris = getFavoris();

  const rows = snap.data ?? [];
  const secteurs = useMemo(() => ["Tous", ...Array.from(new Set(rows.map((r) => r.secteur).filter(Boolean))).sort()], [rows]);
  const indices = useMemo(() => ["Tous", ...Array.from(new Set(rows.map((r) => r.indice).filter(Boolean))).sort()], [rows]);

  const filtered = useMemo(() => {
    const qq = q.trim().toUpperCase();
    let out = rows.filter((r) =>
      (!qq || r.symbol.includes(qq) || (r.nom ?? "").toUpperCase().includes(qq)) &&
      (secteur === "Tous" || r.secteur === secteur) &&
      (indice === "Tous" || r.indice === indice) &&
      (!favOnly || favoris.includes(r.symbol)));
    out = [...out].sort((a, b) => tri === "symbol" ? a.symbol.localeCompare(b.symbol)
      : ((b[tri] as number | null) ?? -Infinity) - ((a[tri] as number | null) ?? -Infinity));
    return out;
  }, [rows, q, secteur, indice, tri, favOnly]);

  const [limit, setLimit] = useState(60);

  return (
    <div class="screen">
      <header class="screen-head">
        <div><h1>Marché</h1><p class="sub">{rows.length} titres · S&P 500, Nasdaq-100, ETF</p></div>
        <RefreshButton />
        <HelpButton keys={["chg_20d", "rsi_14", "volatility", "proba_hausse"]}
          intro={<p>Chaque carte montre le prix, la variation du jour (bord gauche <span class="up">vert</span> = hausse, <span class="down">rouge</span> = baisse) et <b>4 étiquettes</b> : performance 1 mois · RSI · volatilité · signal IA. <span class="badge good">vert</span> favorable, <span class="badge neutral">gris</span> neutre, <span class="badge bad">rouge</span> défavorable, <span class="badge info">bleu</span> excès à surveiller.</p>} />
      </header>
      <OfflineNote res={snap.res} />

      <div class="filters">
        <input type="search" placeholder="Ticker ou société (ex. AAPL, Apple)" value={q} onInput={(e) => setQ((e.target as HTMLInputElement).value)} aria-label="Rechercher" />
        <div class="filter-row">
          <select value={secteur} onChange={(e) => setSecteur((e.target as HTMLSelectElement).value)} aria-label="Secteur">
            {secteurs.map((s) => <option value={s}>{s === "Tous" ? "Tous secteurs" : s}</option>)}
          </select>
          <select value={indice} onChange={(e) => setIndice((e.target as HTMLSelectElement).value)} aria-label="Indice">
            {indices.map((s) => <option value={s}>{s === "Tous" ? "Tous indices" : s}</option>)}
          </select>
        </div>
        <div class="chips" role="group" aria-label="Trier par">
          <button class={`chip ${favOnly ? "on" : ""}`} onClick={() => setFavOnly(!favOnly)}>★ Favoris</button>
          {TRIS.map((t) => <button class={`chip ${tri === t.k ? "on" : ""}`} onClick={() => setTri(t.k)}>{t.label}</button>)}
        </div>
      </div>

      {snap.loading && !rows.length ? <Loading /> : (
        <>
          <p class="count">{filtered.length} résultat(s)</p>
          <ul class="list">
            {filtered.slice(0, limit).map((r) => <Row r={r} go={go} fav={favoris.includes(r.symbol)} />)}
          </ul>
          {filtered.length > limit && <button class="more" onClick={() => setLimit(limit + 100)}>Afficher plus</button>}
        </>
      )}
    </div>
  );
}

function Row({ r, go, fav }: { r: Snapshot; go: (h: string) => void; fav: boolean }) {
  return (
    <li>
      <button class={`row ${r.chg_1d == null ? "" : r.chg_1d > 0 ? "row-up" : r.chg_1d < 0 ? "row-down" : ""}`} onClick={() => go(`#/titre/${r.symbol}`)}>
        <div class="row-main">
          <div class="row-title"><b>{r.symbol}</b>{fav && <span class="star">★</span>}<span class="muted ellipsis">{r.nom}</span></div>
          <div class="mchips">
            <Chip k="chg_20d" v={r.chg_20d} label="1 mois" value={pct(r.chg_20d, 0)} />
            <Chip k="rsi_14" v={r.rsi_14} label="RSI" />
            <Chip k="volatility" v={r.volatility} label="Vol" />
            <Chip k="proba_hausse" v={r.proba_hausse} label="IA" />
          </div>
        </div>
        <div class="row-side"><span>{prix(r.close)}</span><span class={signClass(r.chg_1d)}>{pct(r.chg_1d)}</span></div>
      </button>
    </li>
  );
}
