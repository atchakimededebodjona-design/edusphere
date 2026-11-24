"use client";

import { useEffect, useState } from "react";
import { NotificationItem } from "@/components/notifications/NotificationItem";
import { TableSkeleton } from "@/components/ui/DataTable";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { Card, EmptyState, PageHeader } from "@/components/ui/Surface";
import { notifications, type Notification } from "@/lib/notifications/client";
import { describeTeacherError } from "@/lib/teacher/client";

// Notifications PERSONNELLES de l'enseignant (endpoint existant, filtré par destinataire côté serveur).
// Phase 3 (2026-11-24) : même présentation que l'administration et le parent (NotificationItem).
export default function TeacherNotificationsPage() {
  const [items, setItems] = useState<Notification[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setItems(null);
    setError(null);
    notifications.list({ limit: 50 }).then((list) => setItems(list.items)).catch((err) => setError(describeTeacherError(err)));
  }

  useEffect(() => {
    load();
  }, []);

  async function markRead(id: string) {
    try {
      const updated = await notifications.markRead(id);
      setItems((prev) => (prev ?? []).map((n) => (n.id === id ? updated : n)));
    } catch (err) {
      setError(describeTeacherError(err));
    }
  }

  if (error) return <ErrorRetry message={error} onRetry={load} />;

  return (
    <div className="flex max-w-3xl flex-col gap-5">
      <PageHeader title="Notifications" />
      {items === null ? (
        <TableSkeleton rows={4} />
      ) : items.length === 0 ? (
        <EmptyState icon="bell" title="Aucune notification." description="Les annonces de l'école s'afficheront ici." />
      ) : (
        <Card padded={false}>
          <ul aria-label="Notifications" className="divide-y divide-slate-200">
            {items.map((n) => (
              <NotificationItem key={n.id} notification={n} onMarkRead={(id) => void markRead(id)} />
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
