"use client";

import { TableSkeleton } from "@/components/ui/DataTable";
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
  if (!data) return <TableSkeleton rows={3} />;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">{data.name}</h1>
        <p className="text-sm text-slate-600">
          {data.level_name ?? "Niveau non renseigné"} · {data.student_count} élève(s)
        </p>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="mb-2 text-sm font-semibold text-slate-900">Mes matières dans cette classe</h2>
        <ul className="text-sm text-slate-700">
          {data.subjects.map((s) => (
            <li key={s.class_subject_id}>
              {s.subject_name} <span className="text-slate-600">— coefficient {s.coefficient}</span>
            </li>
          ))}
        </ul>
      </section>

      <div className="flex flex-wrap gap-3">
        <Link href={`/teacher/students?class_id=${classId}`} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10">
          Élèves
        </Link>
        <Link href={`/teacher/attendance?class_id=${classId}`} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10">
          Présences
        </Link>
        <Link href={`/teacher/grades?class_id=${classId}`} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10">
          Notes
        </Link>
        <Link href={`/teacher/report-cards?class_id=${classId}`} className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700">
          Bulletins publiés
        </Link>
      </div>
    </div>
  );
}
