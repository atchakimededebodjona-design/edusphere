"use client";

import { useCallback, useEffect, useState } from "react";
import { PassportPhotoPicker } from "@/components/photos/PassportPhotoPicker";
import { ApiError } from "@/lib/api/client";
import { students } from "@/lib/students/client";

// Photo d'identité de l'élève. 2026-11-19 : deux façons de la mettre (components/photos/
// PassportPhotoPicker.tsx) — appareil photo avec cadrage au format passeport, ou fichier déjà prêt
// (JPEG, PNG, WebP, 5 Mio au plus, mêmes contrôles que l'API). L'enseignant la voit seulement.
export function StudentPhoto({ studentId, canManage }: { studentId: string; canManage: boolean }) {
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const loadPhoto = useCallback(() => {
    void students.getPhotoBlobUrl(studentId).then(setPhotoUrl);
  }, [studentId]);

  useEffect(() => {
    loadPhoto();
  }, [loadPhoto]);

  async function upload(file: File) {
    setError(null);
    await students.uploadPhoto(studentId, file);
    setPhotoUrl(await students.getPhotoBlobUrl(studentId));
  }

  async function handleDelete() {
    setDeleting(true);
    setError(null);
    try {
      await students.deletePhoto(studentId);
      setPhotoUrl(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Échec de la suppression de la photo.");
    } finally {
      setDeleting(false);
      setConfirmingDelete(false);
    }
  }

  return (
    <div className="flex flex-wrap items-start gap-4">
      {photoUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={photoUrl}
          alt="Photo de l'élève"
          className="h-[103px] w-20 rounded object-cover"
          data-testid="student-photo-img"
        />
      ) : (
        <div
          className="flex h-[103px] w-20 items-center justify-center rounded bg-slate-200 text-center text-xs text-slate-500"
          data-testid="student-photo-empty"
        >
          Aucune photo
        </div>
      )}

      {canManage && (
        <div className="flex flex-col gap-2">
          {confirmingDelete ? (
            <div className="flex items-center gap-2 text-xs" data-testid="photo-delete-confirm">
              <span className="text-slate-700">Supprimer la photo ?</span>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                className="text-red-700 underline disabled:opacity-50"
                data-testid="photo-delete-confirm-yes"
              >
                Oui, supprimer
              </button>
              <button
                type="button"
                onClick={() => setConfirmingDelete(false)}
                disabled={deleting}
                className="text-slate-600 underline disabled:opacity-50"
              >
                Annuler
              </button>
            </div>
          ) : (
            <>
              <PassportPhotoPicker capture="environment" onPhoto={upload} disabled={deleting} />
              {photoUrl && (
                <button
                  type="button"
                  onClick={() => setConfirmingDelete(true)}
                  disabled={deleting}
                  className="self-start rounded border border-slate-300 px-3 py-2 text-sm text-red-700 hover:bg-slate-100 disabled:opacity-50"
                  data-testid="photo-delete"
                >
                  Supprimer la photo
                </button>
              )}
            </>
          )}
        </div>
      )}
      {error && (
        <p className="text-sm text-red-700" data-testid="photo-error">
          {error}
        </p>
      )}
    </div>
  );
}
