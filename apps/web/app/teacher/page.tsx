"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { describeTeacherError, teacherApi, type TeacherDashboard } from "@/lib/teacher/client";

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-xs text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900">{value}</p>
    </div>
  );
}

export default function TeacherDashboardPage() {
  const [data, setData] = useState<TeacherDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setData(null);
    setError(null);
    teacherApi.dashboard().then(setData).catch((err) => setError(describeTeacherError(err)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorRetry message={error} onRetry={load} />;
  if (!data) return <p className="text-sm text-slate-400">Chargement du tableau de bord...</p>;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Bonjour {data.teacher_name}</h1>
        <p className="text-sm text-slate-500">
          {data.schools.length > 0 ? data.schools.map((s) => s.name).join(", ") : "Aucune école rattachée"}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="Classes affectées" value={data.class_count} />
        <Metric label="Matières affectées" value={data.subject_count} />
        <Metric label="Élèves suivis" value={data.student_count} />
        <Metric label="Notifications récentes" value={data.recent_notifications.length} />
      </div>

      <div className="flex flex-wrap gap-3">
        <Link href="/teacher/attendance" className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white">
          Faire l&apos;appel
        </Link>
        <Link href="/teacher/grades" className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white">
          Saisir les notes
        </Link>
        <Link href="/teacher/classes" className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700">
          Mes classes
        </Link>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Évaluations récentes</h2>
          {data.recent_assessments.length === 0 ? (
            <p className="text-sm text-slate-400">Aucune évaluation pour le moment.</p>
          ) : (
            <ul className="flex flex-col gap-2 text-sm">
              {data.recent_assessments.map((a) => (
                <li key={a.id} className="flex justify-between gap-2">
                  <span>
                    {a.name} — {a.class_name} · {a.subject_name}
                  </span>
                  <span className="text-slate-500">{a.assessment_date}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Notifications récentes</h2>
          {data.recent_notifications.length === 0 ? (
            <p className="text-sm text-slate-400">Aucune notification.</p>
          ) : (
            <ul className="flex flex-col gap-2 text-sm">
              {data.recent_notifications.map((n) => (
                <li key={n.id} className={n.read ? "text-slate-500" : "font-medium text-slate-900"}>
                  {n.title}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
