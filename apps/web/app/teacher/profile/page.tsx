"use client";

import { TableSkeleton } from "@/components/ui/DataTable";
import { useEffect, useState } from "react";
import { PassportPhotoPicker } from "@/components/photos/PassportPhotoPicker";
import { PhotoThumb } from "@/components/photos/PhotoThumb";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { announceMyPhoto, myPhoto } from "@/lib/photos/client";
import { useMyPhoto } from "@/lib/photos/useMyPhoto";
import { describeTeacherError, teacherApi, type TeacherMe } from "@/lib/teacher/client";

// Profil : rôle, école et coordonnées en LECTURE SEULE (aucune modification de rôle, d'école,
// de permissions ou de is_platform_admin, les règles produit ne l'autorisent pas). Seule la photo
// d'identité se met ici (2026-11-19) ; l'administration de l'école peut aussi la mettre.
export default function TeacherProfilePage() {
  const [me, setMe] = useState<TeacherMe | null>(null);
  const [error, setError] = useState<string | null>(null);
  const photo = useMyPhoto();
  const [confirmingRemove, setConfirmingRemove] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);

  function load() {
    setMe(null);
    setError(null);
    teacherApi
      .me()
      .then((data) => {
        setMe(data);
        announceMyPhoto(Boolean(data.has_photo));
      })
      .catch((err) => setError(describeTeacherError(err)));
  }

  useEffect(() => {
    load();
  }, []);

  async function removePhoto() {
    setRemoveError(null);
    try {
      await myPhoto.remove();
      setConfirmingRemove(false);
    } catch (err) {
      setRemoveError(toErrorMessage(err));
    }
  }

  if (error) return <ErrorRetry message={error} onRetry={load} />;
  if (!me) return <TableSkeleton rows={3} />;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Mon profil</h1>

      <section className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:flex-row sm:items-start">
        <PhotoThumb path={photo.path} version={photo.version} name={me.full_name} size="lg" testId="my-photo" />
        <div className="flex flex-col gap-2">
          <h2 className="text-base font-bold text-slate-900">Photo d&apos;identité</h2>
          <p className="text-xs text-slate-600">
            Format passeport. Avec l&apos;appareil photo, placez votre visage dans l&apos;ovale, de face, sur un fond clair.
          </p>
          <PassportPhotoPicker capture="user" onPhoto={(file) => myPhoto.upload(file)} />
          {photo.path &&
            (confirmingRemove ? (
              <span className="flex items-center gap-3 text-sm">
                <button type="button" onClick={() => void removePhoto()} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-red-700 hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50">
                  Confirmer le retrait
                </button>
                <button type="button" onClick={() => setConfirmingRemove(false)} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-primary-700 hover:bg-primary-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50">
                  Annuler
                </button>
              </span>
            ) : (
              <button type="button" onClick={() => setConfirmingRemove(true)} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-red-700 hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 self-start">
                Retirer ma photo
              </button>
            ))}
          {removeError && (
            <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              {removeError}
            </p>
          )}
        </div>
      </section>

      <dl className="grid grid-cols-1 gap-2 rounded-xl border border-slate-200 bg-white p-4 text-sm sm:grid-cols-2">
        <dt className="text-slate-600">Nom</dt>
        <dd>{me.full_name}</dd>
        <dt className="text-slate-600">Email</dt>
        <dd>{me.email}</dd>
        <dt className="text-slate-600">Téléphone</dt>
        <dd>{me.phone ?? "—"}</dd>
        <dt className="text-slate-600">École</dt>
        <dd>{me.schools.map((s) => s.name).join(", ") || "—"}</dd>
        <dt className="text-slate-600">Rôle</dt>
        <dd>Enseignant</dd>
      </dl>
      <p className="text-xs text-slate-600">Pour modifier vos autres informations, contactez l&apos;administration de l&apos;école.</p>
    </div>
  );
}
