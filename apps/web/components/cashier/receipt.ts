import { payments } from "@/lib/fees/client";

/** Ouvre le reçu PDF existant (`GET /payments/{id}/receipt.pdf`, aucun second système de reçu)
 * dans un nouvel onglet. L'onglet est ouvert AVANT l'appel réseau (geste utilisateur encore
 * actif : pas de blocage de fenêtre surgissante), puis redirigé vers le PDF une fois chargé. */
export async function openReceipt(paymentId: string): Promise<void> {
  const tab = window.open("", "_blank");
  try {
    const url = await payments.getReceiptBlobUrl(paymentId);
    if (tab) tab.location.href = url;
    else window.open(url, "_blank");
  } catch (err) {
    tab?.close();
    throw err;
  }
}
