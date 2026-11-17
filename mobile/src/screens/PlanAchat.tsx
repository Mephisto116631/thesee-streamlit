import { useState } from "preact/hooks";
import { Card, Details, Stat } from "../components";
import { num, pct } from "../format";
import { useParametres } from "../settings";
import { coutAnnualise, planAchat, type Reglages } from "../strategy";

// Frais, change, fractions et prix limite : page Paramètres. Ici : seulement l'étalement de l'achat.
const KEY = "thesee:etalement:v1";
const charger = (): Pick<Reglages, "tranches" | "frequence"> => {
  try { return { tranches: 1, frequence: "mois", ...JSON.parse(localStorage.getItem(KEY) ?? "{}") }; } catch { return { tranches: 1, frequence: "mois" }; }
};
const EURUSD_SECOURS = 1.08;

/** Plan d'achat : combien acheter de chaque titre, à quel prix, quand, et ce que coûtent les frais. */
export function PlanAchat({ capital, lignes, prix, eurusd, annees }: {
  capital: number; lignes: { symbol: string; poids: number }[];
  prix: Record<string, number | null | undefined>; eurusd: number | null; annees: number;
}) {
  const params = useParametres();
  const [etal, setEtal] = useState(charger());
  const maj = (p: Partial<Pick<Reglages, "tranches" | "frequence">>) => {
    const n = { ...etal, ...p };
    setEtal(n);
    try { localStorage.setItem(KEY, JSON.stringify(n)); } catch { /* ignore */ }
  };
  const r: Reglages = { ...etal, fraisOrdre: params.fraisOrdre, fraisChange: params.fraisChange, fractions: params.fractions, margeLimite: params.margeLimite };
  const fx = eurusd ?? EURUSD_SECOURS;
  const plan = planAchat(capital, lignes, prix, fx, r);
  const coutAn = coutAnnualise(plan.partFrais, r.fraisChange, annees);
  const t0 = plan.tranches[0];

  return (
    <>
      <Card title="Plan d'achat" class="tint-accent">
        <p class="hint" style={{ marginTop: 0 }}>
          Frais {num(r.fraisOrdre, 2)} € par ordre · change {pct(r.fraisChange, 2, false)} · {r.fractions ? "fractions d'actions" : "actions entières"} ·
          prix limite + {pct(r.margeLimite ?? 0, 1, false)} — <a href="#/parametres">modifier dans Paramètres</a>
        </p>
        <div class="field" style={{ marginTop: 10 }}>Achat en
          <div class="seg full" role="group" aria-label="Nombre de tranches">
            {[1, 2, 4, 6].map((n) => (
              <button class={r.tranches === n ? "on" : ""} onClick={() => maj({ tranches: n })}>{n === 1 ? "1 fois" : `${n} fois`}</button>
            ))}
          </div>
        </div>
        {r.tranches > 1 && (
          <div class="seg full" role="group" aria-label="Fréquence">
            <button class={r.frequence === "semaine" ? "on" : ""} onClick={() => maj({ frequence: "semaine" })}>Chaque semaine</button>
            <button class={r.frequence === "mois" ? "on" : ""} onClick={() => maj({ frequence: "mois" })}>Chaque mois</button>
          </div>
        )}
        <p class="hint">
          {r.tranches === 1
            ? "Achat en une fois : c'est en moyenne le plus rentable, car l'argent est investi plus tôt (le marché monte plus souvent qu'il ne baisse)."
            : `Achat progressif (DCA) : ${num(capital / r.tranches, 2)} € par tranche. Il ne rapporte pas plus en moyenne, mais il évite de tout acheter juste avant une baisse. Il multiplie le nombre d'ordres.`}
        </p>

        {t0 && (
          <>
            <h3 class="h3">{r.tranches > 1 ? `Tranche 1 sur ${r.tranches} — ${t0.date.toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}` : "Ordres à passer"}</h3>
            <table class="table small">
              <thead><tr><th>Titre</th><th>Quantité</th><th>Prix limite</th><th>Montant</th></tr></thead>
              <tbody>{t0.ordres.map((o) => (
                <tr class={o.quantite === 0 ? "muted" : ""}>
                  <td><b>{o.symbol}</b></td>
                  <td>{o.quantite === 0 ? "—" : num(o.quantite, r.fractions ? 4 : 0)}</td>
                  <td>{o.prix ? `${num(o.limite, 2)} $` : "—"}</td>
                  <td>{num(o.montantEur, 2)} €</td>
                </tr>
              ))}</tbody>
            </table>
            {plan.lignesNonAchetees.length > 0 && (
              <div class="note warn">
                {plan.lignesNonAchetees.join(", ")} : une action entière coûte plus que le montant prévu.
                Active les fractions, augmente le capital ou retire la ligne.
              </div>
            )}
            {r.tranches > 1 && (
              <Details summary={`Calendrier des ${r.tranches} tranches`}>
                <ul class="calendrier">
                  {plan.tranches.map((t, i) => (
                    <li><b>{t.date.toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</b>
                      <span class="muted"> — tranche {i + 1} : {num(capital / r.tranches, 2)} €, mêmes proportions</span></li>
                  ))}
                </ul>
                <p class="hint">Les quantités des tranches suivantes sont à recalculer le jour même : les prix auront bougé.</p>
              </Details>
            )}
          </>
        )}
      </Card>

      <Card title="Comment passer les ordres">
        <ol class="etapes">
          <li><b>Type d'ordre : « à cours limité »</b>, au prix limite indiqué (dernier cours + {num((r.margeLimite ?? 0) * 100, 1)} %).
            Tu ne paieras jamais plus que ce prix. S'il n'est pas exécuté dans la journée, relève-le légèrement le lendemain.</li>
          <li><b>Quand : entre 16h00 et 21h30, heure de Paris.</b> Évite la première demi-heure après l'ouverture de Wall Street (15h30)
            et les dernières minutes avant la clôture (22h00) : les prix sautent et l'écart entre prix d'achat et de vente est plus large.
            De mi-mars à fin mars et de fin octobre à début novembre (changements d'heure décalés), Wall Street ouvre à 14h30 : décale d'une heure.</li>
          <li><b>Fractions</b> : beaucoup de courtiers n'acceptent que des ordres « au marché » pour les fractions.
            Dans ce cas, passe-les dans le même créneau calme, jamais à l'ouverture.</li>
          <li><b>Change</b> : les actions US se paient en dollars. Les frais de change s'appliquent à l'achat et de nouveau à la revente.</li>
          <li><b>Ensuite</b> : ne touche plus au portefeuille. Une fois par an, rééquilibre si une ligne dépasse 25 %.</li>
        </ol>
      </Card>

      <Card title="Coût des frais">
        <div class="stats">
          <Stat label="Ordres" value={String(plan.nbOrdres)} sub={`${num(plan.fraisOrdres, 2)} € de frais`} />
          <Stat label="Change" value={`${num(plan.fraisChangeEur, 2)} €`} sub={`taux 1 € = ${num(fx, 4)} $${eurusd ? "" : " (estimé)"}`} />
          <Stat label="Total" value={`${num(plan.totalFrais, 2)} €`} sub={`${pct(plan.partFrais, 2, false)} du capital`}
            tone={plan.partFrais > 0.02 ? "bad" : plan.partFrais > 0.005 ? "neutral" : "good"} />
        </div>
        <p class="hint">
          Sur l'horizon choisi, les frais (entrée + change à la revente) retirent environ <b>{pct(coutAn, 2, false)} par an</b> à la rentabilité.
          {plan.nonInvesti > 0.5 && <> {num(plan.nonInvesti, 2)} € restent non investis (actions entières).</>}
          {plan.partFrais > 0.02 && <> Au-delà de 2 %, réduis le nombre de lignes ou de tranches.</>}
        </p>
      </Card>
    </>
  );
}
