import { useCallback, useState } from "preact/hooks";
import { api } from "../api";
import { Card, ChartBox, cssVar, Details, HelpButton, Loading, OfflineNote, Stat, toneOf, useData } from "../components";
import { ilYA, num, pct } from "../format";
import { choisirPoint, HORIZON_DEFAUT, HORIZONS, projection } from "../strategy";
import { MesTitres } from "./MesTitres";
import { PlanAchat } from "./PlanAchat";

const KEY = "thesee:objectif:v1";
type Onglet = "objectif" | "titres";
interface Etat { onglet: Onglet; capital: number; cible: number; horizon: string }
const DEFAUT: Etat = { onglet: "objectif", capital: 200, cible: 0.08, horizon: HORIZON_DEFAUT };
const charger = (): Etat => {
  try { return { ...DEFAUT, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") }; } catch { return DEFAUT; }
};

export function Portfolio() {
  const [e, setE] = useState<Etat>(charger());
  const maj = (p: Partial<Etat>) => {
    const n = { ...e, ...p };
    setE(n);
    try { localStorage.setItem(KEY, JSON.stringify(n)); } catch { /* ignore */ }
  };
  const reco = useData(api.portefeuilleReco);
  const ov = useData(api.overview);
  const snap = useData(api.snapshot);

  const h = HORIZONS.find((x) => x.k === e.horizon) ?? HORIZONS[4];
  const frontiere = reco.data?.frontiere ?? [];
  const choix = choisirPoint(frontiere, e.cible);
  const lignes = choix?.point.lignes ?? [];
  const prix: Record<string, number | null | undefined> = {
    ...Object.fromEntries(Object.entries(reco.data?.titres ?? {}).map(([k, v]) => [k, v.prix])),
    ...Object.fromEntries((snap.data ?? []).map((x) => [x.symbol, x.close])),
  };
  const proj = choix ? projection(e.capital, choix.point.rendement, choix.point.volatilite, h.annees, e.cible) : null;

  return (
    <div class="screen">
      <header class="screen-head">
        <div><h1>Portefeuille</h1><p class="sub">{num(e.capital, 0)} € · horizon {h.label}</p></div>
        <HelpButton keys={["sharpe", "volatility", "max_drawdown"]} intro={<>
          <p><b>Objectif</b> : tu fixes la rentabilité visée par an et ton horizon. L'appli choisit, parmi les meilleurs titres du moment,
            le portefeuille <b>le moins risqué</b> qui l'atteint en théorie (frontière efficiente de Markowitz, 20 % max par titre).</p>
          <p><b>Rentabilité attendue</b> : estimée surtout par le modèle CAPM (taux sans risque + prime de risque selon la sensibilité
            du titre au marché), et seulement à 10 % par l'historique. Les titres ont été choisis parce qu'ils ont monté : leur passé
            surestime l'avenir. Ce n'est pas une promesse, c'est une estimation volontairement prudente (≈ 8 à 12 %/an pour des actions).</p>
          <p><b>Fourchette</b> : 90 % des scénarios simulés finissent entre la valeur basse et la valeur haute (modèle log-normal).</p>
          <p><b>Mes titres</b> : tu choisis toi-même les titres ; l'appli calcule les poids (Markowitz ou parts égales).</p>
        </>} />
      </header>

      <div class="seg full" role="tablist">
        <button role="tab" aria-selected={e.onglet === "objectif"} class={e.onglet === "objectif" ? "on" : ""} onClick={() => maj({ onglet: "objectif" })}>Objectif</button>
        <button role="tab" aria-selected={e.onglet === "titres"} class={e.onglet === "titres" ? "on" : ""} onClick={() => maj({ onglet: "titres" })}>Mes titres</button>
      </div>

      <Card title="Mon objectif" class="tint-accent">
        <label class="field">Capital à investir (€)
          <input type="number" inputMode="numeric" min={50} step={50} value={e.capital}
            onChange={(ev) => maj({ capital: Math.max(50, Number((ev.target as HTMLInputElement).value) || 200) })} />
        </label>
        <div class="field" style={{ marginTop: 10 }}>Horizon de placement
          <div class="chips wrap" role="group" aria-label="Horizon">
            {HORIZONS.map((x) => <button class={`chip ${e.horizon === x.k ? "on" : ""}`} onClick={() => maj({ horizon: x.k })}>{x.label}</button>)}
          </div>
        </div>
        <p class="hint" style={{ marginTop: 4 }}>{h.conseil}</p>
        {e.onglet === "objectif" && (
          <div class="field" style={{ marginTop: 12 }}>
            <span>Rentabilité visée : <b class="accent">{pct(e.cible, 0, false)} par an</b></span>
            <input type="range" min={0.02} max={0.3} step={0.01} value={e.cible} aria-label="Rentabilité visée par an"
              onInput={(ev) => maj({ cible: Number((ev.target as HTMLInputElement).value) })} />
            <div class="range-labels"><span>2 %</span><span>8 % ≈ actions long terme</span><span>30 %</span></div>
          </div>
        )}
      </Card>

      {e.onglet === "titres" ? (
        <MesTitres capital={e.capital} depart={lignes.map((l) => l.symbol)} eurusd={ov.data?.eurusd ?? null} />
      ) : (
        <>
          <OfflineNote res={reco.res} />
          {reco.loading && !reco.data ? <Loading /> : !choix ? (
            <div class="note">Le portefeuille objectif sera disponible après la prochaine synchronisation du serveur.</div>
          ) : (
            <>
              <Card title="Portefeuille proposé" class={`edge-${choix.atteignable ? "good" : "bad"}`}>
                {choix.atteignable ? (
                  <p class="verdict">Le portefeuille le moins risqué qui vise <b>{pct(e.cible, 0, false)}</b> par an attend
                    <b> {pct(choix.point.rendement, 1, false)}</b> avec une volatilité de <b>{pct(choix.point.volatilite, 0, false)}</b>.</p>
                ) : (
                  <div class="note warn">
                    {pct(e.cible, 0, false)} par an n'est pas atteignable sans dépasser 20 % par titre.
                    Maximum estimé : <b>{pct(choix.max, 1, false)}</b> par an. Portefeuille affiché : le plus rentable possible.
                  </div>
                )}
                {proj && (
                  <>
                    <h3 class="h3">Dans {h.label}, pour {num(e.capital, 0)} € investis</h3>
                    <div class="stats">
                      <Stat label="Scénario bas (5 %)" value={`${num(proj.bas, 0)} €`} tone={proj.bas < e.capital ? "bad" : "good"} />
                      <Stat label="Médian" value={`${num(proj.median, 0)} €`} tone={proj.median >= e.capital ? "good" : "bad"} />
                      <Stat label="Scénario haut (95 %)" value={`${num(proj.haut, 0)} €`} tone="good" />
                    </div>
                    <div class="stats">
                      <Stat label="Probabilité de perte" value={pct(proj.probPerte, 0, false)}
                        tone={proj.probPerte > 0.3 ? "bad" : proj.probPerte > 0.15 ? "neutral" : "good"} />
                      <Stat label="Atteindre l'objectif" value={pct(proj.probObjectif, 0, false)} sub={`≥ ${num(proj.valeurObjectif, 0)} €`}
                        tone={proj.probObjectif >= 0.5 ? "good" : proj.probObjectif >= 0.35 ? "neutral" : "bad"} />
                      <Stat label="Volatilité" value={pct(choix.point.volatilite, 0, false)} tone={toneOf("volatility", choix.point.volatilite)} />
                    </div>
                  </>
                )}
                <Frontiere frontiere={frontiere} choisi={choix.point.rendement} cible={e.cible} />
              </Card>

              <Card title={`Titres sélectionnés (${lignes.length})`}>
                <table class="table">
                  <thead><tr><th>Titre</th><th>Poids</th><th>Montant</th></tr></thead>
                  <tbody>{lignes.map((l) => {
                    const t = reco.data?.titres?.[l.symbol];
                    const maxP = Math.max(...lignes.map((x) => x.poids));
                    return (
                      <tr>
                        <td><b>{l.symbol}</b><br /><small class="muted">{t?.nom ?? ""}{t?.secteur ? ` · ${t.secteur}` : ""}</small></td>
                        <td><div class="wbar"><div style={{ width: `${(l.poids / maxP) * 100}%` }} /></div>{pct(l.poids, 1, false)}</td>
                        <td><b>{num(l.poids * e.capital, 2)} €</b></td>
                      </tr>
                    );
                  })}</tbody>
                </table>
                <Details summary="Comment ces titres sont choisis">
                  <p>{reco.data?.methode}</p>
                  <p class="hint">Mis à jour {ilYA(reco.data?.updated_at)}. Les titres changent quand le marché change :
                    en buy and hold, garde ton portefeuille et ne suis pas chaque mise à jour.</p>
                </Details>
              </Card>

              <PlanAchat capital={e.capital} lignes={lignes} prix={prix} eurusd={ov.data?.eurusd ?? null} annees={h.annees} />
            </>
          )}
        </>
      )}
    </div>
  );
}

/** Frontière efficiente : risque (x) / rentabilité attendue (y), point choisi en évidence. */
function Frontiere({ frontiere, choisi, cible }: { frontiere: { rendement: number; volatilite: number }[]; choisi: number; cible: number }) {
  const cfg = useCallback(() => {
    const pts = [...frontiere].sort((a, b) => a.volatilite - b.volatilite);
    const accent = cssVar("--accent");
    return {
      type: "line",
      data: {
        datasets: [
          { label: "Frontière efficiente", data: pts.map((p) => ({ x: p.volatilite * 100, y: p.rendement * 100 })),
            borderColor: cssVar("--info"), borderWidth: 2, pointRadius: 2, tension: 0.3 },
          { label: "Ton portefeuille", data: pts.filter((p) => Math.abs(p.rendement - choisi) < 1e-9).map((p) => ({ x: p.volatilite * 100, y: p.rendement * 100 })),
            borderColor: accent, backgroundColor: accent, pointRadius: 7, showLine: false },
          { label: "Objectif", data: [{ x: pts[0].volatilite * 100, y: cible * 100 }, { x: pts[pts.length - 1].volatilite * 100, y: cible * 100 }],
            borderColor: cssVar("--muted"), borderDash: [4, 3], borderWidth: 1, pointRadius: 0 },
        ],
      },
      options: {
        plugins: { legend: { position: "bottom" } },
        scales: {
          x: { type: "linear", title: { display: true, text: "Risque (volatilité %/an)", color: cssVar("--muted") } },
          y: { title: { display: true, text: "Rentabilité attendue %/an", color: cssVar("--muted") } },
        },
      },
    };
  }, [frontiere, choisi, cible]);
  if (frontiere.length < 2) return null;
  return <ChartBox config={cfg} height={220} label="Frontière efficiente : rentabilité attendue selon le risque" />;
}
