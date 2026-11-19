import { useEffect } from "preact/hooks";
import type { ComponentChildren } from "preact";
import { api } from "../api";
import { Card, Loading, textePreuve, useData } from "../components";
import { corr, num, pct, ratioPct } from "../format";
import { avecVolIA, covariance, rendementsAttendus, sousUnivers, variance } from "../optim";
import { coutAnnualise, planAchat, projection } from "../strategy";
import { usePortefeuilleCible } from "./Portfolio";

/** Une étape de calcul : formule, ce qu'elle veut dire en mots, puis la même formule avec les vrais nombres. */
function Etape({ titre, formule, definition, calcul, children }: {
  titre: string; formule: string; definition: ComponentChildren; calcul?: ComponentChildren; children?: ComponentChildren;
}) {
  return (
    <div class="etape">
      <h3 class="h3">{titre}</h3>
      <code class="formule">{formule}</code>
      <p class="definition">{definition}</p>
      {calcul && <div class="calcul">{calcul}</div>}
      {children}
    </div>
  );
}

/** Fiche de calculs : chaque chiffre du portefeuille affiché, recalculé pas à pas (même portefeuille que l'onglet Portefeuille). */
export function Calculs({ section }: { section?: string }) {
  const { e, h, u: u0, choix, params: p, reco, ov, volIA, fiab } = usePortefeuilleCible();
  const models = useData(api.models);
  // Ouvre et montre la section demandée par un lien « Vérifier ce calcul »
  useEffect(() => {
    if (!section) return;
    const t = setTimeout(() => document.getElementById(`calc-${section}`)?.scrollIntoView({ behavior: "smooth", block: "start" }), 250);
    return () => clearTimeout(t);
  }, [section, Boolean(choix)]);

  if (reco.loading && !u0) return <div class="screen"><Loading /></div>;
  if (!u0 || !choix) return <div class="screen"><a class="back" href="#/analyse">‹</a><div class="note">Données du serveur indisponibles : relance le calcul.</div></div>;

  // Même univers que le portefeuille affiché : titres exclus retirés, volatilités IA si choisies
  const su = sousUnivers(u0, e.exclus);
  const u = volIA ? avecVolIA(su) : su;
  const pt = choix.point;
  const mu = rendementsAttendus(u, p);
  const idx = new Map(u.symbols.map((s, i) => [s, i]));
  const lignes = pt.lignes.map((l) => {
    const i = idx.get(l.symbol)!;
    const capm = p.tauxSansRisque + u.beta[i] * p.primeRisque;
    return { ...l, i, beta: u.beta[i], hist: u.mu_hist[i], capm, mu: mu[i], vol: Math.sqrt(variance(u, i)) };
  });
  const er = lignes.reduce((a, l) => a + l.poids * l.mu, 0);
  let variancePf = 0;
  for (const a of lignes) for (const b of lignes) variancePf += a.poids * b.poids * covariance(u, a.i, b.i);
  const vol = Math.sqrt(variancePf);
  // Gain de diversification : risque moyen des titres contre risque du portefeuille, et ce que
  // cela rapporte en rendement composé (≈ σ²/2 de moins perdu chaque année, si l'on rééquilibre)
  const volMoy = lignes.reduce((a, l) => a + l.poids * l.vol, 0);
  const gainCompose = (volMoy * volMoy - vol * vol) / 2;
  const pr = projection(e.capital, er, vol, h.annees, e.mode === "risque" ? er : e.cible, p.confiance);
  const prix = Object.fromEntries(Object.entries(reco.data?.titres ?? {}).map(([k, v]) => [k, v.prix]));
  const fx = ov.data?.eurusd ?? 1.08;
  const plan = planAchat(e.capital, pt.lignes, prix, fx, { fraisOrdre: p.fraisOrdre, fraisChange: p.fraisChange, fractions: p.fractions, margeLimite: p.margeLimite, tranches: 1, frequence: "mois" });
  const coutAn = coutAnnualise(plan.partFrais, p.fraisChange, h.annees);
  const ex = lignes[0];
  const exOrdre = plan.tranches[0]?.ordres.find((o) => o.symbol === ex.symbol);

  return (
    <div class="screen">
      <header class="screen-head">
        <a class="back" href={section ? "#/portefeuille" : "#/analyse"} aria-label="Retour">‹</a>
        <div class="grow"><h1>Fiche de calculs</h1>
          <p class="sub">Ton portefeuille · {num(e.capital, 0)} € · {e.mode === "risque" ? `risque max ${pct(e.volMax, 0, false)}` : `objectif ${pct(e.cible, 0, false)}/an`} · {h.label}
            {volIA ? ` · risque prévu (${fiab.source === "hybride" ? "IA + HAR" : fiab.source === "har" ? "HAR" : "IA"})` : ""}{e.exclus.length ? ` · ${e.exclus.length} exclu(s)` : ""}</p></div>
      </header>

      <Card title="1. Rentabilité attendue de chaque titre" repliable id="calc-rendement" ouvert={!section || section === "rendement"}>
        <Etape titre="Modèle CAPM" formule="μ_CAPM = taux sans risque + β × prime de risque"
          definition={<>Ce qu'un titre « devrait » rapporter selon le risque de marché qu'il porte. <b>μ</b> (mu) = rentabilité attendue par an ;
            <b> β</b> (bêta) = de combien le titre bouge quand le marché bouge de 1 (β = 1,5 : il bouge 1,5 fois plus) ; la prime de risque est le
            supplément que paient les actions par rapport à un placement sans risque.</>}
          calcul={<>{ex.symbol} : {pct(p.tauxSansRisque, 2, false)} + {num(ex.beta, 2)} × {pct(p.primeRisque, 2, false)} = <b>{pct(ex.capm, 2, false)}</b></>} />
        <Etape titre="Mélange avec l'historique" formule="μ = (1 − h) × μ_CAPM + h × μ_historique"
          definition={<>On ajoute un peu de ce que le titre a réellement rapporté ces 3 dernières années. <b>h</b> = part donnée à l'historique
            ({pct(p.poidsHistorique, 0, false)}) : faible, car un titre choisi parce qu'il a monté ne remontera pas forcément autant.</>}
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

      <Card title="2. Rentabilité et risque du portefeuille" repliable id="calc-risque" ouvert={!section || section === "risque"}>
        <Etape titre="Rentabilité attendue" formule="E[R] = Σ wᵢ × μᵢ"
          definition={<>La rentabilité du portefeuille est la moyenne des rentabilités des titres, pondérée par leur part. <b>wᵢ</b> = part du titre i
            dans le portefeuille ; <b>Σ</b> = somme sur tous les titres.</>} calcul={<>somme de la dernière colonne = <b>{pct(er, 2, false)}</b> par an</>} />
        <Etape titre="Volatilité" formule="σ = √( Σᵢ Σⱼ wᵢ × wⱼ × covᵢⱼ )"
          definition={<>Le risque : de combien la valeur s'écarte en général de sa tendance sur un an (σ = 15 % : une année « normale » finit
            entre −15 % et +15 % autour de la moyenne). <b>covᵢⱼ</b> = covariance, mesure de combien deux titres montent et baissent ensemble.
            {volIA && " Ici les volatilités de chaque titre sont celles prévues par l'IA, les corrélations restent historiques."}</>}
          calcul={<>variance = {num(variancePf, 5)} → σ = <b>{pct(vol, 2, false)}</b> par an</>}>
          <p class="hint">La covariance (Ledoit-Wolf, 3 ans) tient compte des titres qui montent et baissent ensemble : le risque du portefeuille est inférieur à la moyenne des risques.</p>
        </Etape>
        <Etape titre="Gain de diversification" formule="σ moy = Σ wᵢ σᵢ ; gain ≈ (σ moy² − σ²) / 2"
          definition={<>Si les titres montaient et baissaient tous ensemble, le risque du portefeuille serait la moyenne de leurs risques
            (<b>σ moy</b>). Comme ce n'est pas le cas, une partie des écarts se compense. Le rendement composé (année après année) perd environ σ²/2
            par an à cause des écarts : un portefeuille moins agité garde ce surplus, à condition de <b>rééquilibrer</b> (revenir aux parts cibles).
            C'est un calcul, pas une prévision.</>}
          calcul={<>σ moy = {pct(volMoy, 1, false)} → σ = {pct(vol, 1, false)} (−{pct(1 - vol / volMoy, 0, false)}) ;
            gain ≈ ({pct(volMoy, 1, false)}² − {pct(vol, 1, false)}²) / 2 = <b>{pct(gainCompose, 2, false)}</b> de rendement composé par an</>} />
        <Etape titre="Rendement / risque" formule="E[R] / σ"
          definition={<>Combien de rentabilité on obtient pour chaque point de risque supporté. Affiché en % dans l'appli.</>}
          calcul={<>{pct(er, 2, false)} / {pct(vol, 2, false)} = <b>{ratioPct(er, vol)}</b></>} />
        <Etape titre="Ratio de Sharpe" formule="Sharpe = (E[R] − taux sans risque) / σ"
          definition={<>Même idée, mais en ne comptant que ce qui dépasse un placement sans risque (livret, bons du Trésor) : c'est la récompense
            réelle du risque pris. Au-dessus de 0,5, c'est correct ; au-dessus de 1, très bon.</>}
          calcul={<>({pct(er, 2, false)} − {pct(p.tauxSansRisque, 2, false)}) / {pct(vol, 2, false)} = <b>{num((er - p.tauxSansRisque) / vol, 2)}</b></>} />
        <Etape titre="Choix sur la frontière" formule={e.mode === "risque" ? "portefeuille de rentabilité maximale tel que σ ≤ risque max" : "portefeuille de risque minimal tel que E[R] ≥ objectif"}
          definition={<>La frontière efficiente rassemble les meilleurs portefeuilles possibles : pour chaque niveau de risque, celui qui rapporte le plus.
            On y prend le point qui respecte ton objectif.</>}
          calcul={<>{e.mode === "risque" ? `risque max ${pct(e.volMax, 1, false)}` : `objectif ${pct(e.cible, 1, false)}`} → {choix.atteignable ? "respecté" : "hors d'atteinte"} ;
            contraintes : {pct(p.poidsMax, 0, false)} max par titre, ≤ {p.nMaxLignes} lignes ≥ {pct(p.poidsMin, 1, false)}</>} />
      </Card>

      <Card title={`3. Projection à ${h.label}`} repliable id="calc-projection" ouvert={!section || section === "projection"}>
        <Etape titre="Paramètres log-normaux" formule="m = (ln(1 + E[R]) − σ²/2) × T     s = σ × √T"
          definition={<>On suppose que les gains se composent dans le temps (modèle log-normal, celui des marchés). <b>m</b> = tendance attendue sur
            la durée <b>T</b> (en années), <b>s</b> = incertitude qui grandit avec la durée. <b>ln</b> = logarithme.</>}
          calcul={<>T = {num(h.annees, 2)} an → m = {num(pr.m, 4)}, s = {num(pr.s, 4)}</>} />
        <Etape titre="Fourchette" formule={`valeur = capital × exp(m ± z × s),  z = ${num(pr.z, 3)} (${pct(p.confiance, 0, false)} des scénarios)`}
          definition={<>Mauvais cas, cas médian et bon cas : {pct(p.confiance, 0, false)} des scénarios finissent entre le bas et le haut.
            <b> z</b> = nombre d'écarts-types correspondant, pris dans une <b>loi de Student à 5 degrés</b> (queues plus épaisses que
            la loi normale) : au backtest 2006-2026, la loi normale sous-estimait les mauvaises années (mauvais cas 5 % touché 8,8 % du temps).</>}
          calcul={<>bas {num(pr.bas, 2)} € · médian {num(pr.median, 2)} € · haut {num(pr.haut, 2)} €</>} />
        <Etape titre="Probabilité de perte" formule="P(perte) = Φ(−m / s)"
          definition={<>La part des scénarios où tu récupères moins que ta mise. <b>Φ</b> (phi) = probabilité que la loi (ici Student à 5 degrés) soit sous une valeur.</>} calcul={<>Φ({num(-pr.m / pr.s, 3)}) = <b>{pct(pr.probPerte, 1, false)}</b></>} />
        <Etape titre="Probabilité d'atteindre l'objectif" formule="P = Φ((m − T × ln(1 + objectif)) / s)"
          definition={<>La part des scénarios qui atteignent la rentabilité visée sur toute la durée.</>}
          calcul={<>Φ({num((pr.m - h.annees * Math.log(1 + e.cible)) / pr.s, 3)}) = <b>{pct(pr.probObjectif, 1, false)}</b> (valeur visée {num(pr.valeurObjectif, 2)} €)</>}>
          <p class="hint">Φ = fonction de répartition de la loi normale. Hypothèse : rendements log-normaux, volatilité constante (sous-estime les krachs).</p>
        </Etape>
      </Card>

      <Card title="4. Ordres et frais" repliable id="calc-frais" ouvert={!section || section === "frais"}>
        {exOrdre && (
          <Etape titre={`Exemple : ${ex.symbol}`} formule="quantité = (capital × poids × (1 − change) × EUR/USD) / prix ; limite = prix × (1 + marge)"
            definition={<>Combien d'actions acheter avec le montant prévu pour ce titre, et le prix maximum à accepter (ordre « à cours limité »).</>}
            calcul={<>({num(e.capital, 0)} × {pct(ex.poids, 1, false)} × {num(1 - p.fraisChange, 4)} × {num(fx, 4)}) / {num(exOrdre.prix, 2)} $ = <b>{num(exOrdre.quantite, 4)}</b> ;
              limite = {num(exOrdre.prix, 2)} × {num(1 + p.margeLimite, 3)} = <b>{num(exOrdre.limite, 2)} $</b></>} />
        )}
        <Etape titre="Frais d'entrée" formule="frais = nb d'ordres × frais par ordre + investi × frais de change"
          definition={<>Ce que coûte la mise en place : un forfait par ordre et, si ton courtier convertit en dollars, une commission de change.</>}
          calcul={<>{plan.nbOrdres} × {num(p.fraisOrdre, 2)} € + {num(plan.fraisChangeEur, 2)} € = <b>{num(plan.totalFrais, 2)} €</b> ({pct(plan.partFrais, 2, false)})</>} />
        <Etape titre="Coût annualisé" formule="1 − ((1 − frais d'entrée) × (1 − change à la revente))^(1/T)"
          definition={<>Les frais d'achat et de revente, étalés sur la durée : ce qu'ils retirent à ta rentabilité chaque année.</>}
          calcul={<><b>{pct(coutAn, 2, false)}</b> par an sur {h.label}</>} />
      </Card>

      <Card title="5. Modèles IA" repliable id="calc-ia" ouvert={!section || section === "ia"}>
        <Etape titre="Coefficient d'information (IC)" formule="IC = corrélation de rang (classement prédit, performance relative réalisée), moyenne des dates de test"
          definition={<>L'IC (« Information Coefficient ») dit si les titres que le modèle classe en tête ont vraiment fait mieux, en %. 0 % = hasard,
            5 % = déjà bon en gestion. Le <b>t</b> dit si ce résultat se distingue du hasard.</>}>
          <table class="table small"><tbody>{["court", "6m", "1a"].map((k) => {
            const m = models.data?.find((x) => x.kind === `horizon_${k}`);
            const d = m?.diagnostics ?? {};
            return <tr><td>{k === "court" ? "1 mois" : k === "6m" ? "6 mois" : "1 an"}</td><td>IC {corr(d.ic_moyen)}</td><td>preuve <b>{textePreuve(d.t_stat, d.seuil_t)}</b> du seuil<br /><small class="muted">t {num(d.t_stat, 1)}{d.seuil_t != null && ` / ${num(d.seuil_t, 1)}`}</small></td></tr>;
          })}</tbody></table>
          <p class="hint">Force de la preuve = t / seuil, en % : à 100 % ou plus, le résultat ne s'explique plus par le hasard.
            t = IC moyen / écart-type × √(périodes indépendantes) ; le seuil est relevé quand il y a peu de périodes ou plusieurs essais
            (sinon le hasard finit par faire gagner un modèle). « Signal » si IC &gt; 3 % et preuve ≥ 100 %.</p>
        </Etape>
        <Etape titre="IA de risque" formule="volatilité prévue = classement IA du risque → niveau des volatilités 3 mois du moment"
          definition={<>L'IA classe les titres du plus calme au plus agité pour les 6 prochains mois ; chaque rang reçoit le niveau de volatilité
            correspondant parmi les titres actuels. Testée sur 2013-2026 : meilleure que la volatilité passée sur 91 % des dates.</>} />
      </Card>
    </div>
  );
}
