"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { PhotoThumb } from "@/components/photos/PhotoThumb";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { studentPhotoPath } from "@/lib/photos/client";
import { describeTeacherError, teacherApi, type TeacherStudent } from "@/lib/teacher/client";

// Élèves des seules classes affectées. Recherche et filtre de classe sont appliqués par le backend.
// Lecture seule : aucune création, modification ni suppression depuis le portail enseignant.
// 2026-11-19 : photo d'identité de chaque élève (mise par l'administration), chargée à l'affichage.
function TeacherStudentsPageContent() {
  const searchParams = useSearchParams();
  const initialClass = searchParams.get("class_id") ?? "";
  const [classId, setClassId] = useState(initialClass);
  const [search, setSearch] = useState("");
  const [students, setStudents] = useState<TeacherStudent[] | null>(null);
  const [classes, setClasses] = useState<{ id: string; name: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    teacherApi.classes().then((list) => setClasses(list.map((c) => ({ id: c.id, name: c.name })))).catch(() => setClasses([]));
  }, []);

  useEffect(() => {
    setStudents(null);
    setError(null);
    const handle = setTimeout(() => {
      teacherApi
        .students({ classId: classId || undefined, search: search.trim() || undefined })
        .then(setStudents)
        .catch((err) => setError(describeTeacherError(err)));
    }, 200);
    return () => clearTimeout(handle);
  }, [classId, search, reloadKey]);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Mes élèves</h1>
      <div className="grid gap-3 sm:grid-cols-2">
        <input
          type="search"
          aria-label="Rechercher un élève"
          placeholder="Rechercher un élève"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
        />
        <select aria-label="Classe" value={classId} onChange={(e) => setClassId(e.target.value)} className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500">
          <option value="">Toutes mes classes</option>
          {classes.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>

      {error && <ErrorRetry message={error} onRetry={() => setReloadKey((k) => k + 1)} />}
      {!error && students === null && <p className="text-sm text-slate-600">Chargement des élèves...</p>}
      {students && students.length === 0 && <p className="text-sm text-slate-600">Aucun élève trouvé.</p>}
      {students && students.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-slate-600">
              <tr>
                <th className="px-3 py-2">
                  <span className="sr-only">Photo</span>
                </th>
                <th className="hidden px-3 py-2 sm:table-cell">Matricule</th>
                <th className="px-3 py-2">Nom</th>
                <th className="px-3 py-2">Classe</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {students.map((s) => (
                <tr key={`${s.id}-${s.class_id}`}>
                  <td className="px-3 py-2">
                    <PhotoThumb
                      path={s.has_photo ? studentPhotoPath(s.id) : null}
                      name={`${s.first_name} ${s.last_name}`}
                      size="sm"
                      lazy
                      testId={`student-photo-${s.id}`}
                    />
                  </td>
                  <td className="hidden px-3 py-2 sm:table-cell">{s.matricule}</td>
                  <td className="px-3 py-2">
                    {s.last_name} {s.first_name}
                    {/* Téléphone : le matricule passe sous le nom (colonne masquée). */}
                    <span className="block text-xs text-slate-600 sm:hidden">{s.matricule}</span>
                  </td>
                  <td className="px-3 py-2">{s.class_name}</td>
                  <td className="px-3 py-2 text-right">
                    <Link href={`/teacher/students/${s.id}`} className="font-medium text-primary-700 underline underline-offset-2 hover:text-primary-800">
                      Fiche
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function TeacherStudentsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-slate-600">Chargement...</p>}>
      <TeacherStudentsPageContent />
    </Suspense>
  );
}
