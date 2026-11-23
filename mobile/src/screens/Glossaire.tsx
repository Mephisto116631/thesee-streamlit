// Glossaire : toutes les notions de l'appli, de A à Z, avec recherche (fiches + indicateurs à seuils).
import { useState } from "preact/hooks";
import { Card } from "../components";
import { chercher, GLOSSAIRE } from "../glossaire";
import { RANGES } from "../ranges";

export function Glossaire() {
  const [q, setQ] = useState("");
  const liste = chercher(q);
  return (
    <div class="screen">
      <header class="screen-head">
        <a class="back" href="#/analyse" aria-label="Retour">‹</a>
        <div class="grow"><h1>Glossaire</h1><p class="sub">{liste.length} notion(s) expliquée(s)</p></div>
      </header>
      <input type="search" style={{ width: "100%", marginBottom: "10px" }} placeholder="Chercher (ex. bêta, VIX, révision)" value={q}
        onInput={(e) => setQ((e.target as HTMLInputElement).value)} aria-label="Chercher dans le glossaire" />
      {liste.map((e) => {
        const f = GLOSSAIRE[e.cle], r = RANGES[e.cle];
        return (
          <Card title={e.titre} repliable ouvert={Boolean(q)} id={`g-${e.cle}`}>
            <p class="hint" style={{ marginTop: 0 }}>{e.categorie}</p>
            {f ? <>
              <p>{f.def}</p>
              <p><b>Comment lire</b> : {f.lecture}</p>
              <p class="muted"><b>Limites</b> : {f.limites}</p>
            </> : r && <>
              <p>{r.definition}</p>
              <ul class="help-zones">{r.zones.map((z) => <li><span class={`badge ${z.ton}`}>{z.nom}</span> {z.aide}</li>)}</ul>
            </>}
          </Card>
        );
      })}
      {!liste.length && <div class="note">Aucune notion ne correspond à « {q} ».</div>}
    </div>
  );
}
