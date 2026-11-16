"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth/useAuth";
import { listOutbox, OUTBOX_CHANGED_EVENT, type OutboxEntry } from "@/lib/offline/outbox";

/** Saisies en attente du compte connecté, tenues à jour à chaque changement de la boîte d'envoi. */
export function useOutbox(): OutboxEntry[] {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  const [entries, setEntries] = useState<OutboxEntry[]>([]);

  useEffect(() => {
    if (!userId) {
      setEntries([]);
      return;
    }
    let cancelled = false;
    const load = () => {
      void listOutbox().then((list) => {
        if (!cancelled) setEntries(list);
      });
    };
    load();
    window.addEventListener(OUTBOX_CHANGED_EVENT, load);
    return () => {
      cancelled = true;
      window.removeEventListener(OUTBOX_CHANGED_EVENT, load);
    };
  }, [userId]);

  return entries;
}
