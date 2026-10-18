import { ApiError } from "@/lib/api/client";

// Refus connus de l'API caisse (apps/api/app/modules/cash/service.py) traduits pour le comptoir.
// Le backend reste l'autorité : un message inconnu est affiché tel quel, jamais masqué.
const KNOWN: [string, string][] = [
  ["A cash session is already open", "Une caisse est déjà ouverte pour vous dans cette école."],
  ["Cash session is closed", "Cette caisse est clôturée : plus aucune opération n'est possible."],
  ["A cash count is required before closing", "Un comptage physique est obligatoire avant la clôture."],
  ["A newer cash count exists", "Un comptage plus récent existe : vérifiez-le avant de clôturer."],
  ["The expected amount changed", "Le solde théorique a changé (nouvelle opération) : vérifiez avant de clôturer."],
  ["A variance reason and note are required", "Un motif et une note sont obligatoires en cas d'écart."],
  ["Outgoing movement exceeds the cash available", "La sortie dépasse les espèces disponibles en caisse."],
  ["An open cash session is required", "Ouvrez votre caisse avant d'encaisser des espèces."],
  [
    "Idempotency key already used for a different cash movement",
    "Cette opération a déjà été envoyée avec d'autres données : vérifiez la liste des mouvements avant de recommencer.",
  ],
  ["Unknown denomination", "Coupure inconnue."],
  ["Duplicate denomination", "Une coupure est saisie deux fois."],
];

export function cashErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Erreur réseau : l'opération n'a pas pu être envoyée. Réessayez.";
  const match = KNOWN.find(([needle]) => err.message.includes(needle));
  if (match) return match[1];
  if (err.status === 403) return "Vous n'êtes pas autorisé à effectuer cette opération.";
  return `L'opération a échoué : ${err.message}`;
}
