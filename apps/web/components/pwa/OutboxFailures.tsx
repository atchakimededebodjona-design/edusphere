"use client";

import { useState } from "react";
import { removeOutboxEntry, type OutboxEntry } from "@/lib/offline/outbox";
import { retryOutboxEntry } from "@/lib/offline/sync";
import { useOutbox } from "@/lib/offline/useOutbox";

// Phase 32, lot 2 — saisies faites hors connexion puis REFUSÉES par le serveur à l'envoi (séance
// verrouillée, bulletin déjà publié, élève retiré de la classe…). Jamais supprimées en silence :
// l'enseignant voit la raison et choisit de réessayer ou de supprimer.
export function OutboxFailures({ kind }: { kind: OutboxEntry["kind"] }) {
  const failed = useOutbox().filter((entry) => entry.kind === kind && entry.state === "failed");
  const [busyId, setBusyId] = useState<string | null>(null);

  if (failed.length === 0) return null;

  async function retry(entry: OutboxEntry) {
    setBusyId(entry.id);
    try {
      await retryOutboxEntry(entry);
    } finally {
      setBusyId(null);
    }
  }

  async function remove(entry: OutboxEntry) {
    if (!window.confirm(`Supprimer définitivement « ${entry.label} » de cet appareil ? Cette saisie ne sera jamais envoyée.`)) return;
    await removeOutboxEntry(entry);
  }

  return (
    <section role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
      <h2 className="mb-2 font-semibold">
        {failed.length === 1 ? "1 saisie refusée par le serveur" : `${failed.length} saisies refusées par le serveur`}
      </h2>
      <ul className="flex flex-col gap-3">
        {failed.map((entry) => (
          <li key={entry.id} className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="font-medium">{entry.label}</p>
              <p className="text-red-800">{entry.error}</p>
            </div>
            <div className="flex shrink-0 gap-2">
              <button
                type="button"
                onClick={() => void retry(entry)}
                disabled={busyId === entry.id}
                className="rounded border border-red-300 bg-white px-3 py-1 text-xs font-medium text-red-800 hover:bg-red-100 disabled:opacity-50"
              >
                Réessayer
              </button>
              <button
                type="button"
                onClick={() => void remove(entry)}
                className="rounded px-3 py-1 text-xs text-red-800 underline"
              >
                Supprimer
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
