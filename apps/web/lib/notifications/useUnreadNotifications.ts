"use client";

import { useCallback, useEffect, useState } from "react";
import { notifications, type Notification } from "@/lib/notifications/client";

// 2026-11-17 — notifications non lues du compte connecté, pour le bandeau « Nouvelle annonce » et
// la cloche de l'espace enseignant : relues toutes les minutes, au retour sur l'onglet et à chaque
// lecture. Met aussi le compteur sur l'icône de l'application installée, quand le navigateur le permet.
const REFRESH_MS = 60_000;

export type UnreadNotifications = {
  count: number;
  /** Annonce non lue la plus récente, ou null. */
  latestAnnouncement: Notification | null;
  refresh: () => void;
};

function updateAppBadge(count: number): void {
  try {
    const nav = navigator as Navigator & { setAppBadge?: (n?: number) => Promise<void>; clearAppBadge?: () => Promise<void> };
    if (count > 0) void nav.setAppBadge?.(count).catch(() => undefined);
    else void nav.clearAppBadge?.().catch(() => undefined);
  } catch {
    // non pris en charge
  }
}

export function useUnreadNotifications(enabled: boolean): UnreadNotifications {
  const [count, setCount] = useState(0);
  const [latestAnnouncement, setLatestAnnouncement] = useState<Notification | null>(null);
  const [tick, setTick] = useState(0);
  const refresh = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    void (async () => {
      try {
        const unread = (await notifications.unreadCount()).count;
        if (cancelled) return;
        setCount(unread);
        updateAppBadge(unread);
        if (unread === 0) {
          setLatestAnnouncement(null);
          return;
        }
        const page = await notifications.list({ limit: 20 });
        if (cancelled) return;
        setLatestAnnouncement(page.items.find((item) => item.type === "ANNOUNCEMENT" && item.read_at === null) ?? null);
      } catch {
        // hors connexion : on garde ce qui est affiché
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [enabled, tick]);

  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(refresh, REFRESH_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [enabled, refresh]);

  return { count, latestAnnouncement, refresh };
}
