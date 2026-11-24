"use client";

/** Bandeau d'erreur avec action de reprise — pattern minimal partagé (Phase 25) pour remplacer un
 * état "Chargement..." qui resterait sinon bloqué indéfiniment après un échec réseau/API.
 * Refonte, phase 2 (2026-11-23) : présentation alignée sur les alertes communes (components/ui). */
export function ErrorRetry({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
    >
      <span className="min-w-0">{message}</span>
      <button
        type="button"
        onClick={onRetry}
        className="min-h-9 shrink-0 rounded-lg border border-red-300 bg-white px-3 text-sm font-medium text-red-800 hover:bg-red-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-red-700"
      >
        Réessayer
      </button>
    </div>
  );
}
