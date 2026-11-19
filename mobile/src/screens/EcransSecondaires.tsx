// Écrans sortis du portefeuille lors de la refonte : positions et court terme.
import { Card, HelpButton, ReglagesButton, RefreshButton } from "../components";
import { CourtTerme } from "./CourtTerme";
import { usePortefeuilleCible } from "./Portfolio";
import { Positions } from "./Positions";

export function PositionsEcran() {
  const { lignes } = usePortefeuilleCible();
  return (
    <div class="screen">
      <header class="screen-head">
        <div><h1>Mes positions</h1><p class="sub">Ce que je possède et l'écart avec le portefeuille conseillé</p></div>
        <RefreshButton />
        <ReglagesButton />
      </header>
      <Positions cible={lignes} />
    </div>
  );
}

export function CourtTermeEcran() {
  const { e, ov } = usePortefeuilleCible();
  return (
    <div class="screen">
      <header class="screen-head">
        <div><h1>Court terme</h1><p class="sub">Expérimental · {e.capital} €</p></div>
        <HelpButton keys={[]} intro={<p>Ce mode fait tourner les titres chaque mois selon les scores IA de rendement.
          Ces scores ne sont <b>pas probants</b> (voir Analyse › Modèles IA) : à utiliser comme un essai, avec une petite somme.</p>} />
        <ReglagesButton />
      </header>
      <Card class="edge-bad"><p class="verdict" style={{ margin: 0 }}>Expérimental : les prévisions de rendement n'ont pas passé les tests.
        Le portefeuille <a href="#/portefeuille">Hold</a> reste la base conseillée.</p></Card>
      <CourtTerme capital={e.capital} eurusd={ov.data?.eurusd ?? null} />
    </div>
  );
}
