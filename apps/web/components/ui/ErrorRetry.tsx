"use client";

/** Bandeau d'erreur avec action de reprise — pattern minimal partagé (Phase 25) pour remplacer un
 * état "Chargement..." qui resterait sinon bloqué indéfiniment après un échec réseau/API. */
export function ErrorRetry({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center justify-between gap-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700"
    >
      <span>{message}</span>
      <button
        type="button"
        onClick={onRetry}
        className="shrink-0 rounded border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-800 hover:bg-red-100"
      >
        Réessayer
      </button>
    </div>
  );
}
