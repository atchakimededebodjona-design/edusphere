// Phase 32, lot 1 — signal « d'où viennent les données affichées », émis par lib/api/client.ts et
// écouté par components/pwa/PwaSupport.tsx. Un simple événement de fenêtre : aucun état global.

export const DATA_SOURCE_EVENT = "edulinkage:data-source";

export type DataSourceDetail =
  // Réponse de l'API reçue : le serveur est joignable.
  | { source: "network" }
  // API injoignable : copie gardée sur l'appareil, datée.
  | { source: "copy"; savedAt: string }
  // API injoignable et aucune copie pour cette lecture.
  | { source: "unreachable" };

export function announceDataSource(detail: DataSourceDetail): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<DataSourceDetail>(DATA_SOURCE_EVENT, { detail }));
}

/** Faux uniquement quand le navigateur sait l'appareil hors ligne (vrai ne garantit pas internet :
 * wifi sans internet, forfait épuisé…). */
export function browserSaysOnline(): boolean {
  return typeof navigator === "undefined" || navigator.onLine !== false;
}

export const OFFLINE_NOT_SENT_MESSAGE =
  "Hors connexion : rien n'a été envoyé. Réessayez quand internet sera revenu.";

export const OFFLINE_NO_COPY_MESSAGE =
  "Hors connexion : ces informations n'ont pas encore été ouvertes avec internet sur cet appareil.";
