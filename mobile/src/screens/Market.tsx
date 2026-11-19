import { useMemo, useState } from "preact/hooks";
import { api, getFavoris, type Snapshot } from "../api";
import { Chip, HelpButton, Loading, OfflineNote, useData, RefreshButton } from "../components";
import { num, pct, prix, signClass } from "../format";
import { useFiabiliteVol } from "../fiabilite";
import { per } from "../valorisation";
import { BadgeTeste } from "./Portfolio";

type Tri = "symbol" | "chg_1d" | "chg_20d" | "chg_1y" | "vol_ia" | "vol_ia_calme" | "per";
// Tris par prévision de l'IA : seulement si son dernier test est probant
const TRIS_IA: Tri[] = ["vol_ia_calme", "vol_ia"];
const TRIS: { k: Tri; label: string }[] = [
  { k: "chg_1d", label: "Aujourd'hui" }, { k: "chg_20d", label: "1 mois" }, { k: "chg_1y", label: "1 an" },
  { k: "vol_ia_calme", label: "Les plus calmes (IA)" }, { k: "vol_ia", label: "Les plus agités (IA)" },
  { k: "per", label: "Les moins chers (PER)" }, { k: "symbol", label: "A → Z" },
];

export function Market({ go }: { go: (h: string) => void }) {
  const snap = useData(api.snapshot);
  const [q, setQ] = useState("");
  const [secteur, setSecteur] = useState("Tous");
  const [indice, setIndice] = useState("Tous");
  const [tri, setTri] = useState<Tri>("chg_1d");
  const [favOnly, setFavOnly] = useState(false);
  const favoris = getFavoris();
  const fiab = useFiabiliteVol();
  const tris = TRIS.filter((t) => fiab.probant || !TRIS_IA.includes(t.k));
  const triEff: Tri = !fiab.probant && TRIS_IA.includes(tri) ? "chg_1d" : tri;

  // Sans preuve, la prévision IA n'est pas montrée (même si une ancienne valeur est en cache)
  const rows = useMemo(() => (snap.data ?? []).map((r) => (fiab.probant ? r : { ...r, vol_ia: null })), [snap.data, fiab.probant]);
  const secteurs = useMemo(() => ["Tous", ...Array.from(new Set(rows.map((r) => r.secteur).filter(Boolean))).sort()], [rows]);
  const indices = useMemo(() => ["Tous", ...Array.from(new Set(rows.map((r) => r.indice).filter(Boolean))).sort()], [rows]);

  const filtered = useMemo(() => {
    const qq = q.trim().toUpperCase();
    let out = rows.filter((r) =>
      (!qq || r.symbol.includes(qq) || (r.nom ?? "").toUpperCase().includes(qq)) &&
      (secteur === "Tous" || r.secteur === secteur) &&
      (indice === "Tous" || r.indice === indice) &&
      (!favOnly || favoris.includes(r.symbol)));
    const val = (r: Snapshot) => (triEff === "vol_ia_calme" ? -(r.vol_ia ?? Infinity)
      : triEff === "per" ? -(per(r) ?? Infinity) : ((r as any)[triEff] as number | null) ?? -Infinity);
    out = [...out].sort((a, b) => triEff === "symbol" ? a.symbol.localeCompare(b.symbol) : val(b) - val(a));
    // PER : les entreprises en perte ou sans comptes SEC (banques, ETF…) sont retirées du classement
    if (triEff === "per") out = out.filter((r) => per(r) != null);
    return out;
  }, [rows, q, secteur, indice, triEff, favOnly]);

  const [limit, setLimit] = useState(60);

  return (
    <div class="screen">
      <header class="screen-head">
        <div><h1>Quels titres bougent ?</h1><p class="sub">{rows.length} titres suivis · S&P 500, Nasdaq-100, ETF</p></div>
        <RefreshButton />
        <HelpButton keys={["chg_20d", "rsi_14", "volatility"]}
          intro={<><p>Chaque ligne montre le prix et la variation du jour (bord gauche <span class="up">vert</span> = hausse,
            <span class="down"> rouge</span> = baisse), puis : la performance sur 1 mois, le RSI (élan récent, « Relative Strength Index »)
            et le <b>risque</b> : volatilité des 3 dernières années, ou celle que prévoit l'IA pour les 6 prochains mois quand son
            dernier test est probant (« Risque IA »).</p>
            <p><b>PER</b> (Price Earnings Ratio) : cours / bénéfice annuel par action, d'après les comptes officiels déposés à la SEC.
            « Les moins chers » ne veut pas dire « meilleurs » : au laboratoire, ce critère n'a pas prédit la performance.</p></>} />
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
          {tris.map((t) => <button class={`chip ${triEff === t.k ? "on" : ""}`} onClick={() => setTri(t.k)}>{t.label}</button>)}
        </div>
        {fiab.probant && TRIS_IA.includes(triEff) && <p class="hint">Volatilité prévue sur 6 mois <BadgeTeste /></p>}
        {triEff === "per" && <p class="hint">Comptes officiels (SEC). Les entreprises en perte ou sans comptes SEC sont retirées.
          Un PER bas n'est pas un signal d'achat : il n'a pas prédit la performance au laboratoire.</p>}
      </div>

      {snap.loading && !rows.length ? <Loading /> : (
        <>
          <p class="count">{filtered.length} résultat(s)</p>
          <ul class="list">
            {filtered.slice(0, limit).map((r) => <Row r={r} go={go} fav={favoris.includes(r.symbol)} avecPer={triEff === "per"} />)}
          </ul>
          {filtered.length > limit && <button class="more" onClick={() => setLimit(limit + 100)}>Afficher plus</button>}
        </>
      )}
    </div>
  );
}

function Row({ r, go, fav, avecPer }: { r: Snapshot; go: (h: string) => void; fav: boolean; avecPer?: boolean }) {
  return (
    <li>
      <button class={`row ${r.chg_1d == null ? "" : r.chg_1d > 0 ? "row-up" : r.chg_1d < 0 ? "row-down" : ""}`} onClick={() => go(`#/titre/${r.symbol}`)}>
        <div class="row-main">
          <div class="row-title"><b>{r.symbol}</b>{fav && <span class="star">★</span>}<span class="muted ellipsis">{r.nom}</span></div>
          <div class="mchips">
            <Chip k="chg_20d" v={r.chg_20d} label="1 mois" value={pct(r.chg_20d, 0)} />
            <Chip k="rsi_14" v={r.rsi_14} label="RSI" />
            <Chip k="volatility" v={r.vol_ia ?? r.volatility} label={r.vol_ia != null ? "Risque IA" : "Risque"} />
            {avecPer && <span class="mchip neutral">PER <b>{num(per(r), 1)}</b></span>}
          </div>
        </div>
        <div class="row-side"><span>{prix(r.close)}</span><span class={signClass(r.chg_1d)}>{pct(r.chg_1d)}</span></div>
      </button>
    </li>
  );
}
