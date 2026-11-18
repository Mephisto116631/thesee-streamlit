// Aide au passage d'ordres chez le courtier (Trade Republic n'a pas d'API publique :
// on prépare les ordres, on les copie et on ouvre l'appli du courtier).
import { Capacitor } from "@capacitor/core";
import { AppLauncher } from "@capacitor/app-launcher";
import { num } from "./format";
import type { Ordre } from "./strategy";

export const PAQUET_TRADE_REPUBLIC = "de.traderepublic.app";

/** Prix limite dans la devise choisie (Trade Republic cote les actions US en euros). */
export function limiteDevise(o: Ordre, devise: "EUR" | "USD", eurusd: number): number {
  return devise === "EUR" ? Math.round((o.limite / eurusd) * 100) / 100 : o.limite;
}

export function texteOrdre(o: Ordre, nom: string | undefined, devise: "EUR" | "USD", eurusd: number, fractions: boolean): string {
  const lim = limiteDevise(o, devise, eurusd);
  return `Acheter ${num(o.quantite, fractions ? 4 : 0)} ${o.symbol}${nom ? ` (${nom})` : ""} — limite ${num(lim, 2)} ${devise === "EUR" ? "€" : "$"}`
    + ` — ≈ ${num(o.montantEur, 2)} €`;
}

export async function copier(texte: string): Promise<boolean> {
  try { await navigator.clipboard.writeText(texte); return true; } catch { return false; }
}

/** Ouvre l'appli Trade Republic si elle est installée (Android), sinon le site web. */
export async function ouvrirTradeRepublic() {
  if (Capacitor.isNativePlatform()) {
    try {
      const { value } = await AppLauncher.canOpenUrl({ url: PAQUET_TRADE_REPUBLIC });
      if (value) { await AppLauncher.openUrl({ url: PAQUET_TRADE_REPUBLIC }); return; }
    } catch { /* repli web */ }
  }
  window.open("https://app.traderepublic.com", "_blank");
}
