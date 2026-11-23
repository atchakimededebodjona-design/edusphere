// Photos d'identité (2026-11-19) : celle du compte connecté (/auth/me/photo), celles du personnel
// d'une école (/users/{id}/photo, administration) et celles des élèves (/students/{id}/photo).
// Les fichiers passent par `apiFetch` : une photo déjà vue reste affichable hors connexion (copie
// gardée sur l'appareil, comme les autres lectures).

import { apiFetch } from "@/lib/api/client";

export const PHOTO_MAX_BYTES = 5 * 1024 * 1024;
export const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];

/** Message d'erreur, ou null si le fichier peut partir tel quel (mêmes règles que l'API). */
export function photoFileProblem(file: File): string | null {
  if (file.size === 0) return "Ce fichier est vide.";
  if (file.size > PHOTO_MAX_BYTES) return "Photo trop volumineuse (maximum 5 Mio).";
  if (!PHOTO_TYPES.includes(file.type)) return "Type de fichier non autorisé (JPEG, PNG ou WebP uniquement).";
  return null;
}

/** Adresse locale (blob:) de la photo, ou null si elle est absente ou illisible. À libérer avec URL.revokeObjectURL. */
export async function photoObjectUrl(path: string): Promise<string | null> {
  try {
    const response = await apiFetch(path);
    return URL.createObjectURL(await response.blob());
  } catch {
    return null;
  }
}

async function upload(path: string, file: File, extra: Record<string, string> = {}): Promise<{ has_photo: boolean }> {
  const form = new FormData();
  for (const [key, value] of Object.entries(extra)) form.append(key, value);
  form.append("file", file);
  const response = await apiFetch(path, { method: "POST", body: form });
  return response.json();
}

export const MY_PHOTO_PATH = "/api/v1/auth/me/photo";

// Photo changée depuis « Mon profil » : l'en-tête de l'espace se met à jour sans recharger la page.
export const MY_PHOTO_EVENT = "edulinkage:my-photo";
export type MyPhotoDetail = { hasPhoto: boolean; version: number };

/** Aussi appelée par « Mon profil » à l'ouverture : la photo a pu être mise par l'administration depuis la connexion. */
export function announceMyPhoto(hasPhoto: boolean) {
  window.dispatchEvent(new CustomEvent<MyPhotoDetail>(MY_PHOTO_EVENT, { detail: { hasPhoto, version: Date.now() } }));
}

export const myPhoto = {
  upload: async (file: File) => {
    const result = await upload(MY_PHOTO_PATH, file);
    announceMyPhoto(true);
    return result;
  },
  remove: async () => {
    await apiFetch(MY_PHOTO_PATH, { method: "DELETE" });
    announceMyPhoto(false);
  },
};

export const staffPhoto = {
  path: (userId: string, schoolId: string) =>
    `/api/v1/users/${encodeURIComponent(userId)}/photo?school_id=${encodeURIComponent(schoolId)}`,
  upload: (userId: string, schoolId: string, file: File) =>
    upload(`/api/v1/users/${encodeURIComponent(userId)}/photo`, file, { school_id: schoolId }),
  remove: async (userId: string, schoolId: string) => {
    await apiFetch(staffPhoto.path(userId, schoolId), { method: "DELETE" });
  },
};

export const studentPhotoPath = (studentId: string) => `/api/v1/students/${encodeURIComponent(studentId)}/photo`;
