// 2026-11-17 (revue de sécurité) — règle d'un NOUVEAU mot de passe, la même que l'API
// (apps/api/app/core/passwords.py) : 12 à 128 caractères, ni mot de passe très courant, ni un seul
// caractère répété. L'API reste seule juge ; ce module ne fait qu'avertir avant l'envoi et traduire
// ses refus.

export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_LENGTH = 128;

export const PASSWORD_RULE_HINT = `${PASSWORD_MIN_LENGTH} caractères minimum`;

/** Message d'erreur avant l'envoi, ou null si la longueur convient. */
export function passwordLengthProblem(password: string): string | null {
  if (password.length < PASSWORD_MIN_LENGTH) return `Le mot de passe doit contenir au moins ${PASSWORD_MIN_LENGTH} caractères.`;
  if (password.length > PASSWORD_MAX_LENGTH) return `Le mot de passe ne doit pas dépasser ${PASSWORD_MAX_LENGTH} caractères.`;
  return null;
}

/** Refus de l'API traduits ; tout autre message est rendu tel quel. */
export function translatePasswordRefusal(message: string): string {
  if (message.includes("too common")) return "Ce mot de passe est trop courant : choisissez-en un autre, plus personnel.";
  if (message.includes("password must contain")) {
    return `Le mot de passe doit contenir de ${PASSWORD_MIN_LENGTH} à ${PASSWORD_MAX_LENGTH} caractères.`;
  }
  return message;
}
