// Carte « Face aux chocs » : le mois à venir (prévu, testé) et les crises passées rejouées (pas une prévision).
// Méthode : docs/METHODE.md §§ 14 (stress test) et 4.16 / 15 (risque du mois à venir).
import { Card, HelpButton, Info, Verifier } from "../components";
import { dateFr, num, pct } from "../format";
import { rejouerCrises, risqueMois, type Chocs, type LignePoids } from "../chocs";
import type { Univers } from "../optim";

export type UniversJour = Univers & {
  chocs?: Chocs | null; vol_1m?: (number | null)[];
  info_1m?: { vix?: number | null; date?: string; avertissement?: boolean; part_depassements?: number | null;
    reel?: { verdict?: string; n_dates?: number; premier_bilan?: string; couverture_mauvais_cas?: number | null } | null } | null;
};

const duree = (jours: number | null) => {
  if (jours == null) return "pas encore revenu à son sommet";
  const mois = Math.round(jours / 21);
  return mois < 12 ? `revenu au sommet en ${Math.max(1, mois)} mois` : `revenu au sommet en ${num(jours / 252, 1)} ans`;
};

export function FaceAuxChocs({ u, lignes, capital }: { u: UniversJour | undefined; lignes: LignePoids[]; capital: number }) {
  if (!u) return null;
  const crises = rejouerCrises(u.chocs, u.symbols, u.beta, lignes);
  const mois = risqueMois(u, lignes);
  if (!crises.length && !mois) return null;
  const pire = crises[0];
  return (
    <Card title="Face aux chocs" repliable id="chocs" right={<HelpButton keys={["stress_test", "risque_mois", "vix", "max_drawdown"]} intro={<>
      <p><b>Le mois à venir</b> : la volatilité prévue sur 22 séances par HAR-X (le modèle HAR plus le VIX, l'indice de la peur du marché
        des options). C'est le seul gain de prévision prouvé du laboratoire, confirmé sur des titres jamais utilisés (S&P MidCap 400)
        et re-testé chaque mois. Il n'est affiché que si le dernier test est réussi.</p>
      <p><b>Les crises passées</b> : ce que ton portefeuille d'aujourd'hui aurait perdu du sommet au creux du marché, avec les mêmes poids.
        Ce n'est <b>pas une prévision</b> : c'est ce qui s'est réellement passé. Sert à savoir si tu supporterais une telle baisse sans vendre.</p>
    </>} />}>
      {mois && (
        <>
          <h3 class="h3">Le mois à venir <a class="badge-teste" href="#/risque/ia" title="Voir la preuve">testé ✓</a></h3>
          <p>Sur les 22 prochaines séances, une baisse de plus de <b class="down">{pct(mois.mauvaisCas, 1, false)}</b>{" "}
            (<b>{num(capital * mois.mauvaisCas, 0)} €</b>) a environ <b>5 % de chances</b>.
            <Info>Volatilité du portefeuille prévue pour le mois : {pct(mois.volAn, 0, false)} par an, contre {pct(mois.volHabituelle, 0, false)}
              {" "}mesurée sur 3 ans. Mauvais cas calculé avec une loi de Student à 5 degrés (queues épaisses), rendement moyen supposé nul.</Info></p>
          <p class="hint">Risque <b class={mois.rapport > 1.1 ? "down" : mois.rapport < 0.9 ? "up" : ""}>
            {mois.rapport > 1.1 ? "plus élevé" : mois.rapport < 0.9 ? "plus faible" : "proche"}</b> que d'habitude
            (mauvais cas habituel : {pct(mois.mauvaisCasHabituel, 1, false)}){u.info_1m?.vix != null && <> · VIX à <b>{num(u.info_1m.vix, 1)}</b></>}
            {u.info_1m?.date && <> · prévision du {dateFr(u.info_1m.date)}</>}.
            {mois.couverture < 0.999 && <> {pct(1 - mois.couverture, 0, false)} du portefeuille n'a pas de prévision (titre hors de l'univers du jour).</>}</p>
          {u.info_1m?.avertissement && <div class="note warn">Au test, ce mauvais cas a été dépassé {pct(u.info_1m.part_depassements, 1, false)} des
            mois au lieu de 5 % : la baisse réelle peut être plus forte.</div>}
          {u.info_1m?.reel && <p class="hint"><b>En conditions réelles</b> : {u.info_1m.reel.verdict === "en attente"
            ? <>prévisions enregistrées chaque semaine, premier bilan vers le {dateFr(u.info_1m.reel.premier_bilan)}
              ({u.info_1m.reel.n_dates ?? 0} semaine(s) déjà jugée(s)).</>
            : <>{({ "HAR-X meilleur": "meilleure", "HAR-X moins bon": "moins bonne", "pas de différence détectable": "pas de différence détectable avec" } as Record<string, string>)[u.info_1m.reel.verdict ?? ""] ?? u.info_1m.reel.verdict}
              {u.info_1m.reel.verdict === "pas de différence détectable" ? " " : " que "}la même prévision sans le VIX, sur {u.info_1m.reel.n_dates} semaines jugées
              {u.info_1m.reel.couverture_mauvais_cas != null && <> ; mauvais cas dépassé {pct(u.info_1m.reel.couverture_mauvais_cas, 1, false)} des fois</>}.</>}</p>}
          <p class="hint">Rien à faire pour autant : le portefeuille est révisé tous les 6 mois. Ce chiffre sert à ne pas être surpris.</p>
        </>
      )}
      {crises.length > 0 && (
        <>
          <h3 class="h3">Les grandes crises, rejouées sur ton portefeuille</h3>
          <table class="table">
            <thead><tr><th>Crise</th><th>Ton portefeuille</th><th>S&P 500</th></tr></thead>
            <tbody>{crises.map((c) => (
              <tr>
                <td><b>{c.nom}</b><br /><small class="muted">{dateFr(c.debut)} → {dateFr(c.fin)} · {duree(c.retour_jours)}</small></td>
                <td class="nowrap"><b class="down">{pct(c.portefeuille, 0)}</b><br /><small>{num(capital * c.portefeuille, 0)} €</small>
                  {c.partEstimee > 0.005 && <><br /><small class="muted">dont {pct(c.partEstimee, 0, false)} estimé</small></>}</td>
                <td class="nowrap">{pct(c.marche, 0)}</td>
              </tr>
            ))}</tbody>
          </table>
          {pire && <p class="hint">Pire cas rejoué : <b>{pct(pire.portefeuille, 0)}</b> en {pire.nom.slice(0, 4)}, soit {num(-capital * pire.portefeuille, 0)} € de
            moins sur {num(capital, 0)} €. Le marché est {duree(pire.retour_jours)}.</p>}
          <p class="hint">Ce n'est pas une prévision : c'est ce qui s'est passé, rejoué avec les poids d'aujourd'hui, sans vendre pendant la chute.
            « Estimé » : titre absent à l'époque, remplacé par son bêta × la chute du marché. Seuls les titres d'aujourd'hui sont rejoués
            (les faillites de l'époque n'y sont pas) et les dividendes ne sont pas comptés.</p>
          <Verifier href="#/parametres/calculs/chocs" />
        </>
      )}
    </Card>
  );
}
