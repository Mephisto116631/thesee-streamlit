import { HelpButton, ReglagesButton } from "../components";

// Espace « Analyse » : tout ce qui sert à comprendre ou à vérifier, mais pas à décider au quotidien.
const ENTREES: { h: string; ic: string; titre: string; txt: string; exp?: boolean }[] = [
  { h: "#/marche", ic: "📈", titre: "Marché", txt: "Tous les titres suivis, par secteur, avec leurs indicateurs." },
  { h: "#/risque", ic: "🛡", titre: "Crédit et régime de marché", txt: "Spreads de crédit, volatilité attendue (VIX), santé financière des titres." },
  { h: "#/risque/ia", ic: "🧪", titre: "Modèles IA et laboratoire", txt: "Ce que prédisent les modèles, leurs tests honnêtes et les essais en cours." },
  { h: "#/titres", ic: "✍️", titre: "Composer mon portefeuille", txt: "Choisis toi-même tes titres : l'appli calcule les poids." },
  { h: "#/court", ic: "⏱", titre: "Mode court terme", txt: "Rotation mensuelle selon les scores IA de rendement, qui ne sont pas probants.", exp: true },
  { h: "#/parametres/calculs", ic: "🧮", titre: "Fiche de calculs", txt: "Toutes les formules utilisées, avec tes hypothèses." },
  { h: "#/parametres", ic: "⚙", titre: "Paramètres", txt: "Hypothèses, risque du portefeuille, frais, courtier, mises à jour." },
];

export function Analyse() {
  return (
    <div class="screen">
      <header class="screen-head">
        <div><h1>Analyse</h1><p class="sub">Pour comprendre et vérifier — pas besoin au quotidien</p></div>
        <HelpButton keys={[]} intro={<p>Le quotidien se passe dans <b>Accueil</b>, <b>Portefeuille</b> et <b>Positions</b>.
          Ici sont rangés les outils d'analyse : marché, crédit, modèles IA et leurs tests, paramètres avancés.</p>} />
        <ReglagesButton />
      </header>
      <nav class="hub">
        {ENTREES.map((x) => (
          <a href={x.h}><span class="ic" aria-hidden="true">{x.ic}</span>
            <span><b>{x.titre}{x.exp && <span class="badge-exp">expérimental</span>}</b><small>{x.txt}</small></span>
            <span class="fl" aria-hidden="true">›</span></a>
        ))}
      </nav>
    </div>
  );
}
