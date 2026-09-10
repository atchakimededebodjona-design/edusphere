"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth/useAuth";
import { notifications } from "@/lib/notifications/client";

// Une requête légère toutes les 30s suffit pour un badge non-lu — pas de state management
// global ni de mécanisme temps réel pour ce besoin (voir PHASE_21_DISCOVERY.md/commande §24).
const UNREAD_POLL_INTERVAL_MS = 30_000;

function useUnreadCount(enabled: boolean): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    async function poll() {
      try {
        const result = await notifications.unreadCount();
        if (!cancelled) setCount(result.count);
      } catch {
        // Best-effort : un badge qui ne se met pas à jour n'est jamais bloquant.
      }
    }

    void poll();
    const interval = setInterval(poll, UNREAD_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [enabled]);

  return count;
}

export function TopBar() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const unreadCount = useUnreadCount(Boolean(user));

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-6">
      <span className="text-lg font-bold text-slate-900">EduLinkage</span>
      <div className="flex items-center gap-4">
        {user && (
          <Link href="/notifications" className="relative text-slate-600 hover:text-slate-900" aria-label="Notifications">
            <span aria-hidden="true">🔔</span>
            {unreadCount > 0 && (
              <span className="absolute -right-2 -top-2 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </Link>
        )}
        {user && <span className="text-sm text-slate-600">{user.full_name}</span>}
        <button
          type="button"
          onClick={handleLogout}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
        >
          Déconnexion
        </button>
      </div>
    </header>
  );
}
