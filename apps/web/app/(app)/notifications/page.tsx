"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { notifications as notificationsClient, type Notification } from "@/lib/notifications/client";

const TYPE_LABELS: Record<string, string> = {
  ANNOUNCEMENT: "Annonce",
  REPORT_CARD_PUBLISHED: "Bulletin",
  PAYMENT_RECORDED: "Paiement",
};

export default function NotificationsPage() {
  const [items, setItems] = useState<Notification[] | null>(null);
  const [nextBefore, setNextBefore] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadFirstPage = useCallback(async () => {
    try {
      const page = await notificationsClient.list({ limit: 20 });
      setItems(page.items);
      setNextBefore(page.next_before);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    }
  }, []);

  useEffect(() => {
    void loadFirstPage();
  }, [loadFirstPage]);

  async function handleLoadMore() {
    if (!nextBefore) return;
    setLoadingMore(true);
    try {
      const page = await notificationsClient.list({ limit: 20, before: nextBefore });
      setItems((prev) => [...(prev ?? []), ...page.items]);
      setNextBefore(page.next_before);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleMarkRead(id: string) {
    const updated = await notificationsClient.markRead(id);
    setItems((prev) => (prev ?? []).map((n) => (n.id === id ? updated : n)));
  }

  async function handleMarkAllRead() {
    await notificationsClient.markAllRead();
    await loadFirstPage();
  }

  if (items === null) return <p className="text-sm text-slate-500">Chargement...</p>;

  const hasUnread = items.some((n) => n.read_at === null);

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Notifications</h1>
        {hasUnread && (
          <button type="button" onClick={() => void handleMarkAllRead()} className="text-sm text-slate-600 underline">
            Tout marquer comme lu
          </button>
        )}
      </div>

      {error && <p className="text-sm text-red-700">{error}</p>}

      <div className="flex flex-col divide-y divide-slate-100 rounded border border-slate-200">
        {items.map((n) => (
          <div key={n.id} className={`flex items-start justify-between gap-3 px-4 py-3 ${n.read_at === null ? "bg-slate-50" : ""}`}>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium uppercase tracking-wide text-slate-400">{TYPE_LABELS[n.type] ?? n.type}</span>
              <span className="text-sm font-semibold text-slate-900">{n.title}</span>
              <span className="text-sm text-slate-600">{n.body}</span>
              <span className="text-xs text-slate-400">{new Date(n.created_at).toLocaleString()}</span>
            </div>
            {n.read_at === null && (
              <button type="button" onClick={() => void handleMarkRead(n.id)} className="shrink-0 text-xs text-slate-700 underline">
                Marquer lu
              </button>
            )}
          </div>
        ))}
        {items.length === 0 && <p className="px-4 py-6 text-center text-sm text-slate-400">Aucune notification.</p>}
      </div>

      {nextBefore && (
        <button
          type="button"
          onClick={() => void handleLoadMore()}
          disabled={loadingMore}
          className="w-fit rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-50"
        >
          {loadingMore ? "Chargement..." : "Charger plus"}
        </button>
      )}
    </div>
  );
}
