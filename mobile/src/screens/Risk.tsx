import { useCallback, useState } from "preact/hooks";
import { api, type ModelRun } from "../api";
import { BarreSeuil, textePreuve, Card, ChartBox, cssVar, Details, HelpButton, Loading, OfflineNote, RangeBar, Stat, toneOf, useData, ZoneBadge, RefreshButton } from "../components";
import { corr, dateFr, ilYA, num, pb, pct, signClass } from "../format";
import { Relance } from "./Relance";
import { isIG } from "./Stock";
import { useFiabiliteVol } from "../fiabilite";

export function Risk({ tab, go }: { tab: "credit" | "ia"; go: (h: string) => void }) {
  return (
    <div class="screen">
      <header class="screen-head">
        <div><h1>{tab === "credit" ? "Le marché est-il nerveux ?" : "Les modèles IA sont-ils fiables ?"}</h1></div>
        <RefreshButton />
        <HelpButton keys={tab === "credit" ? ["spread_pct", "z_score"] : []}
          intro={tab === "credit"
            ? <p>Le <b>spread de crédit</b> est le surcoût annuel que paient les entreprises pour emprunter par rapport à l'État américain.
              Il monte quand les investisseurs ont peur. High Yield = entreprises fragiles (notes BB+ et moins) ; Investment Grade = solides (BBB- et plus).</p>
            : <p>Les modèles classent les titres selon leur performance attendue (rendement) ou leur risque à venir. Chacun est testé
              sur des années qu'il n'a jamais vues ; un résultat n'est jugé fiable que s'il dépasse un seuil qui tient compte du hasard.</p>} />
      </header>
      <div class="seg full" role="tablist">
        <button role="tab" aria-selected={tab === "credit"} class={tab === "credit" ? "on" : ""} onClick={() => go("#/risque")}>Marché et crédit</button>
        <button role="tab" aria-selected={tab === "ia"} class={tab === "ia" ? "on" : ""} onClick={() => go("#/risque/ia")}>Modèles IA</button>
      </div>
      {tab === "credit" ? <Credit go={go} /> : <Models />}
    </div>
  );
}

