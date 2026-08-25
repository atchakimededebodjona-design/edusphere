"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { students } from "@/lib/students/client";

export function StudentPhoto({ studentId, canManage }: { studentId: string; canManage: boolean }) {
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void students.getPhotoBlobUrl(studentId).then(setPhotoUrl);
  }, [studentId]);

  async function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setError(null);
    try {
      await students.uploadPhoto(studentId, file);
      setPhotoUrl(await students.getPhotoBlobUrl(studentId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Échec de l'envoi de la photo.");
    }
  }

  return (
    <div className="flex items-center gap-4">
      {photoUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={photoUrl} alt="Photo de l'élève" className="h-20 w-20 rounded object-cover" />
      ) : (
        <div className="flex h-20 w-20 items-center justify-center rounded bg-slate-200 text-xs text-slate-500">
          Aucune photo
        </div>
      )}
      {canManage && (
        <label className="cursor-pointer rounded border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-100">
          Changer la photo
          <input type="file" accept="image/*" onChange={handleChange} className="hidden" />
        </label>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  );
}
