"use client";

import { TableSkeleton } from "@/components/ui/DataTable";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { PhotoThumb } from "@/components/photos/PhotoThumb";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { studentPhotoPath } from "@/lib/photos/client";
import { describeTeacherError, teacherApi, type TeacherStudentDetail } from "@/lib/teacher/client";

// Fiche élève en lecture seule. Un élève hors des classes affectées répond 404 côté backend.
// 2026-11-19 : photo d'identité, mise par l'administration (l'enseignant la voit seulement).
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
  if (!data) return <TableSkeleton rows={3} />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-4">
        <PhotoThumb
          path={data.has_photo ? studentPhotoPath(data.id) : null}
          name={`${data.first_name} ${data.last_name}`}
          size="lg"
          testId="student-detail-photo"
        />
        <h1 className="text-2xl font-bold text-slate-900">
          {data.last_name} {data.first_name}
        </h1>
      </div>
      <dl className="grid grid-cols-1 gap-2 rounded-xl border border-slate-200 bg-white p-4 text-sm sm:grid-cols-2">
        <dt className="text-slate-600">Matricule</dt>
        <dd>{data.matricule}</dd>
        <dt className="text-slate-600">Statut</dt>
        <dd>{data.status}</dd>
        <dt className="text-slate-600">Classes</dt>
        <dd>{data.classes.map((c) => c.class_name).join(", ") || "—"}</dd>
      </dl>
      <p className="text-xs text-slate-600">Fiche en lecture seule.</p>
      <Link href="/teacher/students" className="text-sm font-medium text-primary-700 underline underline-offset-2 hover:text-primary-800">
        Retour à mes élèves
      </Link>
    </div>
  );
}
