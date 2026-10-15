import { ApiError } from "@/lib/api/client";

// Messages d'erreur de l'annulation d'un paiement (`POST /payments/{id}/cancel`).
//
// Représentation des erreurs par le client existant (lib/api/client.ts::apiFetch) :
// - réponse HTTP non 2xx -> `ApiError(message, status)` ; `message` = `detail` du corps JSON s'il est
//   exploitable, sinon le repli générique `Request failed with status N` (corps absent, non JSON,
//   ou sans `detail`) — jamais supposé toujours présent ;
// - aucune réponse reçue (coupure réseau) -> `TypeError` de fetch() ou `NetworkError` (refresh).
// Le backend reste l'autorité : ces messages ne font qu'expliquer un refus, ils ne décident de rien.

export const CLOSED_SESSION_FALLBACK = "Annulation impossible : la session de caisse est clôturée.";

// Messages métier connus du backend (fees/service.py::cancel_payment), traduits pour l'écran.
const KNOWN_DETAILS: [string, string][] = [
  [
    "A payment belonging to a closed cash session cannot be cancelled",
    "Annulation impossible : ce paiement appartient à une session de caisse déjà clôturée.",
  ],
  ["Only a completed payment can be cancelled", "Annulation impossible : ce paiement est déjà annulé."],
];

function usableDetail(err: ApiError): string | null {
  const message = err.message.trim();
  if (!message || /^Request failed with status \d+$/.test(message)) return null;
  return message;
}

export function cancelPaymentErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) {
    return "La requête d'annulation n'a pas pu aboutir (problème de connexion). Vérifiez l'état du paiement avant de réessayer.";
  }
  const detail = usableDetail(err);
  const known = detail ? KNOWN_DETAILS.find(([needle]) => detail.includes(needle)) : undefined;
  if (known) return known[1];

  switch (true) {
    case err.status === 409:
      return detail ? `Annulation impossible : ${detail}` : CLOSED_SESSION_FALLBACK;
    case err.status === 401:
      return err.message; // déjà formulé par apiFetch ("Votre session a expiré...")
    case err.status === 403:
      return "Vous n'êtes pas autorisé à annuler ce paiement.";
    case err.status === 404:
      return "Paiement introuvable : il a peut-être été supprimé ou n'appartient pas à cet établissement.";
    case err.status === 422:
      return "Annulation refusée : le motif saisi est invalide (1 à 500 caractères).";
    case err.status === 429:
      return "Trop de tentatives. Patientez une minute avant de réessayer.";
    case err.status >= 500:
      return "Erreur serveur : l'annulation n'a pas été effectuée. Réessayez plus tard.";
    default:
      return "L'annulation n'a pas été effectuée.";
  }
}
