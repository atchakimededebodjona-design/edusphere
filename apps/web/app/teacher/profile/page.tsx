"use client";

import { useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { describeTeacherError, teacherApi, type TeacherMe } from "@/lib/teacher/client";

// Profil en LECTURE SEULE : rôle, école, coordonnées. Aucune modification de rôle, d'école,
// de permissions ou de is_platform_admin n'est proposée ici (les règles produit ne l'autorisent pas).
export default function TeacherProfilePage() {
  const [me, setMe] = useState<TeacherMe | null>(null);
  const [error, setError] = useState<string | null>(null);

  function load() {
    setMe(null);
    setError(null);
    teacherApi.me().then(setMe).catch((err) => setError(describeTeacherError(err)));
  }

  useEffect(() => {
    load();
  }, []);

  if (error) return <ErrorRetry message={error} onRetry={load} />;
  if (!me) return <p className="text-sm text-slate-400">Chargement du profil...</p>;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Mon profil</h1>
      <dl className="grid grid-cols-1 gap-2 rounded-xl border border-slate-200 bg-white p-4 text-sm sm:grid-cols-2">
        <dt className="text-slate-500">Nom</dt>
        <dd>{me.full_name}</dd>
        <dt className="text-slate-500">Email</dt>
        <dd>{me.email}</dd>
        <dt className="text-slate-500">Téléphone</dt>
        <dd>{me.phone ?? "—"}</dd>
        <dt className="text-slate-500">École</dt>
        <dd>{me.schools.map((s) => s.name).join(", ") || "—"}</dd>
        <dt className="text-slate-500">Rôle</dt>
        <dd>Enseignant</dd>
      </dl>
      <p className="text-xs text-slate-400">Pour modifier vos informations, contactez l&apos;administration de l&apos;école.</p>
    </div>
  );
}
