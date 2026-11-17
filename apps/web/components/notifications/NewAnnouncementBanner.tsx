"use client";

import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth/useAuth";
import { notifications } from "@/lib/notifications/client";
import { useUnreadNotifications } from "@/lib/notifications/useUnreadNotifications";

const DISMISSED_KEY = "edulinkage.announcement-dismissed";

function readDismissed(): string | null {
  try {
    return window.sessionStorage.getItem(DISMISSED_KEY);
  } catch {
    return null;
  }
}

// 2026-11-17 — une annonce non lue s'affiche en haut de CHAQUE page de l'espace, jusqu'à ce qu'elle
// soit lue (« Lire ») ou remise à plus tard pour cette visite. Avant, seule la petite cloche le
// signalait : une annonce pouvait passer inaperçue pendant des jours.
export function NewAnnouncementBanner({ inboxHref }: { inboxHref: string }) {
  const { status } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const { latestAnnouncement, refresh } = useUnreadNotifications(status === "authenticated");
  const [dismissedId, setDismissedId] = useState<string | null>(() => (typeof window === "undefined" ? null : readDismissed()));

  // Sur la page des annonces elle-même, la liste suffit.
  if (!latestAnnouncement || latestAnnouncement.id === dismissedId || pathname === inboxHref) return null;
  const announcement = latestAnnouncement;

  async function handleRead() {
    try {
      await notifications.markRead(announcement.id);
    } catch {
      // hors connexion : elle restera non lue, la page des annonces s'ouvre quand même
    }
    refresh();
    router.push(inboxHref);
  }

  function handleLater() {
    try {
      window.sessionStorage.setItem(DISMISSED_KEY, announcement.id);
    } catch {
      // ignore
    }
    setDismissedId(announcement.id);
  }

  return (
    <section
      role="status"
      aria-label="Nouvelle annonce"
      data-testid="new-announcement-banner"
      className="mb-4 flex flex-col gap-2 rounded-lg border border-sky-300 bg-sky-50 p-4 text-sky-950 shadow-sm sm:flex-row sm:items-start sm:justify-between"
    >
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-wide text-sky-800">📢 Nouvelle annonce</p>
        <p className="mt-0.5 font-semibold">{announcement.title}</p>
        <p className="mt-0.5 line-clamp-2 text-sm text-sky-900">{announcement.body}</p>
      </div>
      <div className="flex shrink-0 gap-2">
        <button
          type="button"
          onClick={() => void handleRead()}
          className="rounded bg-sky-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-sky-900"
        >
          Lire
        </button>
        <button type="button" onClick={handleLater} className="px-2 py-1.5 text-sm text-sky-900 underline">
          Plus tard
        </button>
      </div>
    </section>
  );
}
