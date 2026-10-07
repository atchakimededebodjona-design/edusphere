"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { students } from "@/lib/students/client";

const PHOTO_MAX_BYTES = 5 * 1024 * 1024;
const ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"];

export function StudentPhoto({ studentId, canManage }: { studentId: string; canManage: boolean }) {
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "uploading" | "deleting">("idle");
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const loadPhoto = useCallback(() => {
    void students.getPhotoBlobUrl(studentId).then(setPhotoUrl);
  }, [studentId]);

  useEffect(() => {
    loadPhoto();
  }, [loadPhoto]);

  async function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Réinitialise immédiatement l'input : sans ça, sélectionner deux fois le même fichier
    // d'affilée (ex. après une erreur) ne redéclenche pas onChange côté navigateur.
    event.target.value = "";
    if (!file) return;

    setError(null);
    if (file.size === 0) {
      setError("Ce fichier est vide.");
      return;
    }
    if (file.size > PHOTO_MAX_BYTES) {
      setError("Photo trop volumineuse (maximum 5 Mio).");
      return;
    }
    if (!ALLOWED_MIME_TYPES.includes(file.type)) {
      setError("Type de fichier non autorisé (JPEG, PNG ou WebP uniquement).");
      return;
    }

    setStatus("uploading");
    try {
      await students.uploadPhoto(studentId, file);
      setPhotoUrl(await students.getPhotoBlobUrl(studentId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Échec de l'envoi de la photo.");
    } finally {
      setStatus("idle");
    }
  }

  async function handleDelete() {
    setStatus("deleting");
    setError(null);
    try {
      await students.deletePhoto(studentId);
      setPhotoUrl(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Échec de la suppression de la photo.");
    } finally {
      setStatus("idle");
      setConfirmingDelete(false);
    }
  }

  const busy = status !== "idle";

  return (
    <div className="flex items-center gap-4">
      {photoUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={photoUrl} alt="Photo de l'élève" className="h-20 w-20 rounded object-cover" data-testid="student-photo-img" />
      ) : (
        <div
          className="flex h-20 w-20 items-center justify-center rounded bg-slate-200 text-xs text-slate-500"
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
                disabled={busy}
                className="text-red-700 underline disabled:opacity-50"
                data-testid="photo-delete-confirm-yes"
              >
                Oui, supprimer
              </button>
              <button
                type="button"
                onClick={() => setConfirmingDelete(false)}
                disabled={busy}
                className="text-slate-600 underline disabled:opacity-50"
              >
                Annuler
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <label
                className={`cursor-pointer rounded border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 ${
                  busy ? "pointer-events-none opacity-50" : ""
                }`}
              >
                {status === "uploading" ? "Envoi..." : "Changer la photo"}
                <input
                  type="file"
                  accept={ALLOWED_MIME_TYPES.join(",")}
                  onChange={handleChange}
                  disabled={busy}
                  className="hidden"
                  data-testid="photo-file-input"
                />
              </label>
              {photoUrl && (
                <button
                  type="button"
                  onClick={() => setConfirmingDelete(true)}
                  disabled={busy}
                  className="rounded border border-slate-300 px-3 py-2 text-sm text-red-700 hover:bg-slate-100 disabled:opacity-50"
                  data-testid="photo-delete"
                >
                  Supprimer la photo
                </button>
              )}
            </div>
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
