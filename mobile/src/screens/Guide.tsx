// « Bien utiliser Thésée » : ce que l'appli sait faire (prouvé), ce qu'elle ne sait pas faire, et comment s'en servir.
// Sources : docs/METHODE.md §§ 5 à 16. À tenir à jour quand une preuve change.
import { Card } from "../components";

export function Guide() {
  return (
    <div class="screen guide">
      <header class="screen-head">
        <a class="back" href="#/analyse" aria-label="Retour">‹</a>
        <div class="grow"><h1>Bien utiliser Thésée</h1><p class="sub">Ce qu'elle sait faire, ce qu'elle ne sait pas, comment s'en servir</p></div>
      </header>

      <Card title="En bref" class="tint-accent">
        <p style={{ marginTop: 0 }}>Thésée suffit pour <b>composer et tenir un portefeuille d'actions américaines diversifié</b>, avec un risque maîtrisé
          et des frais bas. Elle ne suffit pas pour <b>toute</b> ton épargne : elle ne dit ni combien investir, ni comment répartir entre actions,
          épargne et autres pays, et elle ne tient pas compte des impôts ni du dollar. Elle n'a pas prouvé qu'elle fait mieux que l'indice.</p>
      </Card>

      <Card title="Ce qu'elle fait bien" repliable>
        <ul class="liste-guide">
          <li><b>Diversifier</b> parmi les ~500 titres du S&P 500, 20 % au plus par titre, en tenant compte des titres qui baissent ensemble (Markowitz).</li>
          <li><b>Mesurer le risque</b> : l'ordre des titres par l'IA (prouvé, re-testé chaque mois), le niveau par HAR, le risque du mois à venir (confirmé
            sur d'autres titres), les crises rejouées sur ton portefeuille.</li>
          <li><b>Limiter les frais</b> : révision tous les 6 ou 12 mois (au backtest 2006-2026 : environ 34 ordres par an au lieu de 165, et 4 à 7 points
            de rendement net en plus).</li>
          <li><b>Préparer les ordres</b> (Plan d'achat) et <b>te rappeler les révisions</b> (Paramètres).</li>
          <li><b>Se retirer d'elle-même</b> : si un test mensuel échoue, l'appli revient à des méthodes simples et le dit.</li>
        </ul>
      </Card>

      <Card title="Ce qu'elle ne sait pas faire" repliable>
        <ul class="liste-guide">
          <li><b>Prévoir si les cours vont monter ou baisser</b> : aucun modèle testé n'y arrive. La rentabilité affichée est une hypothèse de long terme.</li>
          <li><b>Battre l'indice de façon prouvée</b> : au backtest 2013-2026, le portefeuille conseillé fait jeu égal avec le S&P 500 (écart non prouvé,
            6 % du seuil de preuve). Il est aussi plus concentré (12 lignes au plus).</li>
          <li><b>Te dire combien investir</b>, ni répartir ton épargne entre actions, épargne sûre, obligations ou autres pays : tout ici est en actions américaines.</li>
          <li><b>Compter les impôts et le dollar</b> : les chiffres sont en dollars et avant impôts ; l'euro peut ajouter ou retirer plusieurs points par an.</li>
        </ul>
      </Card>

      <Card title="Comment t'en servir" repliable>
        <ol class="liste-guide">
          <li><b>Avant d'investir</b> : garde une épargne de précaution hors bourse (3 à 6 mois de dépenses). N'investis que l'argent dont tu n'auras pas
            besoin avant <b>5 ans</b> au moins.</li>
          <li><b>Choisis ton risque avec la carte « Face aux chocs »</b> (Portefeuille) : regarde la perte de 2008. Si tu ne la supporterais pas sans vendre,
            passe en « Je limite le risque » avec une limite plus basse.</li>
          <li><b>Adapte le nombre de lignes à ton capital</b> : à 1 € par ordre, 12 lignes coûtent 12 €. En dessous d'environ 2 500 €, réduis le nombre de
            lignes dans les Paramètres pour garder les frais sous 0,5 % (le Plan d'achat affiche ce pourcentage).</li>
          <li><b>Une fois acheté, ne touche à rien</b> entre deux révisions, sauf si une ligne dépasse le seuil de rééquilibrage. Active les rappels.
            Le risque du mois et la part « baisse » servent à ne pas être surpris, <b>pas à vendre</b>.</li>
          <li><b>Enveloppe et impôts</b> : les actions américaines ne vont pas dans un PEA. Sur un compte-titres, plus-values et dividendes sont imposés
            (prélèvement forfaitaire d'environ 30 %), et les dividendes américains subissent une retenue de 15 % si le formulaire W-8BEN est rempli
            chez le courtier. Vérifie les taux de l'année en cours.</li>
          <li><b>Approche prudente</b> : un cœur en fonds indiciel large (ETF Monde ou S&P 500, possible en PEA), et Thésée pour la partie que tu
            veux choisir titre par titre, en comprenant et en maîtrisant son risque.</li>
          <li><b>Regarde l'onglet Risque une fois par mois</b> : il dit si les preuves tiennent toujours. Si l'une tombe, l'appli s'adapte seule.</li>
        </ol>
        <p class="hint">Ce n'est pas un conseil en investissement personnalisé : l'appli ne connaît ni ta situation, ni tes objectifs, ni tes impôts.</p>
      </Card>
    </div>
  );
}
