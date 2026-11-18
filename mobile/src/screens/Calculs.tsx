import { useMemo } from "preact/hooks";
import type { ComponentChildren } from "preact";
import { api } from "../api";
import { Card, Loading, useData } from "../components";
import { num, pct } from "../format";
import { frontiere, rendementsAttendus, type Univers } from "../optim";
import { useParametres } from "../settings";
import { choisirPoint, coutAnnualise, HORIZONS, planAchat, projection } from "../strategy";

/** Une étape de calcul : formule, puis la même formule avec les vrais nombres. */
function Etape({ titre, formule, calcul, children }: { titre: string; formule: string; calcul?: ComponentChildren; children?: ComponentChildren }) {
  return (
    <div class="etape">
      <h3 class="h3">{titre}</h3>
      <code class="formule">{formule}</code>
      {calcul && <div class="calcul">{calcul}</div>}
      {children}
    </div>
  );
}

const etatPortefeuille = () => {
  try { return { capital: 200, cible: 0.08, horizon: "1a", ...JSON.parse(localStorage.getItem("thesee:objectif:v1") ?? "{}") }; }
  catch { return { capital: 200, cible: 0.08, horizon: "1a" }; }
};

/** Fiche de calculs : chaque chiffre du portefeuille Hold, recalculé pas à pas. */
export function Calculs() {
  const p = useParametres();
  const reco = useData(api.portefeuilleReco);
  const ov = useData(api.overview);
  const models = useData(api.models);
  const e = etatPortefeuille();
  const h = HORIZONS.find((x) => x.k === e.horizon) ?? HORIZONS[3];
  const u = reco.data?.univers as Univers | undefined;
  const f = useMemo(() => (u ? frontiere(u, p) : []), [u, p]);

  if (reco.loading && !u) return <div class="screen"><Loading /></div>;
  if (!u || !f.length) return <div class="screen"><a class="back" href="#/parametres">‹</a><div class="note">Données du serveur indisponibles : relance le calcul.</div></div>;

  const choix = choisirPoint(f, e.cible)!;
  const pt = choix.point;
  const mu = rendementsAttendus(u, p);
  const idx = new Map(u.symbols.map((s, i) => [s, i]));
  const lignes = pt.lignes.map((l) => {
    const i = idx.get(l.symbol)!;
    const capm = p.tauxSansRisque + u.beta[i] * p.primeRisque;
    return { ...l, i, beta: u.beta[i], hist: u.mu_hist[i], capm, mu: mu[i], vol: Math.sqrt(u.cov[i][i]) };
  });
  const er = lignes.reduce((a, l) => a + l.poids * l.mu, 0);
  let variance = 0;
  for (const a of lignes) for (const b of lignes) variance += a.poids * b.poids * u.cov[a.i][b.i];
  const vol = Math.sqrt(variance);
  const pr = projection(e.capital, er, vol, h.annees, e.cible, p.confiance);
  const prix = Object.fromEntries(Object.entries(reco.data?.titres ?? {}).map(([k, v]) => [k, v.prix]));
  const fx = ov.data?.eurusd ?? 1.08;
  const plan = planAchat(e.capital, pt.lignes, prix, fx, { fraisOrdre: p.fraisOrdre, fraisChange: p.fraisChange, fractions: p.fractions, margeLimite: p.margeLimite, tranches: 1, frequence: "mois" });
  const coutAn = coutAnnualise(plan.partFrais, p.fraisChange, h.annees);
  const ex = lignes[0];
  const exOrdre = plan.tranches[0]?.ordres.find((o) => o.symbol === ex.symbol);

  return (
    <div class="screen">
      <header class="screen-head">
        <a class="back" href="#/parametres" aria-label="Retour">‹</a>
        <div class="grow"><h1>Fiche de calculs</h1>
          <p class="sub">Portefeuille Hold · {num(e.capital, 0)} € · objectif {pct(e.cible, 0, false)}/an · {h.label}</p></div>
      </header>

      <Card title="1. Rentabilité attendue de chaque titre">
        <Etape titre="Modèle CAPM" formule="μ_CAPM = taux sans risque + β × prime de risque"
          calcul={<>{ex.symbol} : {pct(p.tauxSansRisque, 2, false)} + {num(ex.beta, 2)} × {pct(p.primeRisque, 2, false)} = <b>{pct(ex.capm, 2, false)}</b></>} />
        <Etape titre="Mélange avec l'historique" formule="μ = (1 − h) × μ_CAPM + h × μ_historique"
          calcul={<>{ex.symbol} : {num(1 - p.poidsHistorique, 2)} × {pct(ex.capm, 2, false)} + {num(p.poidsHistorique, 2)} × {pct(ex.hist, 1, false)} = <b>{pct(ex.mu, 2, false)}</b></>}>
          <p class="hint">β = sensibilité au marché (SPY) sur 3 ans ; μ_historique = rendement annuel moyen sur 3 ans.</p>
        </Etape>
        <div class="table-scroll">
          <table class="table small">
            <thead><tr><th>Titre</th><th>β</th><th>Hist.</th><th>CAPM</th><th>μ</th><th>Vol.</th><th>Poids</th><th>w×μ</th></tr></thead>
            <tbody>{lignes.map((l) => (
              <tr><td><b>{l.symbol}</b></td><td>{num(l.beta, 2)}</td><td>{pct(l.hist, 1, false)}</td><td>{pct(l.capm, 1, false)}</td>
                <td><b>{pct(l.mu, 1, false)}</b></td><td>{pct(l.vol, 0, false)}</td><td>{pct(l.poids, 1, false)}</td><td>{pct(l.poids * l.mu, 2, false)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </Card>

      <Card title="2. Rentabilité et risque du portefeuille">
        <Etape titre="Rentabilité attendue" formule="E[R] = Σ wᵢ × μᵢ" calcul={<>somme de la dernière colonne = <b>{pct(er, 2, false)}</b> par an</>} />
        <Etape titre="Volatilité" formule="σ = √( Σᵢ Σⱼ wᵢ × wⱼ × covᵢⱼ )"
          calcul={<>variance = {num(variance, 5)} → σ = <b>{pct(vol, 2, false)}</b> par an</>}>
          <p class="hint">La covariance (Ledoit-Wolf, 3 ans) tient compte des titres qui montent et baissent ensemble : le risque du portefeuille est inférieur à la moyenne des risques.</p>
        </Etape>
        <Etape titre="Ratio de Sharpe" formule="Sharpe = (E[R] − taux sans risque) / σ"
          calcul={<>({pct(er, 2, false)} − {pct(p.tauxSansRisque, 2, false)}) / {pct(vol, 2, false)} = <b>{num((er - p.tauxSansRisque) / vol, 2)}</b></>} />
        <Etape titre="Choix sur la frontière" formule="portefeuille de variance minimale tel que E[R] ≥ objectif"
          calcul={<>objectif {pct(e.cible, 1, false)} → {choix.atteignable ? "atteint" : `hors d'atteinte (max ${pct(choix.max, 1, false)})`} ;
            contraintes : {pct(p.poidsMax, 0, false)} max par titre, ≤ {p.nMaxLignes} lignes ≥ {pct(p.poidsMin, 1, false)}</>} />
      </Card>

      <Card title={`3. Projection à ${h.label}`}>
        <Etape titre="Paramètres log-normaux" formule="m = (ln(1 + E[R]) − σ²/2) × T     s = σ × √T"
          calcul={<>T = {num(h.annees, 2)} an → m = {num(pr.m, 4)}, s = {num(pr.s, 4)}</>} />
        <Etape titre="Fourchette" formule={`valeur = capital × exp(m ± z × s),  z = ${num(pr.z, 3)} (${pct(p.confiance, 0, false)} des scénarios)`}
          calcul={<>bas {num(pr.bas, 2)} € · médian {num(pr.median, 2)} € · haut {num(pr.haut, 2)} €</>} />
        <Etape titre="Probabilité de perte" formule="P(perte) = Φ(−m / s)" calcul={<>Φ({num(-pr.m / pr.s, 3)}) = <b>{pct(pr.probPerte, 1, false)}</b></>} />
        <Etape titre="Probabilité d'atteindre l'objectif" formule="P = Φ((m − T × ln(1 + objectif)) / s)"
          calcul={<>Φ({num((pr.m - h.annees * Math.log(1 + e.cible)) / pr.s, 3)}) = <b>{pct(pr.probObjectif, 1, false)}</b> (valeur visée {num(pr.valeurObjectif, 2)} €)</>}>
          <p class="hint">Φ = fonction de répartition de la loi normale. Hypothèse : rendements log-normaux, volatilité constante (sous-estime les krachs).</p>
        </Etape>
      </Card>

      <Card title="4. Ordres et frais">
        {exOrdre && (
          <Etape titre={`Exemple : ${ex.symbol}`} formule="quantité = (capital × poids × (1 − change) × EUR/USD) / prix ; limite = prix × (1 + marge)"
            calcul={<>({num(e.capital, 0)} × {pct(ex.poids, 1, false)} × {num(1 - p.fraisChange, 4)} × {num(fx, 4)}) / {num(exOrdre.prix, 2)} $ = <b>{num(exOrdre.quantite, 4)}</b> ;
              limite = {num(exOrdre.prix, 2)} × {num(1 + p.margeLimite, 3)} = <b>{num(exOrdre.limite, 2)} $</b></>} />
        )}
        <Etape titre="Frais d'entrée" formule="frais = nb d'ordres × frais par ordre + investi × frais de change"
          calcul={<>{plan.nbOrdres} × {num(p.fraisOrdre, 2)} € + {num(plan.fraisChangeEur, 2)} € = <b>{num(plan.totalFrais, 2)} €</b> ({pct(plan.partFrais, 2, false)})</>} />
        <Etape titre="Coût annualisé" formule="1 − ((1 − frais d'entrée) × (1 − change à la revente))^(1/T)"
          calcul={<><b>{pct(coutAn, 2, false)}</b> par an sur {h.label}</>} />
      </Card>

      <Card title="5. Modèles IA">
        <Etape titre="Coefficient d'information (IC)" formule="IC = corrélation de rang (classement prédit, performance relative réalisée), moyenne des dates de test">
          <table class="table small"><tbody>{["court", "6m", "1a"].map((k) => {
            const m = models.data?.find((x) => x.kind === `horizon_${k}`);
            const d = m?.diagnostics ?? {};
            return <tr><td>{k === "court" ? "1 mois" : k === "6m" ? "6 mois" : "1 an"}</td><td>IC {num(d.ic_moyen, 3)}</td><td>t = {num(d.t_stat, 1)}</td><td>momentum {num(d.ic_momentum, 3)}</td></tr>;
          })}</tbody></table>
          <p class="hint">t = IC moyen / écart-type × √(observations indépendantes) ; verdict « signal » si IC &gt; 0,03, t &gt; 2 et IC &gt; momentum seul.</p>
        </Etape>
        <Etape titre="Mode court terme" formule="poidsᵢ = (1 / volᵢ) / Σ (1 / volⱼ), plafonné" />
      </Card>
    </div>
  );
}
