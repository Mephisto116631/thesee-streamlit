import { useEffect, useState } from "preact/hooks";
import { api, lirePositions, type Position, surChangementSession, utilisateurCourant } from "../api";
import { Card, Details, Loading, OfflineNote, RangeBar, ReglagesButton, RefreshButton, Stat, toneOf, useData, ZoneBadge } from "../components";
import { dateFr, ilYA, num, pct } from "../format";
import { zoneIndex } from "../ranges";
import { useParametres } from "../settings";
import { usePortefeuilleCible } from "./Portfolio";

const EURUSD_SECOURS = 1.08;

/** Accueil : trois questions — où en est mon argent, que me conseille l'appli, comment va le marché. */
export function Home({ go }: { go: (h: string) => void }) {
  const ov = useData(api.overview);
  const sync = useData(api.lastSync);
  const o = ov.data;
  const s = sync.data;

  return (
    <div class="screen">
      <header class="screen-head">
        <div>
          <h1>Thésée</h1>
          <p class="sub">
            {s ? <>Données {s.status === "error" ? "⚠️ dernière synchro en erreur" : "à jour"} · {ilYA(s.finished_at ?? s.started_at)}</> : "—"}
            {o?.date && <> · clôture du {dateFr(o.date)}</>}
          </p>
        </div>
        <RefreshButton />
        <ReglagesButton />
      </header>
      <OfflineNote res={ov.res} />

      <MonArgent go={go} />
      <Conseil go={go} />
      {ov.loading && !o ? <Loading /> : o && <Humeur o={o} go={go} />}

      <p class="foot">Les performances passées ne préjugent pas des performances futures. Thésée ne passe aucun ordre à ta place.</p>
    </div>
  );
}

/** Où en est mon argent : valeur, plus-value, besoin de rééquilibrer. */
function MonArgent({ go }: { go: (h: string) => void }) {
  const p = useParametres();
  const snap = useData(api.snapshot);
  const ov = useData(api.overview);
  const [connecte, setConnecte] = useState<boolean | undefined>(undefined);
  const [positions, setPositions] = useState<Position[] | null>(null);
  useEffect(() => {
    const lire = () => utilisateurCourant().then((u) => {
      setConnecte(Boolean(u));
      if (u) lirePositions().then(setPositions).catch(() => setPositions([]));
    });
    lire();
    return surChangementSession(lire);
  }, []);

  if (connecte === undefined) return null;
  if (!connecte) {
    return (
      <Card title="Mon argent">
        <p class="hint" style={{ marginTop: 0 }}>Connecte-toi pour suivre ce que tu possèdes : valeur, gain ou perte, et quand rééquilibrer.</p>
        <button class="more" onClick={() => go("#/positions")}>Suivre mes positions ›</button>
      </Card>
    );
  }
  if (!positions || !snap.data) return <Card title="Mon argent"><Loading /></Card>;
  if (!positions.length) {
    return (
      <Card title="Mon argent">
        <p class="hint" style={{ marginTop: 0 }}>Aucune position enregistrée. Passe tes premiers ordres depuis le portefeuille conseillé.</p>
        <button class="more" onClick={() => go("#/portefeuille")}>Voir le portefeuille conseillé ›</button>
      </Card>
    );
  }
  const fx = ov.data?.eurusd ?? EURUSD_SECOURS;
  const cours = new Map(snap.data.map((x) => [x.symbol, x.close / fx]));
  let investi = 0, valeur = 0;
  const parTitre = new Map<string, number>();
  for (const x of positions) {
    investi += x.quantite * (x.prix_achat_eur ?? 0) + (x.frais_eur ?? 0);
    const v = x.quantite * (cours.get(x.symbol) ?? x.prix_achat_eur ?? 0);
    valeur += v;
    parTitre.set(x.symbol, (parTitre.get(x.symbol) ?? 0) + v);
  }
  const pv = valeur - investi;
  const depasse = [...parTitre.entries()].filter(([, v]) => valeur > 0 && v / valeur > p.seuilReequilibrage).map(([k]) => k);
  return (
    <Card title="Mon argent" right={<button class="link" onClick={() => go("#/positions")}>Détails ›</button>}>
      <div class="stats">
        <Stat label="Valeur" value={`${num(valeur, 2)} €`} />
        <Stat label="Gain / perte" value={`${pv >= 0 ? "+" : ""}${num(pv, 2)} €`} sub={investi > 0 ? pct(pv / investi, 1) : ""} tone={pv >= 0 ? "good" : "bad"} />
      </div>
      {depasse.length
        ? <div class="note warn">À rééquilibrer : {depasse.join(", ")} dépasse {pct(p.seuilReequilibrage, 0, false)} du portefeuille.</div>
        : <p class="hint">Rien à faire : aucune ligne ne dépasse {pct(p.seuilReequilibrage, 0, false)} du portefeuille.</p>}
    </Card>
  );
}

