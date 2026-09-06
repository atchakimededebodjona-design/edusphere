"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { schoolClasses, type SchoolClass } from "@/lib/academics/client";
import { useAuth } from "@/lib/auth/useAuth";
import { announcements, type AnnouncementTargetType } from "@/lib/notifications/client";

export default function AnnouncementsPage() {
  const { currentSchoolId } = useAuth();
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [targetType, setTargetType] = useState<AnnouncementTargetType>("SCHOOL");
  const [selectedClassIds, setSelectedClassIds] = useState<string[]>([]);
  const [status, setStatus] = useState<"idle" | "saving" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<number | null>(null);

  useEffect(() => {
    if (currentSchoolId) void schoolClasses.list(currentSchoolId).then(setClasses);
  }, [currentSchoolId]);

  function toggleClass(classId: string) {
    setSelectedClassIds((prev) => (prev.includes(classId) ? prev.filter((id) => id !== classId) : [...prev, classId]));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!currentSchoolId) return;
    setStatus("saving");
    setError(null);
    setResult(null);
    try {
      const response = await announcements.create({
        school_id: currentSchoolId,
        title,
        body,
        target_type: targetType,
        class_ids: targetType === "CLASS" ? selectedClassIds : undefined,
      });
      setResult(response.recipient_count);
      setTitle("");
      setBody("");
      setSelectedClassIds([]);
      setStatus("idle");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
      setStatus("error");
    }
  }

  if (!currentSchoolId || classes === null) return <p className="text-sm text-slate-500">Chargement...</p>;

  return (
    <div className="flex max-w-xl flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Annonces</h1>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded border border-slate-200 p-4">
        <label className="flex flex-col gap-1 text-sm text-slate-700">
          Titre
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            maxLength={255}
            required
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-700">
          Contenu
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            maxLength={2000}
            required
            rows={4}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-700">
          Cible
          <select
            value={targetType}
            onChange={(e) => setTargetType(e.target.value as AnnouncementTargetType)}
            className="rounded border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="SCHOOL">Toute l&apos;école</option>
            <option value="CLASS">Une ou plusieurs classes</option>
          </select>
        </label>
        {targetType === "CLASS" && (
          <div className="flex flex-col gap-1 text-sm text-slate-700">
            Classes
            <div className="flex flex-wrap gap-2">
              {classes.map((c) => (
                <label key={c.id} className="flex items-center gap-1 rounded border border-slate-300 px-2 py-1 text-xs">
                  <input type="checkbox" checked={selectedClassIds.includes(c.id)} onChange={() => toggleClass(c.id)} />
                  {c.name}
                </label>
              ))}
              {classes.length === 0 && <span className="text-xs text-slate-400">Aucune classe.</span>}
            </div>
          </div>
        )}
        <button
          type="submit"
          disabled={status === "saving" || (targetType === "CLASS" && selectedClassIds.length === 0)}
          className="w-fit rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {status === "saving" ? "Publication..." : "Publier"}
        </button>
        {result !== null && <p className="text-sm text-green-700">Annonce publiée — {result} destinataire(s) notifié(s).</p>}
        {error && <p className="text-sm text-red-700">{error}</p>}
      </form>
    </div>
  );
}