function Credit({ go }: { go: (h: string) => void }) {
  const ov = useData(api.overview);
  const sp = useData(api.spreads);
  const snap = useData(api.snapshot);
  const o = ov.data;

  const cfg = useCallback(() => {
    const hy = (sp.data ?? []).filter((p) => p.serie_id === "BAMLH0A0HYM2");
    const igMap = new Map((sp.data ?? []).filter((p) => p.serie_id === "BAMLC0A0CM").map((p) => [p.date, p.valeur]));
    return {
      type: "line",
      data: {
        labels: hy.map((p) => dateFr(p.date)),
        datasets: [
          { label: "High Yield (%)", data: hy.map((p) => p.valeur), borderColor: cssVar("--down"), borderWidth: 1.5, pointRadius: 0 },
          { label: "Investment Grade (%)", data: hy.map((p) => igMap.get(p.date) ?? NaN), borderColor: cssVar("--info"), borderWidth: 1.5, pointRadius: 0 },
        ],
      },
      options: { plugins: { legend: { position: "bottom" } } },
    };
  }, [sp.data]);

  const z = (snap.data ?? []).filter((s) => s.z_score !== null || s.rating_sp).sort((a, b) => (a.z_score ?? 99) - (b.z_score ?? 99));

  return (
    <>
      <OfflineNote res={ov.res} />
      {o && (<>
        <Card title="Combien coûte d'emprunter pour les entreprises ?">
          <div class="stats">
            <Stat label="High Yield" value={pb(o.hy_spread_bp)} sub={`fourchette 10 ans ${pb(o.hy_min_10y)} – ${pb(o.hy_max_10y)}`} />
            <Stat label="Investment Grade" value={pb(o.ig_spread_bp)} sub={`fourchette 10 ans ${pb(o.ig_min_10y)} – ${pb(o.ig_max_10y)}`} />
          </div>
          <RangeBar k="spread_pct" v={o.hy_pct_10y} median={50} medianLabel="médiane 10 ans" />
          <p class="hint">Le curseur place le spread High Yield d'aujourd'hui parmi les 10 dernières années : à {Math.round(o.hy_pct_10y ?? 0)} %,
            il est plus élevé que {Math.round(o.hy_pct_10y ?? 0)} % des jours. Au-dessus de 75 %, le crédit est tendu ; sous 25 %, il est détendu.</p>
        </Card>
        <Card title="Volatilité attendue (VIX)">
          <RangeBar k="vix" v={o.vix} />
          <p class="hint">Le VIX est la volatilité annuelle que le marché des options anticipe pour le S&P 500 sur le prochain mois
            (« indice de la peur »). Sous 15 % : calme ; au-dessus de 25 % : stress.</p>
        </Card>
      </>)}
      <Card title="Comment le crédit a-t-il évolué sur 3 ans ?" repliable ouvert={false}>
        {sp.loading && !sp.data?.length ? <Loading /> : sp.data?.length ? <ChartBox config={cfg} height={230} label="Spreads de crédit High Yield et Investment Grade sur 3 ans" /> : <p class="hint">Pas de données FRED (clé FRED_API_KEY absente du cron ?).</p>}
      </Card>
      <Card title="Quelles entreprises sont fragiles ?" repliable ouvert={false}>
        {!z.length ? <p class="hint">Aucun Z-Score publié.</p> : (
          <table class="table">
            <thead><tr><th>Titre</th><th>Z-Score</th><th>Note S&P</th></tr></thead>
            <tbody>{z.map((s) => (
              <tr onClick={() => go(`#/titre/${s.symbol}`)} class="clickable">
                <td><b>{s.symbol}</b></td>
                <td>{num(s.z_score, 2)} <ZoneBadge k="z_score" v={s.z_score} /></td>
                <td>{s.rating_sp ?? "—"} {s.rating_sp && <small class={isIG(s.rating_sp) ? "up" : "down"}>{isIG(s.rating_sp) ? "IG" : "HY"}</small>}</td>
              </tr>
            ))}</tbody>
          </table>
        )}
        <p class="hint">Le Z-Score d'Altman combine 5 ratios du bilan pour estimer le risque de faillite : au-dessus de 2,99 sain,
          de 1,81 à 2,99 zone grise, sous 1,81 détresse. Peu pertinent pour les banques (JPM, V, MA).</p>
      </Card>
    </>
  );
}

type Choix = "court" | "6m" | "1a";
const CHOIX: { k: Choix; label: string }[] = [
  { k: "6m", label: "6 mois" }, { k: "1a", label: "1 an" }, { k: "court", label: "1 mois" },
];

function Models() {
  const models = useData(api.models);
  const [choix, setChoix] = useState<Choix>("6m");
  const mh = models.data?.find((x) => x.kind === `horizon_${choix}`);
  return (
    <>
      <OfflineNote res={models.res} />
      <FiabiliteRisque />
      <ExamenApprofondi />
      <h2 class="h3">Prévoir le rendement : en test</h2>
      <p class="hint" style={{ marginTop: 0 }}>Ces classements par rendement futur restent au laboratoire : aucun n'a passé le test,
        ils ne servent à aucune décision dans l'appli (Accueil, Portefeuille, Positions, Marché).</p>
      <div class="chips wrap" role="group" aria-label="Horizon du modèle">
        {CHOIX.map((c) => <button class={`chip ${choix === c.k ? "on" : ""}`} onClick={() => setChoix(c.k)}>{c.label}</button>)}
      </div>
      {models.loading && !mh ? <Loading /> : !mh ? (
        <div class="note">Modèle {CHOIX.find((c) => c.k === choix)?.label} pas encore entraîné : relance le calcul ci-dessous.</div>
      ) : <HorizonView m={mh} />}
      <Laboratoire />
      <Card title="Relancer">
        <Relance />
      </Card>
    </>
  );
}

