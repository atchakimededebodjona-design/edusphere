"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { describeTeacherError, teacherApi, type TeacherClass } from "@/lib/teacher/client";

// Liste renvoyée par le backend : uniquement les classes où l'enseignant a une affectation.
export default function TeacherClassesPage() {
  const [classes, setClasses] = useState<TeacherClass[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setClasses(null);
    setError(null);
    teacherApi.classes().then(setClasses).catch((err) => setError(describeTeacherError(err)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorRetry message={error} onRetry={load} />;
  if (classes === null) return <p className="text-sm text-slate-400">Chargement des classes...</p>;
  if (classes.length === 0) {
    return (
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold text-slate-900">Mes classes</h1>
        <p className="text-sm text-slate-500">Aucune classe ne vous est affectée pour le moment.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Mes classes</h1>
      <div className="grid gap-4 md:grid-cols-2">
        {classes.map((c) => (
          <article key={c.id} className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h2 className="font-semibold text-slate-900">{c.name}</h2>
                <p className="text-xs text-slate-500">{c.level_name ?? "Niveau non renseigné"}</p>
              </div>
              <span className="text-xs text-slate-600">{c.student_count} élève(s)</span>
            </div>
            <ul className="text-sm text-slate-700">
              {c.subjects.map((s) => (
                <li key={s.class_subject_id}>
                  {s.subject_name} <span className="text-slate-400">— coef. {s.coefficient}</span>
                </li>
              ))}
            </ul>
            <div className="flex flex-wrap gap-3 text-sm">
              <Link href={`/teacher/classes/${c.id}`} className="text-slate-900 underline">Détail</Link>
              <Link href={`/teacher/students?class_id=${c.id}`} className="text-slate-900 underline">Élèves</Link>
              <Link href={`/teacher/attendance?class_id=${c.id}`} className="text-slate-900 underline">Présences</Link>
              <Link href={`/teacher/grades?class_id=${c.id}`} className="text-slate-900 underline">Notes</Link>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
