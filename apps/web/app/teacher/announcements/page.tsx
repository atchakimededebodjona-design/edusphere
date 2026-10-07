"use client";

import { useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { describeTeacherError, teacherApi, type TeacherAnnouncement } from "@/lib/teacher/client";

// Annonces réellement destinées à l'enseignant : école entière, ou une classe où il est affecté
// (GET /api/v1/teacher/announcements, filtré côté backend). Aucune publication depuis ce portail :
// la publication reste soumise à `announcements.manage`, que le rôle TEACHER ne possède pas.
export default function TeacherAnnouncementsPage() {
  const [items, setItems] = useState<TeacherAnnouncement[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setItems(null);
    setError(null);
    teacherApi.announcements().then(setItems).catch((err) => setError(describeTeacherError(err)));
  }

  useEffect(() => {
    load();
  }, []);

  if (error) return <ErrorRetry message={error} onRetry={load} />;
  if (items === null) return <p className="text-sm text-slate-400">Chargement des annonces...</p>;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Annonces</h1>
      {items.length === 0 && <p className="text-sm text-slate-500">Aucune annonce pour le moment.</p>}
      <ul className="flex flex-col gap-2">
        {items.map((n) => (
          <li key={n.id} className="rounded-xl border border-slate-200 bg-white p-3 text-sm">
            <p className={n.read ? "text-slate-600" : "font-medium text-slate-900"}>{n.title}</p>
            <p className="text-slate-600">{n.body}</p>
            <p className="mt-1 text-xs text-slate-400">{new Date(n.created_at).toLocaleDateString("fr-FR")}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