/** Ce que conseille l'appli pour mon objectif. */
function Conseil({ go }: { go: (h: string) => void }) {
  const { e, h, choix, lignes, volIA } = usePortefeuilleCible();
  if (!choix) return null;
  const pt = choix.point;
  return (
    <Card title="Portefeuille conseillé" class="tint-accent" right={<button class="link" onClick={() => go("#/portefeuille")}>Ouvrir ›</button>}>
      <p class="verdict" style={{ marginTop: 0 }}>Pour <b>{num(e.capital, 0)} €</b> sur <b>{h.label}</b> :
        {" "}{lignes.length} titres, rentabilité attendue <b>{pct(pt.rendement, 1, false)}</b> par an.</p>
      <div class="stats">
        <Stat label="Volatilité" value={pct(pt.volatilite, 0, false)} sub={volIA ? "prévue par l'IA" : "historique 3 ans"} tone={toneOf("volatility", pt.volatilite)} />
        <Stat label="Rendement / risque" value={num(pt.rendement / Math.max(pt.volatilite, 1e-9), 2)} tone={pt.rendement / pt.volatilite >= 0.6 ? "good" : "neutral"} />
      </div>
    </Card>
  );
}

/** Humeur du marché en une phrase : volatilité attendue, crédit, largeur de la tendance. */
function Humeur({ o, go }: { o: any; go: (h: string) => void }) {
  const tension = (zoneIndex("vix", o.vix) ?? 1) + (zoneIndex("spread_pct", o.hy_pct_10y) ?? 1)
    + (o.pct_above_ma200 == null ? 1 : o.pct_above_ma200 < 40 ? 2 : o.pct_above_ma200 > 60 ? 0 : 1);
  const [mot, couleur, phrase] = tension <= 1 ? ["Calme", "var(--up)", "Peu de stress : volatilité basse, crédit détendu, la plupart des titres en tendance haussière."]
    : tension <= 3 ? ["Normal", "var(--accent)", "Rien d'inhabituel. En buy and hold, aucune action particulière."]
      : ["Tendu", "var(--down)", "Le marché est nerveux. En buy and hold, ne vends pas dans la panique : les baisses font partie du parcours."];
  return (
    <Card title="Humeur du marché">
      <div class="humeur"><span class="pastille" style={{ background: couleur }} /><b>{mot}</b></div>
      <p class="hint">{phrase}</p>
      <Details summary="Voir les indicateurs">
        <RangeBar k="vix" v={o.vix} />
        <div class="stats">
          <Stat label="Titres > MM200" value={`${Math.round(o.pct_above_ma200 ?? 0)} %`} sub="tendance long terme" />
          <Stat label="Crédit High Yield" value={`${Math.round(o.hy_spread_bp ?? 0)} pb`} sub={<><ZoneBadge k="spread_pct" v={o.hy_pct_10y} /></>} />
        </div>
        <p class="hint">VIX : volatilité attendue du S&P 500 (indice de la peur). MM200 : moyenne des 200 derniers jours.
          High Yield : surcoût d'emprunt des entreprises les plus fragiles, en points de base (pb, 1 pb = 0,01 %).</p>
        <button class="link" onClick={() => go("#/risque")}>Analyse détaillée ›</button>
      </Details>
    </Card>
  );
}
