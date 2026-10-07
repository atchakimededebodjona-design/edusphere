"use client";

import { useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { notifications, type Notification } from "@/lib/notifications/client";
import { describeTeacherError } from "@/lib/teacher/client";

// Notifications PERSONNELLES de l'enseignant (endpoint existant, filtré par destinataire côté serveur).
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
  if (items === null) return <p className="text-sm text-slate-400">Chargement des notifications...</p>;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Notifications</h1>
      {items.length === 0 && <p className="text-sm text-slate-500">Aucune notification.</p>}
      <ul className="flex flex-col gap-2">
        {items.map((n) => (
          <li key={n.id} className="flex items-start justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3 text-sm">
            <div>
              <p className={n.read_at ? "text-slate-600" : "font-medium text-slate-900"}>{n.title}</p>
              <p className="text-slate-500">{n.body}</p>
            </div>
            {!n.read_at && (
              <button type="button" onClick={() => markRead(n.id)} className="shrink-0 text-xs text-slate-900 underline">
                Marquer lue
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
