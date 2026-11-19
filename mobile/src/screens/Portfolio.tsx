import { useCallback, useMemo, useState } from "preact/hooks";
import { api } from "../api";
import { Card, ChartBox, cssVar, Details, HelpButton, Loading, OfflineNote, RefreshButton, ReglagesButton, Stat, toneOf, useData } from "../components";
import { frontiere as calculerFrontiere, type Univers } from "../optim";
import { nbModifies, useParametres } from "../settings";
import { ilYA, num, pct } from "../format";
import { choisirPoint, choisirPointRisque, HORIZON_DEFAUT, HORIZONS, projection } from "../strategy";
import { MonteCarlo } from "./MonteCarlo";
import { PlanAchat } from "./PlanAchat";

const KEY = "thesee:objectif:v1";
// Hold : horizons de 6 mois et plus (en dessous, c'est le mode court terme)
const HORIZONS_HOLD = HORIZONS.filter((x) => x.annees >= 0.5);
export interface Etat { capital: number; cible: number; horizon: string; mode: "rendement" | "risque"; volMax: number }
const DEFAUT: Etat = { capital: 200, cible: 0.08, horizon: HORIZON_DEFAUT, mode: "rendement", volMax: 0.15 };
const charger = (): Etat => {
  try { return { ...DEFAUT, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") }; } catch { return DEFAUT; }
};

/** Objectif de l'utilisateur et portefeuille conseillé qui en découle : partagé par l'accueil,
 *  le portefeuille et les positions (l'objectif est gardé sur le téléphone). */
export function usePortefeuilleCible() {
  const [e, setE] = useState<Etat>(charger());
  const maj = (p: Partial<Etat>) => {
    const n = { ...e, ...p };
    setE(n);
    try { localStorage.setItem(KEY, JSON.stringify(n)); } catch { /* ignore */ }
  };
  const reco = useData(api.portefeuilleReco);
  const ov = useData(api.overview);
  const snap = useData(api.snapshot);

  const h = HORIZONS_HOLD.find((x) => x.k === e.horizon) ?? HORIZONS_HOLD.find((x) => x.k === "1a")!;
  const params = useParametres();
  const u = reco.data?.univers as Univers | undefined;
  // Frontière recalculée sur le téléphone avec les hypothèses de la page Paramètres
  // (repli : celle du serveur si l'univers n'est pas encore publié).
  const frontiere = useMemo(() => (u ? calculerFrontiere(u, params) : reco.data?.frontiere ?? []),
    [u, reco.data?.frontiere, params.tauxSansRisque, params.primeRisque, params.poidsHistorique, params.poidsMax, params.nMaxLignes, params.poidsMin, params.sourceVol]);
  const modifies = nbModifies(params);
  const choix = e.mode === "risque" ? choisirPointRisque(frontiere, e.volMax) : choisirPoint(frontiere, e.cible);
  const volIA = params.sourceVol === "ia" && Boolean(u?.vol_ia?.length);
  const volHistDe = new Map((u?.symbols ?? []).map((sy, i) => [sy, Math.sqrt(Math.max(u!.cov[i][i], 0))]));
  const volIADe = new Map((u?.symbols ?? []).map((sy, i) => [sy, u?.vol_ia?.[i] ?? null]));
  const lignes = choix?.point.lignes ?? [];
  return { e, maj, reco, ov, snap, h, params, u, frontiere, modifies, choix, volIA, volHistDe, volIADe, lignes };
}

export function Portfolio() {
  const { e, maj, reco, ov, snap, h, params, frontiere, modifies, choix, volIA, volHistDe, volIADe, lignes } = usePortefeuilleCible();
  const prix: Record<string, number | null | undefined> = {
    ...Object.fromEntries(Object.entries(reco.data?.titres ?? {}).map(([k, v]) => [k, v.prix])),
    ...Object.fromEntries((snap.data ?? []).map((x) => [x.symbol, x.close])),
  };
  const proj = choix ? projection(e.capital, choix.point.rendement, choix.point.volatilite, h.annees, e.cible, params.confiance) : null;
  const queue = pct((1 - params.confiance) / 2, 0, false);

  return (
    <div class="screen">
      <header class="screen-head">
        <div><h1>Portefeuille</h1><p class="sub">{num(e.capital, 0)} € · horizon {h.label}</p></div>
        <HelpButton keys={["sharpe", "volatility", "max_drawdown"]} intro={<>
          <p><b>Objectif</b> : tu fixes la rentabilité visée par an et ton horizon. L'appli choisit, parmi les meilleurs titres du moment,
            le portefeuille <b>le moins risqué</b> qui l'atteint en théorie (frontière efficiente de Markowitz, 20 % max par titre).</p>
          <p>Toutes les hypothèses (taux sans risque, prime de risque, plafonds, frais…) se règlent dans les <b>Paramètres</b> (roue dentée ⚙ en haut à droite).</p>
          <p><b>Rentabilité attendue</b> : estimée surtout par le modèle CAPM (taux sans risque + prime de risque selon la sensibilité
            du titre au marché), et seulement à 10 % par l'historique. Les titres ont été choisis parce qu'ils ont monté : leur passé
            surestime l'avenir. Ce n'est pas une promesse, c'est une estimation volontairement prudente (≈ 8 à 12 %/an pour des actions).</p>
          <p><b>Fourchette</b> : 90 % des scénarios simulés finissent entre la valeur basse et la valeur haute (modèle log-normal).</p>
        </>} />
        <RefreshButton />
        <ReglagesButton />
      </header>
      {modifies > 0 && <div class="note">Calculé avec {modifies} hypothèse(s) personnalisée(s) — <a href="#/parametres">voir les Paramètres</a>.</div>}


      <Card title="Mon objectif" class="tint-accent">
        <label class="field">Capital à investir (€)
          <input type="number" inputMode="numeric" min={50} step={50} value={e.capital}
            onChange={(ev) => maj({ capital: Math.max(50, Number((ev.target as HTMLInputElement).value) || 200) })} />
        </label>
        {(
          <>
            <div class="field" style={{ marginTop: 10 }}>Horizon de placement
              <div class="chips wrap" role="group" aria-label="Horizon">
                {HORIZONS_HOLD.map((x) => <button class={`chip ${e.horizon === x.k ? "on" : ""}`} onClick={() => maj({ horizon: x.k })}>{x.label}</button>)}
              </div>
            </div>
            <p class="hint" style={{ marginTop: 4 }}>{h.conseil}</p>
          </>
        )}
        {(
          <>
            <div class="seg full" role="group" aria-label="Ce que je fixe" style={{ marginTop: 12 }}>
              <button class={e.mode === "rendement" ? "on" : ""} onClick={() => maj({ mode: "rendement" })}>Je vise une rentabilité</button>
              <button class={e.mode === "risque" ? "on" : ""} onClick={() => maj({ mode: "risque" })}>Je limite le risque</button>
            </div>
            {e.mode === "rendement" ? (
              <div class="field">
                <span>Rentabilité visée : <b class="accent">{pct(e.cible, 0, false)} par an</b></span>
                <input type="range" min={0.02} max={0.3} step={0.01} value={e.cible} aria-label="Rentabilité visée par an"
                  onInput={(ev) => maj({ cible: Number((ev.target as HTMLInputElement).value) })} />
                <div class="range-labels"><span>2 %</span><span>8 % ≈ actions long terme</span><span>30 %</span></div>
              </div>
            ) : (
              <div class="field">
                <span>Volatilité maximale : <b class="accent">{pct(e.volMax, 0, false)} par an</b></span>
                <input type="range" min={0.08} max={0.35} step={0.01} value={e.volMax} aria-label="Volatilité maximale par an"
                  onInput={(ev) => maj({ volMax: Number((ev.target as HTMLInputElement).value) })} />
                <div class="range-labels"><span>8 % calme</span><span>≈ 18 % S&P 500</span><span>35 % agité</span></div>
                <p class="hint">Le portefeuille le plus rentable dont la volatilité reste sous ce plafond.
                  Volatilité {volIA ? "prévue par l'IA" : "historique (3 ans)"} — à changer dans <a href="#/parametres">Paramètres</a>.</p>
              </div>
            )}
          </>
        )}
      </Card>

      {(
        <>
          <OfflineNote res={reco.res} />
          {reco.loading && !reco.data ? <Loading /> : !choix ? (
            <div class="note">Le portefeuille objectif sera disponible après la prochaine synchronisation du serveur.</div>
          ) : (
            <>
              <Card title="Portefeuille proposé" class={`edge-${choix.atteignable ? "good" : "bad"}`}>
                {e.mode === "risque" ? (
                  choix.atteignable ? (
                    <p class="verdict">Le portefeuille le plus rentable avec au plus <b>{pct(e.volMax, 0, false)}</b> de volatilité attend
                      <b> {pct(choix.point.rendement, 1, false)}</b> par an (volatilité <b>{pct(choix.point.volatilite, 0, false)}</b>).</p>
                  ) : (
                    <div class="note warn">Aucun portefeuille n'est aussi calme avec ces titres : le moins volatil possible est à
                      <b> {pct(choix.point.volatilite, 0, false)}</b>. Portefeuille affiché : celui-là.</div>
                  )
                ) : choix.atteignable ? (
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
                      <Stat label={`Scénario bas (${queue})`} value={`${num(proj.bas, 0)} €`} tone={proj.bas < e.capital ? "bad" : "good"} />
                      <Stat label="Médian" value={`${num(proj.median, 0)} €`} tone={proj.median >= e.capital ? "good" : "bad"} />
                      <Stat label={`Scénario haut (${pct(1 - (1 - params.confiance) / 2, 0, false)})`} value={`${num(proj.haut, 0)} €`} tone="good" />
                    </div>
                    <div class="stats">
                      <Stat label="Probabilité de perte" value={pct(proj.probPerte, 0, false)}
                        tone={proj.probPerte > 0.3 ? "bad" : proj.probPerte > 0.15 ? "neutral" : "good"} />
                      <Stat label="Atteindre l'objectif" value={pct(proj.probObjectif, 0, false)} sub={`≥ ${num(proj.valeurObjectif, 0)} €`}
                        tone={proj.probObjectif >= 0.5 ? "good" : proj.probObjectif >= 0.35 ? "neutral" : "bad"} />
                      <Stat label="Volatilité" value={pct(choix.point.volatilite, 0, false)} tone={toneOf("volatility", choix.point.volatilite)}
                        sub={volIA ? "prévue par l'IA" : "historique 3 ans"} />
                    </div>
                    <div class="stats">
                      <Stat label="Rendement / risque" value={num(choix.point.rendement / Math.max(choix.point.volatilite, 1e-9), 2)}
                        sub="rendement attendu ÷ volatilité" tone={choix.point.rendement / choix.point.volatilite >= 0.6 ? "good" : "neutral"} />
                      {choix.point.sharpe != null && <Stat label="Sharpe" value={num(choix.point.sharpe, 2)}
                        sub="au-delà du taux sans risque" tone={toneOf("sharpe", choix.point.sharpe)} />}
                    </div>
                  </>
                )}
                <Details summary="Voir la frontière efficiente (tous les compromis risque / rendement)">
                  <Frontiere frontiere={frontiere} choisi={choix.point.rendement} cible={e.cible} />
                </Details>
              </Card>

              <Card title={`Titres sélectionnés (${lignes.length})`}>
                <table class="table">
                  <thead><tr><th>Titre</th><th>Poids</th><th>Volatilité<br /><small>3 ans · IA</small></th><th>Montant</th></tr></thead>
                  <tbody>{lignes.map((l) => {
                    const t = reco.data?.titres?.[l.symbol];
                    const maxP = Math.max(...lignes.map((x) => x.poids));
                    return (
                      <tr>
                        <td><b>{l.symbol}</b><br /><small class="muted">{t?.nom ?? ""}{t?.secteur ? ` · ${t.secteur}` : ""}</small>
</td>
                        <td><div class="wbar"><div style={{ width: `${(l.poids / maxP) * 100}%` }} /></div>{pct(l.poids, 1, false)}</td>
                        <td class="nowrap">{pct(volHistDe.get(l.symbol), 0, false)}
                          {volIADe.get(l.symbol) != null && <> · <b class={(volIADe.get(l.symbol) ?? 0) > (volHistDe.get(l.symbol) ?? 0) ? "down" : "up"}>{pct(volIADe.get(l.symbol), 0, false)}</b></>}</td>
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

              <Card>
                <Details paresseux summary={`Simulation Monte-Carlo sur ${h.label} (option)`}>
                  <MonteCarlo lignes={lignes} capital={e.capital} annees={h.annees} volCible={choix.point.volatilite}
                    source={volIA ? "prévue par l'IA" : "historique 3 ans"} />
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
