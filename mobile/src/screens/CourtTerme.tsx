import { api } from "../api";
import { Card, Chip, Loading, Stat, useData } from "../components";
import { num, pct } from "../format";
import { capWeights } from "../portfolio";
import { useParametres } from "../settings";
import { PlanAchat } from "./PlanAchat";

/** Mode court terme : les titres les mieux classés par le modèle 1 mois, renouvelés à chaque rotation. */
export function CourtTerme({ capital, eurusd }: { capital: number; eurusd: number | null }) {
  const p = useParametres();
  const scores = useData(() => api.scores("court"));
  const snap = useData(api.snapshot);
  const models = useData(api.models);
  const m = models.data?.find((x) => x.kind === "horizon_court");
  const d = m?.diagnostics ?? {};

  if ((scores.loading && !scores.data?.length) || (snap.loading && !snap.data?.length)) return <Loading />;
  const infos = new Map((snap.data ?? []).map((s) => [s.symbol, s]));
  const retenus = (scores.data ?? [])
    .filter((s) => s.score >= p.ctScoreMin && infos.get(s.symbol)?.volatility)
    .sort((a, b) => b.score - a.score)
    .slice(0, p.ctNbTitres);
  if (!retenus.length) {
    return <div class="note">Aucun titre classé par le modèle 1 mois avec un score ≥ {pct(p.ctScoreMin, 0, false)} : relance le calcul
      (Risque &amp; IA) ou baisse le score minimal dans Réglages.</div>;
  }
  // Poids inversement proportionnels à la volatilité (un titre agité pèse moins), plafonnés
  const inv = retenus.map((s) => 1 / (infos.get(s.symbol)!.volatility as number));
  const tot = inv.reduce((a, b) => a + b, 0);
  const poids = capWeights(inv.map((x) => x / tot), Math.max(p.poidsMax, 1 / retenus.length));
  const lignes = retenus.map((s, i) => ({ symbol: s.symbol, poids: poids[i] }));

  // Coût de la rotation : on suppose qu'environ la moitié du portefeuille change à chaque fois
  const rotationsAn = p.ctRotation === "semaine" ? 52 : 12;
  const rotationPart = 0.5;
  const ordresParRotation = Math.round(lignes.length * rotationPart * 2); // ventes + achats
  const coutAn = rotationsAn * (ordresParRotation * p.fraisOrdre + capital * rotationPart * 2 * p.fraisChange);
  const ton = m?.verdict === "signal" ? "good" : m?.verdict === "bruit" ? "neutral" : "bad";

  return (
    <>
      <Card title="Modèle 1 mois" class={`edge-${ton}`}>
        {m ? (
          <>
            <p class="verdict">
              {m.verdict === "signal" ? "Le classement à 1 mois a montré un lien net avec les performances réelles."
                : m.verdict === "bruit" ? "Le classement à 1 mois n'a montré qu'un lien faible avec la réalité : prudence."
                : "Le classement à 1 mois n'a pas montré de lien avec la réalité : ce mode revient à choisir au hasard."}
            </p>
            <div class="stats">
              <Stat label="IC moyen" value={num(d.ic_moyen, 3)} sub="> 0,03 = utile" tone={ton} />
              <Stat label="Top quintile" value={pct(d.rendement_par_quintile?.[4], 1)} sub="vs médiane, sur 1 mois (test)" />
            </div>
          </>
        ) : <p class="hint">Modèle 1 mois pas encore entraîné.</p>}
        <p class="hint">Court terme = garder chaque titre quelques semaines et renouveler la sélection {p.ctRotation === "semaine" ? "chaque semaine" : "chaque mois"}.
          C'est plus risqué et plus coûteux que le hold : chaque rotation génère des ordres et du change.</p>
      </Card>

      <Card title={`Sélection du moment (${lignes.length} titres)`}>
        <table class="table">
          <thead><tr><th>Titre</th><th>Poids</th><th>Montant</th></tr></thead>
          <tbody>{lignes.map((l, i) => {
            const s = infos.get(l.symbol)!;
            return (
              <tr>
                <td><b>{l.symbol}</b><br /><small class="muted">{s.nom}</small>
                  <div class="mchips"><Chip k="proba_hausse" v={retenus[i].score} label="IA" value={pct(retenus[i].score, 0, false)} />
                    <Chip k="volatility" v={s.volatility} label="Vol" /></div></td>
                <td>{pct(l.poids, 1, false)}</td>
                <td><b>{num(l.poids * capital, 2)} €</b></td>
              </tr>
            );
          })}</tbody>
        </table>
        <p class="hint">Score IA = rang du titre dans le classement (100 % = premier). Poids inversement proportionnels à la volatilité,
          {" "}{pct(Math.max(p.poidsMax, 1 / lignes.length), 0, false)} max par titre.</p>
      </Card>

      <Card title="Coût de la rotation">
        <div class="stats">
          <Stat label="Rotations / an" value={String(rotationsAn)} />
          <Stat label="Coût estimé / an" value={`${num(coutAn, 2)} €`} sub={`${pct(coutAn / capital, 1, false)} du capital`}
            tone={coutAn / capital > 0.03 ? "bad" : coutAn / capital > 0.01 ? "neutral" : "good"} />
        </div>
        <p class="hint">Hypothèse : la moitié du portefeuille change à chaque rotation (ventes + achats, change aller-retour).
          Ce coût doit être battu par le modèle avant tout gain : compare-le à l'avance du top quintile ci-dessus.</p>
      </Card>

      <PlanAchat capital={capital} lignes={lignes} prix={Object.fromEntries((snap.data ?? []).map((x) => [x.symbol, x.close]))}
        eurusd={eurusd} annees={1} mode="court" />
    </>
  );
}
