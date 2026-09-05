import { ApiError } from "@/lib/api/client";

/**
 * Traduit une erreur d'appel API en message compréhensible pour l'assistant de mise en place
 * (Phase 8). Les codes mappés ici (401/403/404/409/5xx) reflètent le comportement réel des
 * endpoints `academics`/`users` existants (ex. IntegrityError -> 409 sur la plupart des routes
 * de création) — voir docs/phases/PHASE_8_IMPLEMENTATION.md pour l'exception connue
 * (`create_academic_term` ne catche pas encore IntegrityError, documentée en Discovered/Deferred).
 */
export function formatWizardError(err: unknown): string {
  if (err instanceof ApiError) {
    switch (err.status) {
      case 401:
        return "Votre session a expiré. Reconnectez-vous pour continuer.";
      case 403:
        return "Vous n'avez pas la permission d'effectuer cette action.";
      case 404:
        return "Cette ressource n'existe plus. Rechargez la page.";
      case 409:
        return "Cet élément existe déjà.";
      default:
        if (err.status >= 500) return "Une erreur serveur est survenue. Réessayez dans un instant.";
        // 422 (validation) et autres 4xx : le détail renvoyé par l'API est déjà lisible.
        return err.message || "Une erreur est survenue.";
    }
  }
  return "Erreur réseau : vérifiez votre connexion et réessayez.";
}

export function isSessionExpired(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}
