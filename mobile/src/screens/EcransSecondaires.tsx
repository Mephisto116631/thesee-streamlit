// Écran sorti du portefeuille lors de la refonte : positions.
import { ReglagesButton, RefreshButton } from "../components";
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
