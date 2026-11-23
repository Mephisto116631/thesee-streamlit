import { HelpButton, ReglagesButton } from "../components";

// Espace « Analyse » : tout ce qui sert à comprendre ou à vérifier, mais pas à décider au quotidien.
const ENTREES: { h: string; titre: string; txt: string }[] = [
  { h: "#/guide", titre: "Bien utiliser Thésée", txt: "Ce qu'elle sait faire, ce qu'elle ne sait pas, et comment t'en servir." },
  { h: "#/parametres/calculs", titre: "Vérifier les calculs de mon portefeuille", txt: "Chaque chiffre, formule par formule, avec sa définition et tes valeurs." },
  { h: "#/risque/ia", titre: "Le modèle IA est-il fiable ?", txt: "Ce que prédisent les modèles, leurs tests et les essais du laboratoire." },
  { h: "#/risque", titre: "Le marché est-il nerveux ?", txt: "Volatilité attendue (VIX), crédit, santé financière des entreprises." },
  { h: "#/marche", titre: "Tous les titres suivis", txt: "Par secteur, avec leurs indicateurs ; touche un titre pour sa fiche." },
  { h: "#/glossaire", titre: "Glossaire", txt: "Toutes les notions de l'appli expliquées : bêta, VIX, HAR, révision, stress test…" },
  { h: "#/parametres", titre: "Paramètres", txt: "Toutes les hypothèses, les frais, le courtier, les mises à jour." },
];

export function Analyse() {
  return (
    <div class="screen">
      <header class="screen-head">
        <div><h1>Analyse</h1><p class="sub">Pour vérifier — les réponses sont dans Accueil, Portefeuille et Positions</p></div>
        <HelpButton keys={[]} intro={<p>Le quotidien se passe dans <b>Accueil</b>, <b>Portefeuille</b> et <b>Positions</b>.
          Ici sont rangés les outils d'analyse : marché, crédit, modèles IA et leurs tests, paramètres avancés.</p>} />
        <ReglagesButton />
      </header>
      <nav class="hub">
        {ENTREES.map((x) => (
          <a href={x.h}>
            <span><b>{x.titre}</b><small>{x.txt}</small></span>
            <span class="fl" aria-hidden="true">›</span></a>
        ))}
      </nav>
    </div>
  );
}
