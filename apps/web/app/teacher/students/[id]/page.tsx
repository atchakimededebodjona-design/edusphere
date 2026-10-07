"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { describeTeacherError, teacherApi, type TeacherStudentDetail } from "@/lib/teacher/client";

// Fiche élève en lecture seule. Un élève hors des classes affectées répond 404 côté backend.
export default function TeacherStudentDetailPage() {
  const params = useParams<{ id: string }>();
  const studentId = params.id;
  const [data, setData] = useState<TeacherStudentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setData(null);
    setError(null);
    teacherApi.student(studentId).then(setData).catch((err) => setError(describeTeacherError(err)));
  }, [studentId]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorRetry message={error} onRetry={load} />;
  if (!data) return <p className="text-sm text-slate-400">Chargement de la fiche...</p>;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">
        {data.last_name} {data.first_name}
      </h1>
      <dl className="grid grid-cols-1 gap-2 rounded-xl border border-slate-200 bg-white p-4 text-sm sm:grid-cols-2">
        <dt className="text-slate-500">Matricule</dt>
        <dd>{data.matricule}</dd>
        <dt className="text-slate-500">Statut</dt>
        <dd>{data.status}</dd>
        <dt className="text-slate-500">Classes</dt>
        <dd>{data.classes.map((c) => c.class_name).join(", ") || "—"}</dd>
      </dl>
      <p className="text-xs text-slate-400">Fiche en lecture seule.</p>
      <Link href="/teacher/students" className="text-sm text-slate-900 underline">
        Retour à mes élèves
      </Link>
    </div>
  );
}
