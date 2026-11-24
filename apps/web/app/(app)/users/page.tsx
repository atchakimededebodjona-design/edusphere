"use client";

import { Fragment, useEffect, useState } from "react";
import { PassportPhotoPicker } from "@/components/photos/PassportPhotoPicker";
import { PhotoThumb } from "@/components/photos/PhotoThumb";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/useAuth";
import { staffPhoto } from "@/lib/photos/client";
import {
  ASSIGNABLE_ROLES,
  SCHOOL_ADMIN_ONLY_ROLES,
  isSchoolAdminOf,
  users,
  type RoleCode,
  type UserCreateResponse,
  type UserWithRoles,
} from "@/lib/users/client";

const ROLE_LABELS: Record<string, string> = Object.fromEntries(ASSIGNABLE_ROLES.map((r) => [r.value, r.label]));

const initialForm = {
  email: "",
  full_name: "",
  phone: "",
  role_code: "TEACHER" as RoleCode,
};

export default function UsersPage() {
  const { currentSchoolId, currentOrganizationId, permissions, roles, user: currentUser } = useAuth();
  const canManage = permissions.includes("users.manage");
  // 2026-11-24 — parents et élèves : administrateur de l'école uniquement (lib/users/client.ts).
  const isSchoolAdminHere = isSchoolAdminOf(roles, currentOrganizationId, currentSchoolId);
  const creatableRoles = ASSIGNABLE_ROLES.filter((r) => isSchoolAdminHere || !SCHOOL_ADMIN_ONLY_ROLES.has(r.value));
  // Le rôle actuel d'une ligne reste affiché dans son sélecteur, même s'il ne fait plus partie des choix.
  const rowRoleOptions = (current: string) =>
    ASSIGNABLE_ROLES.filter((r) => r.value === current || creatableRoles.includes(r));

  const [items, setItems] = useState<UserWithRoles[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [form, setForm] = useState(initialForm);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastCreated, setLastCreated] = useState<UserCreateResponse | null>(null);

  const [rowSaving, setRowSaving] = useState<Record<string, boolean>>({});
  const [rowError, setRowError] = useState<Record<string, string>>({});
  const [pendingToggleUserId, setPendingToggleUserId] = useState<string | null>(null);
  // 2026-11-19 — photo d'identité d'un membre du personnel (panneau sous sa ligne).
  const [photoPanelUserId, setPhotoPanelUserId] = useState<string | null>(null);
  const [photoVersions, setPhotoVersions] = useState<Record<string, number>>({});
  const [confirmingPhotoRemoval, setConfirmingPhotoRemoval] = useState(false);

  function reload() {
    if (!currentSchoolId) return;
    setListError(null);
    void users
      .list(currentSchoolId)
      .then(setItems)
      .catch((err) => setListError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSchoolId]);

  async function handleRoleChange(userId: string, roleCode: RoleCode) {
    if (!currentSchoolId) return;
    setRowSaving((prev) => ({ ...prev, [userId]: true }));
    setRowError((prev) => ({ ...prev, [userId]: "" }));
    try {
      await users.update(userId, { school_id: currentSchoolId, role_code: roleCode });
      reload();
    } catch (err) {
      setRowError((prev) => ({ ...prev, [userId]: err instanceof ApiError ? err.message : "Une erreur est survenue." }));
    } finally {
      setRowSaving((prev) => ({ ...prev, [userId]: false }));
    }
  }

  async function handleToggleActive(userId: string, nextActive: boolean) {
    if (!currentSchoolId) return;
    setPendingToggleUserId(null);
    setRowSaving((prev) => ({ ...prev, [userId]: true }));
    setRowError((prev) => ({ ...prev, [userId]: "" }));
    try {
      await users.update(userId, { school_id: currentSchoolId, is_active: nextActive });
      reload();
    } catch (err) {
      setRowError((prev) => ({ ...prev, [userId]: err instanceof ApiError ? err.message : "Une erreur est survenue." }));
    } finally {
      setRowSaving((prev) => ({ ...prev, [userId]: false }));
    }
  }

  function photoChanged(userId: string) {
    setPhotoVersions((prev) => ({ ...prev, [userId]: Date.now() }));
    setConfirmingPhotoRemoval(false);
    reload();
  }

  async function handlePhotoRemove(userId: string) {
    if (!currentSchoolId) return;
    setRowError((prev) => ({ ...prev, [userId]: "" }));
    try {
      await staffPhoto.remove(userId, currentSchoolId);
      photoChanged(userId);
    } catch (err) {
      setRowError((prev) => ({ ...prev, [userId]: err instanceof ApiError ? err.message : "Une erreur est survenue." }));
    }
  }

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!currentSchoolId) return;
    setCreating(true);
    setError(null);
    setLastCreated(null);
    try {
      const created = await users.create({
        email: form.email,
        full_name: form.full_name,
        phone: form.phone || null,
        school_id: currentSchoolId,
        role_code: form.role_code,
      });
      setLastCreated(created);
      setForm(initialForm);
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setCreating(false);
    }
  }

  if (!currentSchoolId) return <p className="text-sm text-slate-500">Chargement...</p>;
  const schoolId = currentSchoolId;
  const columnCount = canManage ? 6 : 5;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Utilisateurs</h1>

      {listError && <p className="text-sm text-red-700">{listError}</p>}

      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-slate-600">
                <span className="sr-only">Photo</span>
              </th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Nom</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Email</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Rôles</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Statut</th>
              {canManage && <th className="px-3 py-2 text-left font-medium text-slate-600">Actions</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items === null ? (
              <tr>
                <td colSpan={columnCount} className="px-3 py-4 text-center text-slate-400">
                  Chargement...
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={columnCount} className="px-3 py-4 text-center text-slate-400">
                  Aucun utilisateur.
                </td>
              </tr>
            ) : (
              items.map((u) => {
                const schoolScopedRoles = u.roles.filter((r) => r.school_id === currentSchoolId);
                const isSelf = currentUser?.id === u.user.id;
                const saving = rowSaving[u.user.id] === true;
                const photoPath = u.user.has_photo ? staffPhoto.path(u.user.id, schoolId) : null;
                return (
                  <Fragment key={u.user.id}>
                  <tr>
                    <td className="px-3 py-2">
                      <PhotoThumb
                        path={photoPath}
                        version={photoVersions[u.user.id] ?? 0}
                        name={u.user.full_name}
                        size="sm"
                        lazy
                        testId={`staff-photo-${u.user.id}`}
                      />
                    </td>
                    <td className="px-3 py-2">{u.user.full_name}</td>
                    <td className="px-3 py-2">{u.user.email}</td>
                    <td className="px-3 py-2">
                      {u.roles.map((r) => ROLE_LABELS[r.role_code] ?? r.role_code).join(", ")}
                    </td>
                    <td className="px-3 py-2">
                      <span className={u.user.is_active ? "text-emerald-700" : "text-slate-400"}>
                        {u.user.is_active ? "Actif" : "Inactif"}
                      </span>
                    </td>
                    {canManage && (
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => {
                            setPhotoPanelUserId(photoPanelUserId === u.user.id ? null : u.user.id);
                            setConfirmingPhotoRemoval(false);
                          }}
                          className="mb-1 rounded border border-slate-300 px-2 py-1 text-xs"
                        >
                          Photo
                        </button>
                        {isSelf ? (
                          <span className="block text-xs text-slate-400">Votre compte</span>
                        ) : (
                          <div className="flex flex-col gap-1">
                            <div className="flex items-center gap-2">
                              {schoolScopedRoles.length === 1 ? (
                                <select
                                  value={schoolScopedRoles[0].role_code}
                                  disabled={saving}
                                  onChange={(e) => handleRoleChange(u.user.id, e.target.value as RoleCode)}
                                  className="rounded border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
                                >
                                  {rowRoleOptions(schoolScopedRoles[0].role_code).map((r) => (
                                    <option key={r.value} value={r.value}>
                                      {r.label}
                                    </option>
                                  ))}
                                </select>
                              ) : (
                                <span className="text-xs text-slate-400">Rôle non modifiable ici</span>
                              )}

                              {pendingToggleUserId === u.user.id ? (
                                <span className="flex items-center gap-1 text-xs">
                                  Confirmer ?
                                  <button
                                    type="button"
                                    disabled={saving}
                                    onClick={() => handleToggleActive(u.user.id, !u.user.is_active)}
                                    className="rounded bg-slate-900 px-2 py-1 text-white disabled:opacity-50"
                                  >
                                    Oui
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => setPendingToggleUserId(null)}
                                    className="rounded border border-slate-300 px-2 py-1"
                                  >
                                    Non
                                  </button>
                                </span>
                              ) : (
                                <button
                                  type="button"
                                  disabled={saving}
                                  onClick={() => setPendingToggleUserId(u.user.id)}
                                  className="rounded border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
                                >
                                  {u.user.is_active ? "Désactiver" : "Activer"}
                                </button>
                              )}
                            </div>
                            {rowError[u.user.id] && <p className="text-xs text-red-700">{rowError[u.user.id]}</p>}
                          </div>
                        )}
                      </td>
                    )}
                  </tr>
                  {canManage && photoPanelUserId === u.user.id && (
                    <tr data-testid={`staff-photo-panel-${u.user.id}`}>
                      <td colSpan={columnCount} className="bg-slate-50 px-3 py-3">
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
                          <PhotoThumb path={photoPath} version={photoVersions[u.user.id] ?? 0} name={u.user.full_name} size="lg" />
                          <div className="flex flex-col gap-2">
                            <p className="text-sm font-semibold text-slate-900">Photo d&apos;identité de {u.user.full_name}</p>
                            <p className="text-xs text-slate-500">
                              Format passeport. Avec l&apos;appareil photo, le visage dans l&apos;ovale, de face, sur un fond clair.
                            </p>
                            <PassportPhotoPicker
                              capture="environment"
                              onPhoto={async (file) => {
                                await staffPhoto.upload(u.user.id, schoolId, file);
                                photoChanged(u.user.id);
                              }}
                            />
                            {photoPath &&
                              (confirmingPhotoRemoval ? (
                                <span className="flex items-center gap-3 text-sm">
                                  <button type="button" onClick={() => void handlePhotoRemove(u.user.id)} className="font-medium text-red-700 underline">
                                    Confirmer le retrait
                                  </button>
                                  <button type="button" onClick={() => setConfirmingPhotoRemoval(false)} className="text-slate-600 underline">
                                    Annuler
                                  </button>
                                </span>
                              ) : (
                                <button type="button" onClick={() => setConfirmingPhotoRemoval(true)} className="self-start text-sm text-red-700 underline">
                                  Retirer la photo
                                </button>
                              ))}
                            {isSelf && rowError[u.user.id] && (
                              <p role="alert" className="text-sm text-red-700">
                                {rowError[u.user.id]}
                              </p>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                  </Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {canManage && (
        <form onSubmit={handleCreate} className="flex flex-col gap-3 rounded border border-dashed border-slate-300 p-4">
          <h2 className="text-sm font-semibold text-slate-900">Nouvel utilisateur</h2>
          <div className="flex flex-wrap gap-3">
            <input
              type="email"
              placeholder="Email"
              value={form.email}
              onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
              required
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <input
              placeholder="Nom complet"
              value={form.full_name}
              onChange={(e) => setForm((prev) => ({ ...prev, full_name: e.target.value }))}
              required
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <input
              placeholder="Téléphone"
              value={form.phone}
              onChange={(e) => setForm((prev) => ({ ...prev, phone: e.target.value }))}
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <select
              value={form.role_code}
              onChange={(e) => setForm((prev) => ({ ...prev, role_code: e.target.value as RoleCode }))}
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            >
              {creatableRoles.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          {!isSchoolAdminHere && (
            <p className="text-xs text-slate-600">
              Les comptes des parents et des élèves sont créés par l&apos;administrateur de l&apos;école.
            </p>
          )}
          <button
            type="submit"
            disabled={creating}
            className="w-fit rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {creating ? "Création..." : "Créer"}
          </button>
          {error && <p className="text-sm text-red-700">{error}</p>}
          {lastCreated && !lastCreated.dev_reset_token && (
            <p className="rounded border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900">
              Un email d&apos;invitation a été envoyé à <strong>{lastCreated.user.email}</strong>{" "}
              pour définir son mot de passe.
            </p>
          )}
          {lastCreated?.dev_reset_token && (
            <div className="rounded border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
              <p className="font-semibold">
                Environnement de développement — l&apos;email d&apos;invitation n&apos;est pas
                réellement envoyé ici (voir app/core/email.py), le lien est affiché ci-dessous pour
                faciliter les tests.
              </p>
              <p className="mt-1">
                Lien de définition du mot de passe pour <strong>{lastCreated.user.email}</strong> :
              </p>
              <code className="mt-1 block break-all rounded bg-white px-2 py-1">{lastCreated.dev_reset_token}</code>
            </div>
          )}
        </form>
      )}
    </div>
  );
}
