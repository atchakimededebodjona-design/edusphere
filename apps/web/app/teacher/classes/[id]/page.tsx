"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { describeTeacherError, teacherApi, type TeacherClass } from "@/lib/teacher/client";

// Une classe hors affectation répond 404 côté backend : on affiche alors le message d'accès refusé.
export default function TeacherClassDetailPage() {
  const params = useParams<{ id: string }>();
  const classId = params.id;
  const [data, setData] = useState<TeacherClass | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setData(null);
    setError(null);
    teacherApi.classDetail(classId).then(setData).catch((err) => setError(describeTeacherError(err)));
  }, [classId]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorRetry message={error} onRetry={load} />;
  if (!data) return <p className="text-sm text-slate-400">Chargement de la classe...</p>;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{data.name}</h1>
        <p className="text-sm text-slate-500">
          {data.level_name ?? "Niveau non renseigné"} · {data.student_count} élève(s)
        </p>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold text-slate-900">Mes matières dans cette classe</h2>
        <ul className="text-sm text-slate-700">
          {data.subjects.map((s) => (
            <li key={s.class_subject_id}>
              {s.subject_name} <span className="text-slate-400">— coefficient {s.coefficient}</span>
            </li>
          ))}
        </ul>
      </section>

      <div className="flex flex-wrap gap-3">
        <Link href={`/teacher/students?class_id=${classId}`} className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white">
          Élèves
        </Link>
        <Link href={`/teacher/attendance?class_id=${classId}`} className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white">
          Présences
        </Link>
        <Link href={`/teacher/grades?class_id=${classId}`} className="rounded-lg bg-slate-900 px-4 py-2 text-sm text-white">
          Notes
        </Link>
        <Link href={`/teacher/report-cards?class_id=${classId}`} className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700">
          Bulletins publiés
        </Link>
      </div>
    </div>
  );
}