/** La seule prévision utilisée pour décider : son dernier test et son bilan en conditions réelles. */
function FiabiliteRisque() {
  const f = useFiabiliteVol();
  if (f.loading && !f.connu) return <Loading />;
  const r = f.reel;
  return (
    <Card title="Le modèle de risque est-il toujours fiable ?" class={`edge-${f.probant ? "good" : "bad"}`} id="fiabilite">
      <p class="verdict" style={{ marginTop: 0 }}>
        <span class={`badge ${f.probant ? "good" : "bad"}`}>{f.probant ? "Probant" : f.connu ? "Non probant" : "Pas encore testé"}</span>{" "}
        {f.probant ? "La volatilité prévue sur 6 mois est affichée dans l'appli et peut servir au portefeuille."
          : "La volatilité prévue n'est affichée nulle part : l'appli utilise la volatilité des 3 dernières années."}</p>
      {f.connu && (
        <>
          <h3 class="h3">Dernier test ({dateFr(f.date)})</h3>
          <div class="stats">
            <Stat label="IA" value={corr(f.ic)} sub="lien avec le risque réel (IC)" tone={f.probant ? "good" : ""} />
            <Stat label="Référence" value={corr(f.icBase)} sub="volatilité des 3 derniers mois" />
            <Stat label="IA meilleure" value={pct(f.part, 0, false)} sub="des dates testées" />
          </div>
          <BarreSeuil t={f.t} seuil={f.seuil} />
          <p class="hint">Test sur 2013-2026, sur des années que le modèle n'a jamais vues. L'IC (Information Coefficient) mesure, de 0 à 100 %,
            si les titres prévus agités l'ont vraiment été. L'IA doit battre nettement la référence : sa force de preuve est
            de <b>{textePreuve(f.t, f.seuil)} du seuil</b> (100 % = probant ; seuil relevé pour chaque essai fait, afin que le hasard ne passe pas).
            <small class="muted"> t = {num(f.t, 1)}, seuil {num(f.seuil, 1)}.</small></p>
        </>
      )}
      <h3 class="h3">En conditions réelles</h3>
      {r && r.n_dates > 0 ? (
        <>
          <p class="verdict"><span class={`badge ${r.verdict === "probant" ? "good" : r.verdict === "non probant" ? "bad" : "neutral"}`}>{r.verdict}</span>{" "}
            {r.n_dates} prévisions hebdomadaires jugées 6 mois plus tard (jusqu'au {dateFr(r.derniere_date_jugee)}).</p>
          <div class="stats">
            <Stat label="IA" value={corr(r.ic_ia)} sub="IC réel" />
            <Stat label="Référence" value={corr(r.ic_reference)} sub="IC réel" />
            <Stat label="IA meilleure" value={pct(r.part_dates_gagnantes, 0, false)} sub="des semaines" />
          </div>
          <BarreSeuil t={r.t_stat} seuil={r.seuil} />
        </>
      ) : (
        <p class="hint" style={{ marginTop: 0 }}>{r?.premiere_prevision
          ? <>Prévisions enregistrées chaque semaine depuis le {dateFr(r.premiere_prevision)}. Premier bilan possible le <b>{dateFr(r.premier_bilan)}</b>
            {" "}(il faut attendre 6 mois pour connaître le risque réel).</>
          : "Le suivi commence à la prochaine synchronisation : la prévision de chaque titre sera enregistrée chaque semaine, puis comparée 6 mois plus tard au risque réellement observé."}</p>
      )}
      <p class="hint">Prochain re-test automatique : <b>{dateFr(f.prochainTest.toISOString())}</b>. Si le modèle cesse d'être probant,
        l'appli le retire d'elle-même.</p>
    </Card>
  );
}

/** Examen approfondi : épreuves plus dures que le test habituel (règles fixées avant les tests). */
function ExamenApprofondi() {
  const r = useData(api.examen);
  const par = new Map((r.data ?? []).map((x) => [x.nom, x]));
  if (!par.size) return null;
  const ligne = (nom: string, titre: string, ton: (v: string, d: any) => string, detail: (d: any) => any) => {
    const x = par.get(nom);
    if (!x) return null;
    return (
      <li class="ligne-labo">
        <div class="tete"><b>{titre}</b><span class={`badge ${ton(x.verdict, x.diagnostics)}`}>{x.verdict}</span></div>
        <p class="hint" style={{ marginTop: 4 }}>{detail(x.diagnostics ?? {})}</p>
      </li>
    );
  };
  const q = (v: number | undefined) => (v == null ? "—" : num(v, 3));
  return (
    <Card title="Examen approfondi" repliable ouvert={false} id="examen">
      <p class="hint" style={{ marginTop: 0 }}>Des épreuves plus dures que le test habituel, avec des règles de décision fixées
        avant de lancer les essais (journal : docs/METHODE.md).</p>
      <ul class="liste-labo">
        {ligne("examen_references", "Contre les méthodes reconnues", (v) => (v.startsWith("l'IA") ? "good" : "bad"), (d) => <>
          Perte QLIKE (plus bas = mieux) : IA {q(d.qlike?.ia)} · EWMA {q(d.qlike?.ewma)} · GARCH {q(d.qlike?.garch)} · HAR {q(d.qlike?.har)} ·
          volatilité 3 mois {q(d.qlike?.vol_3m)}. Contre la meilleure ({String(d.meilleure_reference ?? "").toUpperCase()}) :
          force de la preuve <b>{pct(d.dm?.[d.meilleure_reference]?.force, 0, false)}</b> du seuil.</>)}
        {ligne("examen_hybride", "Hybride : ordre par l'IA, niveau par HAR", (v) => (v === "publié" ? "good" : "neutral"), (d) => <>
          QLIKE : hybride {q(d.qlike?.hybride)} · HAR {q(d.qlike?.har)} · IA {q(d.qlike?.ia)}. IC : hybride {pct(d.ic?.hybride, 1, false)} contre
          {" "}{pct(d.ic?.vol_3m, 1, false)} pour la volatilité 3 mois (force de la preuve {pct(d.force_ic, 0, false)} du seuil).
          {d.publie ? " Publié : c'est la prévision utilisée dans l'appli." : " Non retenu : l'appli utilise HAR seul."}</>)}
        {ligne("examen_harx_1m", "Risque du mois à venir (HAR + VIX), confirmé ailleurs ?", (v) => (v === "confirmé" ? "good" : "neutral"), (d) => {
          const m = d.midcaps?.horizons?.["22"], s = d.sp500_reproduction?.horizons?.["22"];
          return <>Sur {d.midcaps?.n_titres ?? "—"} titres jamais utilisés (S&P MidCap 400) : perte QLIKE {q(m?.qlike?.harx)} avec le VIX contre {q(m?.qlike?.har)}
            {" "}sans (t = {num(m?.dm?.t, 2)}, doit être ≤ −2) ; VIX décalé d'un an (placebo) : t = {num(m?.placebo?.t, 2)}.
            {" "}S&P 500 : t = {num(s?.dm?.t, 2)}. Mauvais cas 5 % dépassé {pct(d.midcaps?.couverture?.harx?.part_depassements, 1, false)} des mois.
            {d.decision === "confirme" ? " Affiché dans Portefeuille › Face aux chocs." : " Non affiché."}</>;
        })}
        {ligne("examen_marge", "Marge de sécurité et rythme de révision", (v) => (v.startsWith("limite tenue") ? "good" : "neutral"), (d) => {
          const m = d.marges?.["15"], r1 = d.rythmes?.sharpe_max_1m, r6 = d.rythmes?.sharpe_max_6m;
          return <>Limite 15 % : marge {num(m?.marge_actuelle, 2)}, tenue {pct(m?.part_respectee_avec_marge, 0, false)} des semestres
            (sans marge : {pct(m?.part_respectee_sans_marge, 0, false)}). Révision tous les 6 mois : {num(r6?.ordres_par_an, 0)} ordres/an,
            {" "}{pct(r6?.rendement_net, 1, false)}/an net, contre {num(r1?.ordres_par_an, 0)} ordres et {pct(r1?.rendement_net, 1, false)} chaque mois.</>;
        })}
        {ligne("examen_calibration", "Le niveau prévu est-il juste ?", (v) => (v === "calibrée" ? "good" : "neutral"), (d) => <>
          Écart médian prévu / réel : IA {pct(d.ia?.biais_median, 0)} ; HAR {pct(d.har?.biais_median, 0)} ; volatilité 3 mois {pct(d.vol_3m?.biais_median, 0)}.</>)}
        {ligne("examen_crises", "Pendant les crises", () => "neutral", (d) => <>
          {Object.entries(d.crises ?? {}).map(([k, v]: [string, any]) => `${k} : ${v.gain_qlike > 0 ? "IA meilleure" : "IA moins bonne"}`).join(" · ")}
          {d.hors_crises && <> · hors crises : IA meilleure {pct(d.hors_crises.part_dates_gagnantes, 0, false)} des dates</>}</>)}
        {ligne("examen_placebo", "Contrôle anti-fuite (placebo)", (v) => (v === "réussi" ? "good" : "bad"), (d) => <>
          Cible mélangée{d.ic_tirages ? ` (moyenne de ${d.ic_tirages.length} tirages)` : ""} : IC {pct(d.ic_cible_melangee, 1)} (doit être ≈ 0) · fuite volontaire : IC {pct(d.ic_fuite_volontaire, 0)} (doit exploser) ·
          facteur aléatoire classé {d.importance_rang_facteur_aleatoire}ᵉ sur {d.n_facteurs}.</>)}
        {ligne("examen_sensibilite", "Selon les réglages du modèle", (v) => (v.startsWith("réussi") ? "good" : "neutral"), (d) => <>
          Gain d'IC sur la référence : {Object.entries(d).map(([k, v]: [string, any]) => `${k} ${pct(v.gain, 1)}`).join(" · ")}.</>)}
        {ligne("examen_midcap", "Sur un autre marché (S&P MidCap 400)", (v) => (v === "même résultat" ? "good" : "neutral"), (d) => <>
          IC de l'IA {pct(d.ic_ia, 1)} contre {pct(d.ic_ref, 1)} pour la volatilité 3 mois, sur {d.n_titres} titres jamais vus.</>)}
        {ligne("examen_backtest_reel", "Portefeuille avec frais réels", (_, d) => ((d.pbo?.pbo ?? 1) < 0.5 ? "good" : "bad"), (d) => {
          const s = d.reel?.sharpe_max_ia, r15 = d.reel?.risque_15_ia, c = d.couverture?.ia;
          return <>Conseillé (IA) : {pct(s?.rendement_net, 1, false)}/an net de frais ({pct(s?.rendement_brut, 1, false)} brut),
            {" "}{num(s?.ordres_par_an, 0)} ordres par an. « Risque max 15 % » dépassé {pct(r15?.part_semestres_au_dessus, 0, false)} des semestres.
            Fourchette « mauvais cas 5 % » touchée {pct(c?.part_sous_mauvais_cas, 0, false)} des fois. Probabilité de sur-ajustement (PBO) :
            {" "}{pct(d.pbo?.pbo, 0, false)}.</>;
        })}
      </ul>
    </Card>
  );
}

const VERDICT_H: Record<string, { ton: string; nom: string; txt: string }> = {
  signal: { ton: "good", nom: "Signal", txt: "Le classement utilisé a été nettement et régulièrement lié aux performances réelles en test." },
  bruit: { ton: "neutral", nom: "Faible", txt: "Léger lien avec la réalité, pas assez net pour être fiable : à prendre comme un indice, pas une décision." },
  aucun: { ton: "bad", nom: "Aucun avantage", txt: "Pas de lien mesurable entre le classement et les performances réelles : ne pas s'en servir." },
};

const LIBELLES_CONFIG: Record<string, string> = {
  cnn: "CNN", ensemble: "Ensemble", xgb_prudent: "XGB prudent", xgb_standard: "XGB standard", xgb_riche: "XGB riche", lineaire: "Linéaire",
};
// Sens de lecture des facteurs surveillés : [valeur élevée, valeur faible]
const SENS: Record<string, [string, string, string]> = {
  vol_3m: ["Volatilité 3 mois", "les plus volatils", "les plus calmes"],
  vol_idio: ["Volatilité propre (hors marché)", "les plus agités", "les plus réguliers"],
  liquidite: ["Taille (montants échangés)", "les plus grandes valeurs", "les plus petites valeurs"],
  beta_1a: ["Bêta (sensibilité au marché)", "les plus sensibles au marché", "les moins sensibles"],
  max_1m: ["Effet « loterie »", "ceux qui ont fait un gros bond d'un jour", "ceux sans gros bond"],
};
const sens = (f: string, x: number | null | undefined, seuil: number) =>
  x == null || Math.abs(x) < seuil ? "ni l'un ni l'autre" : x > 0 ? SENS[f][1] : SENS[f][2];

const SOURCES: Record<string, string> = {
  modele: "modèle IA (XGBoost, « eXtreme Gradient Boosting » : une suite d'arbres de décision qui corrigent chacun les erreurs des précédents)",
  momentum: "momentum 12-1 mois (ce qui a le plus monté sur un an, hors dernier mois)",
  multifacteurs: "score multi-facteurs (momentum + faible volatilité + proximité du plus haut 1 an)",
};

/** Modèle « horizon » : classement relatif des titres, évalué par l'IC. */
function HorizonView({ m }: { m: ModelRun }) {
  const d = m.diagnostics ?? {};
  const v = VERDICT_H[m.verdict] ?? VERDICT_H.aucun;
  const imp = m.importance ?? [];
  const maxImp = Math.max(1e-9, ...imp.map((x) => x.importance));
  const totImp = Math.max(1e-9, imp.reduce((a, x) => a + x.importance, 0));
  const q: number[] = d.rendement_par_quintile ?? [];
  const maxQ = Math.max(1e-9, ...q.map((x) => Math.abs(x ?? 0)));
  return (
    <>
      <Card title="Le modèle est-il fiable ?" class={`edge-${v.ton}`} right={<small class="muted">entraîné {ilYA(m.trained_at)}</small>}>
        <p class="verdict"><span class={`badge ${v.ton}`}>{v.nom}</span> {v.txt}</p>
        <div class="note">Classement utilisé : <b>{SOURCES[d.source as string] ?? "modèle IA"}</b>.
          {d.source !== "modele" && " Le modèle IA (XGBoost) a fait moins bien en test : il reste entraîné à chaque calcul et reprendra la main s'il devient meilleur."}
          {d.debut_test && <> Testé depuis {dateFr(d.debut_test)} (données depuis {dateFr(d.debut_donnees)}) : environ {num(d.n_effectif, 0)} périodes indépendantes.</>}
          {d.seuil_t != null && <> « Signal » exige une force de preuve d'au moins 100 % du seuil (seuil relevé : peu de périodes et meilleur de 3 classements ;
            <small class="muted"> t &gt; {num(d.seuil_t, 1)}</small>).</>}
          <BarreSeuil t={d.source === "momentum" ? d.t_momentum : d.source === "multifacteurs" ? d.t_multifacteurs : d.t_stat} seuil={d.seuil_t} />
          {d.config_libelle && <> Réglage du modèle IA : {d.config_libelle}, choisi sur le passé uniquement.</>}</div>
        <div class="stats">
          <Stat label="IC modèle IA" value={corr(d.ic_moyen)} sub={<>preuve {textePreuve(d.t_stat, d.seuil_t)} du seuil<small class="muted"> · t {num(d.t_stat, 1)}</small></>} tone={d.source === "modele" ? v.ton : "neutral"} />
          <Stat label="IC momentum" value={corr(d.ic_momentum)} sub={<>preuve {textePreuve(d.t_momentum, d.seuil_t)} du seuil<small class="muted"> · t {num(d.t_momentum, 1)}</small></>} tone={d.source === "momentum" ? v.ton : "neutral"} />
          <Stat label="IC multi-facteurs" value={corr(d.ic_multifacteurs)} sub={<>preuve {textePreuve(d.t_multifacteurs, d.seuil_t)} du seuil<small class="muted"> · t {num(d.t_multifacteurs, 1)}</small></>} tone={d.source === "multifacteurs" ? v.ton : "neutral"} />
        </div>
        <p class="hint">L'<b>IC</b> (« Information Coefficient », coefficient d'information) mesure, date par date, si les titres classés en tête ont réellement fait mieux
          que les autres sur les {d.horizon_jours} jours de bourse suivants (corrélation de rang, de −100 % à +100 %). En gestion, un IC de 5 % stable est déjà bon.
          Le <b>t</b> (statistique de Student) dit si l'IC moyen se distingue du hasard : plus il est grand, moins le résultat
          peut être un coup de chance.</p>
      </Card>

      {q.length === 5 && (
        <Card title="Les titres les mieux classés ont-ils fait mieux ?" repliable ouvert={false} id="quintiles">
          <ul class="imp">{q.map((x, i) => (
            <li><span>{["Q1 (les moins bien classés)", "Q2", "Q3", "Q4", "Q5 (les mieux classés)"][i]}</span>
              <div class="qbar"><div class={x >= 0 ? "pos" : "neg"} style={{ width: `${(Math.abs(x) / maxQ) * 50}%`, [x >= 0 ? "left" : "right"]: "50%" }} /></div>
              <b class={signClass(x)}>{pct(x, 1)}</b></li>
          ))}</ul>
          <p class="hint">Rendement moyen par rapport à la médiane, sur {d.horizon_jours} jours de bourse, en période de test.
            Écart Q5 − Q1 : <b>{pct(d.spread_quintiles, 1)}</b>. Les titres du top quintile ont battu la médiane
            {d.taux_reussite_top != null && <> dans <b>{pct(d.taux_reussite_top, 0, false)}</b> des cas</>}.</p>
        </Card>
      )}

      <Card title="Ce qui compte pour le modèle" repliable ouvert={false}>
        <ul class="imp">{imp.map((x) => (
          <li><span>{x.label}</span><div class="wbar"><div style={{ width: `${(x.importance / maxImp) * 100}%` }} /></div><b class="imp-val">{pct(x.importance / totImp, 0, false)}</b></li>
        ))}</ul>
      </Card>

      {d.controles && (
        <Card title="Contrôles anti-biais" repliable ouvert={false}>
          <table class="table small">
            <thead><tr><th>Facteur</th><th>Le modèle favorise</th><th>En réalité, ont fait mieux</th></tr></thead>
            <tbody>{Object.keys(SENS).filter((f) => d.controles.facteurs?.[f]).map((f) => {
              const c = d.controles.facteurs[f];
              return <tr><td>{SENS[f][0]}</td>
                <td>{sens(f, c.modele, 0.05)} <small class="muted">({corr(c.modele, 0)})</small></td>
                <td>{sens(f, c.realite, 0.01)} <small class="muted">(IC {corr(c.realite)})</small></td></tr>;
            })}</tbody>
          </table>
          <div class="stats">
            <Stat label="IC chez les grandes valeurs" value={corr(d.controles.ic_grandes)} tone={(d.controles.ic_grandes ?? 0) > 0.02 ? "good" : "neutral"} />
            <Stat label="IC chez les petites valeurs" value={corr(d.controles.ic_petites)} tone="neutral" />
          </div>
          <p class="hint">Les cours des entreprises disparues (faillites) manquent : ce sont surtout des petites valeurs très volatiles.
            Si le modèle favorise les titres <b>petits et volatils</b> et ne marche que chez les petites valeurs, son résultat est suspect.
            S'il marche aussi chez les <b>grandes valeurs</b> (moitié la plus échangée, rarement disparue par faillite), il est plus crédible.
            Colonne « modèle » : corrélation entre le score et le facteur (de −100 % à +100 %).</p>
        </Card>
      )}

      <Card>
        <Details summary="Détails de l'évaluation">
          <table class="table small">
            <thead><tr><th>Période de test</th><th>IC</th><th>Dates</th><th>Réglage</th></tr></thead>
            <tbody>{(d.fenetres ?? []).map((f: any) => <tr><td>{dateFr(f.debut)} → {dateFr(f.fin)}</td><td class={signClass(f.ic)}>{corr(f.ic)}</td><td>{f.n_dates}</td><td class="muted">{LIBELLES_CONFIG[f.config] ?? "—"}</td></tr>)}</tbody>
          </table>
          <p class="hint">Validation « walk-forward » : le modèle est entraîné sur le passé puis testé sur la période suivante,
            avec un écart de {d.horizon_jours} jours de bourse entre les deux pour qu'il ne voie jamais le futur. {d.n_dates_test} dates testées,
            soit environ {num(d.n_effectif, 0)} observations indépendantes (les périodes de {d.horizon_jours} jours de bourse se chevauchent).
            {d.composition_historique
              ? <> À chaque date, seuls les titres réellement dans le S&P 500 (« Standard & Poor's 500 », les 500 grandes entreprises américaines) ce jour-là sont pris en compte (~{num(d.titres_par_date, 0)} par date). Les titres disparus depuis (faillites, rachats) n'ont plus de cours chez Yahoo : les résultats restent un peu optimistes.</>
              : <> Univers = composition actuelle de l'indice : les titres disparus ou entrés depuis faussent le test (biais du survivant), les résultats sont donc optimistes.</>}</p>
        </Details>
      </Card>
    </>
  );
}

const NOMS_LABO: Record<string, string> = {
  reference: "Modèle publié", alpha: "Sans effet marché (alpha)", alpha_secteur: "Alpha par secteur",
  alpha_secteur_sans_taille: "Alpha par secteur, sans la taille", fondamentaux: "Cours + comptes des entreprises",
  fondamentaux_seuls: "Comptes des entreprises seuls", risque_volatilite: "IA de risque : volatilité",
  risque_perte_max: "IA de risque : perte maximale", backtest_volatilite_sharpe_max: "Portefeuille avec la volatilité IA",
  backtest_volatilite_variance_min: "Portefeuille le plus calme avec la volatilité IA",
  risque_perte_max_comptes: "IA de risque : perte maximale + comptes", risque_volatilite_comptes: "IA de risque : volatilité + comptes",
  ensemble: "Ensemble XGBoost + linéaire (cours + comptes)", cnn: "CNN sur la forme des courbes",
  regime_logistique: "Baisse du marché > 10 % en 6 mois (logistique)", regime_xgboost: "Baisse du marché > 10 % en 6 mois (XGBoost)",
};

/** Laboratoire : variantes du modèle essayées sans toucher aux scores publiés (experiences.py). */
function Laboratoire() {
  const ex = useData(api.experiences);
  const lignes = ex.data ?? [];
  if (!lignes.length) return null;
  // Dernier résultat de chaque variante × horizon (les lots peuvent ne relancer qu'une partie des essais)
  const vus = new Set<string>();
  const lot = lignes.filter((e) => { const k = `${e.nom}|${e.horizon}`; if (vus.has(k)) return false; vus.add(k); return true; }).reverse();
  const n = Math.max(...lot.filter((e) => !e.nom.startsWith("risque") && !e.nom.startsWith("backtest")).map((e) => e.n_essais ?? 0), 0);
  const hz = (h: string) => (h === "1a" ? "1 an" : h === "6m" ? "6 mois" : h === "1m" ? "chaque mois" : h);
  return (
    <Card title="Laboratoire : les essais" repliable ouvert={false} id="labo">
      {lot.map((e) => (
        <div class="ligne-labo">
          <div class="tete"><b>{NOMS_LABO[e.nom] ?? e.nom}</b>
            {e.verdict === "probant" ? <span class="badge good">probant</span> : <small class="muted">{hz(e.horizon)}</small>}</div>
          <div class="chiffres">
            {e.nom.startsWith("backtest")
              ? <span>Risque réel <b class={signClass(-(e.ic ?? 0))}>{e.ic != null && e.ic > 0 ? "+" : ""}{pct(e.ic, 1, false)}</b> vs méthode actuelle</span>
              : e.nom.startsWith("regime")
                ? <span>AUC <b>{corr(e.ic, 0)}</b> (50 % = hasard)</span>
                : <span>IC <b class={signClass(e.ic)}>{corr(e.ic)}</b>{e.ic_base != null && <> (réf. {corr(e.ic_base)})</>}</span>}
            {e.regimes?.hausse && <span>marché en hausse {corr(e.regimes.hausse.ic)} · en baisse {corr(e.regimes?.baisse?.ic)}</span>}
            {e.verdict === "probant" && <span>{hz(e.horizon)}</span>}
          </div>
          <BarreSeuil t={e.t_stat} seuil={e.seuil_t_global} />
        </div>
      ))}
      <p class="hint">Variantes testées à part : les scores publiés ne changent pas. La barre montre le résultat par rapport au seuil exigé
        (trait vertical) ; ce seuil monte avec le nombre d'essais ({n} pour le rendement), sinon le hasard finit par faire gagner une variante.
        « Alpha » = ce qui reste une fois l'effet du marché retiré. « IA de risque » doit battre la référence, la volatilité des 3 derniers mois.</p>
    </Card>
  );
}
