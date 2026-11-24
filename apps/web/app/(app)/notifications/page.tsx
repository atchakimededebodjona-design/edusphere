"use client";

import { useCallback, useEffect, useState } from "react";
import { NotificationItem } from "@/components/notifications/NotificationItem";
import { Button } from "@/components/ui/Button";
import { TableSkeleton } from "@/components/ui/DataTable";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { Card, EmptyState, PageHeader } from "@/components/ui/Surface";
import { ApiError } from "@/lib/api/client";
import { notifications as notificationsClient, type Notification } from "@/lib/notifications/client";

// Centre de notifications de l'administration ; la même page sert au parent (/parent/notifications).
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
      setError(null);
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
    try {
      const updated = await notificationsClient.markRead(id);
      setItems((prev) => (prev ?? []).map((n) => (n.id === id ? updated : n)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    }
  }

  async function handleMarkAllRead() {
    try {
      await notificationsClient.markAllRead();
      await loadFirstPage();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    }
  }

  if (error && items === null) return <ErrorRetry message={error} onRetry={loadFirstPage} />;

  const unreadCount = (items ?? []).filter((n) => n.read_at === null).length;

  return (
    <div className="flex max-w-3xl flex-col gap-5">
      <PageHeader
        title="Notifications"
        description={
          items === null
            ? undefined
            : unreadCount > 0
              ? `${unreadCount} non lue${unreadCount > 1 ? "s" : ""}${nextBefore ? " parmi les plus récentes" : ""}.`
              : "Tout est lu."
        }
        actions={
          unreadCount > 0 && (
            <Button variant="secondary" icon="checkSquare" onClick={() => void handleMarkAllRead()}>
              Tout marquer comme lu
            </Button>
          )
        }
      />

      {error && <ErrorRetry message={error} onRetry={loadFirstPage} />}

      {items === null ? (
        <TableSkeleton rows={4} />
      ) : items.length === 0 ? (
        <EmptyState icon="bell" title="Aucune notification." description="Annonces, bulletins, paiements et absences s'afficheront ici." />
      ) : (
        <Card padded={false}>
          <ul aria-label="Notifications" className="divide-y divide-slate-200">
            {items.map((n) => (
              <NotificationItem key={n.id} notification={n} onMarkRead={(id) => void handleMarkRead(id)} />
            ))}
          </ul>
        </Card>
      )}

      {nextBefore && (
        <Button variant="secondary" className="self-center" onClick={() => void handleLoadMore()} disabled={loadingMore}>
          {loadingMore ? "Chargement..." : "Charger plus"}
        </Button>
      )}
    </div>
  );
}
