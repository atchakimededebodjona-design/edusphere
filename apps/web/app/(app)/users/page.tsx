"use client";

import { useEffect, useState } from "react";
import { PassportPhotoPicker } from "@/components/photos/PassportPhotoPicker";
import { PhotoThumb } from "@/components/photos/PhotoThumb";
import { Button } from "@/components/ui/Button";
import { DataTable, TableSkeleton, type Column } from "@/components/ui/DataTable";
import { ConfirmDialog } from "@/components/ui/Dialog";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { SelectField, TextField, controlClass } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { Badge, Card, EmptyState, PageHeader } from "@/components/ui/Surface";
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
  // Phase 3 (2026-11-24) — activer / désactiver un compte se confirme dans une fenêtre commune.
  const [pendingToggle, setPendingToggle] = useState<UserWithRoles | null>(null);
  // 2026-11-19 — photo d'identité d'un membre du personnel (panneau sous sa ligne).
  const [photoPanelUserId, setPhotoPanelUserId] = useState<string | null>(null);
  const [photoVersions, setPhotoVersions] = useState<Record<string, number>>({});
  const [confirmingPhotoRemoval, setConfirmingPhotoRemoval] = useState<UserWithRoles | null>(null);

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
    setPendingToggle(null);
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
    setConfirmingPhotoRemoval(null);
    reload();
  }

  async function handlePhotoRemove(userId: string) {
    if (!currentSchoolId) return;
    setConfirmingPhotoRemoval(null);
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

  if (!currentSchoolId) return <TableSkeleton />;
  const schoolId = currentSchoolId;
  const photoPathOf = (u: UserWithRoles) => (u.user.has_photo ? staffPhoto.path(u.user.id, schoolId) : null);

  const columns: Column<UserWithRoles>[] = [
    {
      key: "photo",
      header: <span className="sr-only">Photo</span>,
      mobile: "lead",
      cell: (u) => (
        <PhotoThumb
          path={photoPathOf(u)}
          version={photoVersions[u.user.id] ?? 0}
          name={u.user.full_name}
          size="sm"
          lazy
          testId={`staff-photo-${u.user.id}`}
        />
      ),
    },
    {
      key: "name",
      header: "Nom",
      mobile: "title",
      cell: (u) => (
        <span className="font-medium text-slate-900">
          {u.user.full_name}
          {currentUser?.id === u.user.id && <span className="ml-2 text-xs font-normal text-slate-600">(vous)</span>}
        </span>
      ),
    },
    { key: "email", header: "Email", mobile: "full", cell: (u) => <span className="break-all text-slate-700">{u.user.email}</span> },
    { key: "roles", header: "Rôles", cell: (u) => u.roles.map((r) => ROLE_LABELS[r.role_code] ?? r.role_code).join(", ") },
    {
      key: "status",
      header: "Statut",
      cell: (u) => <Badge tone={u.user.is_active ? "success" : "neutral"}>{u.user.is_active ? "Actif" : "Inactif"}</Badge>,
    },
    ...(canManage
      ? [
          {
            key: "actions",
            header: "Actions",
            mobile: "full" as const,
            cell: (u: UserWithRoles) => {
              const schoolScopedRoles = u.roles.filter((r) => r.school_id === currentSchoolId);
              const isSelf = currentUser?.id === u.user.id;
              const saving = rowSaving[u.user.id] === true;
              const photoOpen = photoPanelUserId === u.user.id;
              return (
                <div className="flex flex-col gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      aria-expanded={photoOpen}
                      onClick={() => {
                        setPhotoPanelUserId(photoOpen ? null : u.user.id);
                        setConfirmingPhotoRemoval(null);
                      }}
                    >
                      Photo
                    </Button>
                    {isSelf ? (
                      <span className="text-xs text-slate-600">Votre compte</span>
                    ) : (
                      <>
                        {schoolScopedRoles.length === 1 ? (
                          <select
                            aria-label={`Rôle de ${u.user.full_name}`}
                            value={schoolScopedRoles[0].role_code}
                            disabled={saving}
                            onChange={(e) => handleRoleChange(u.user.id, e.target.value as RoleCode)}
                            className={`${controlClass} !min-h-9 py-1 sm:!w-auto`}
                          >
                            {rowRoleOptions(schoolScopedRoles[0].role_code).map((r) => (
                              <option key={r.value} value={r.value}>
                                {r.label}
                              </option>
                            ))}
                          </select>
                        ) : (
                          <span className="text-xs text-slate-600">Rôle non modifiable ici</span>
                        )}
                        <Button
                          variant={u.user.is_active ? "quietDanger" : "quiet"}
                          size="sm"
                          disabled={saving}
                          onClick={() => setPendingToggle(u)}
                        >
                          {u.user.is_active ? "Désactiver" : "Activer"}
                        </Button>
                      </>
                    )}
                  </div>
                  {!photoOpen && rowError[u.user.id] && (
                    <p role="alert" className="text-xs font-medium text-red-700">
                      {rowError[u.user.id]}
                    </p>
                  )}
                </div>
              );
            },
          },
        ]
      : []),
  ];

  const photoPanel = (u: UserWithRoles) => {
    if (!canManage || photoPanelUserId !== u.user.id) return null;
    const photoPath = photoPathOf(u);
    return (
      <div data-testid={`staff-photo-panel-${u.user.id}`} className="flex flex-col gap-3 sm:flex-row sm:items-start">
        <PhotoThumb path={photoPath} version={photoVersions[u.user.id] ?? 0} name={u.user.full_name} size="lg" />
        <div className="flex flex-col gap-2">
          <p className="text-sm font-semibold text-slate-900">Photo d&apos;identité de {u.user.full_name}</p>
          <p className="text-xs text-slate-600">
            Format passeport. Avec l&apos;appareil photo, le visage dans l&apos;ovale, de face, sur un fond clair.
          </p>
          <PassportPhotoPicker
            capture="environment"
            onPhoto={async (file) => {
              await staffPhoto.upload(u.user.id, schoolId, file);
              photoChanged(u.user.id);
            }}
          />
          {photoPath && (
            <Button variant="quietDanger" size="sm" className="self-start" onClick={() => setConfirmingPhotoRemoval(u)}>
              Retirer la photo
            </Button>
          )}
          {rowError[u.user.id] && (
            <p role="alert" className="text-sm text-red-700">
              {rowError[u.user.id]}
            </p>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Utilisateurs"
        description="Le personnel de l'école et les comptes des familles, avec leurs rôles."
        actions={
          canManage && (
            <a
              href="#nouvel-utilisateur"
              className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 sm:min-h-10"
            >
              <Icon name="plus" className="h-4 w-4" />
              Nouvel utilisateur
            </a>
          )
        }
      />

      {listError && <ErrorRetry message={listError} onRetry={reload} />}

      {items === null ? (
        listError ? null : <TableSkeleton />
      ) : (
        <DataTable
          caption="Utilisateurs"
          columns={columns}
          rows={items}
          rowKey={(u) => u.user.id}
          rowTone={(u) => (u.user.is_active ? undefined : "muted")}
          after={photoPanel}
          empty={<EmptyState icon="users" title="Aucun utilisateur." />}
        />
      )}

      {canManage && (
        <form id="nouvel-utilisateur" onSubmit={handleCreate} className="scroll-mt-20">
          <Card className="flex flex-col gap-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Nouvel utilisateur</h2>
              <p className="text-sm text-slate-600">Un email d&apos;invitation lui permettra de choisir son mot de passe.</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <TextField
                label="Email"
                type="email"
                value={form.email}
                onChange={(e) => setForm((prev) => ({ ...prev, email: e.target.value }))}
                required
                autoComplete="off"
              />
              <TextField
                label="Nom complet"
                value={form.full_name}
                onChange={(e) => setForm((prev) => ({ ...prev, full_name: e.target.value }))}
                required
                autoComplete="off"
              />
              <TextField
                label="Téléphone"
                type="tel"
                value={form.phone}
                onChange={(e) => setForm((prev) => ({ ...prev, phone: e.target.value }))}
                hint="Facultatif"
              />
              <SelectField
                label="Rôle"
                value={form.role_code}
                onChange={(e) => setForm((prev) => ({ ...prev, role_code: e.target.value as RoleCode }))}
                hint={!isSchoolAdminHere ? "Les comptes des parents et des élèves sont créés par l'administrateur de l'école." : undefined}
              >
                {creatableRoles.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </SelectField>
            </div>
            {error && (
              <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
                {error}
              </p>
            )}
            {lastCreated && !lastCreated.dev_reset_token && (
              <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
                Un email d&apos;invitation a été envoyé à <strong>{lastCreated.user.email}</strong> pour définir son mot de passe.
              </p>
            )}
            {lastCreated?.dev_reset_token && (
              <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
                <p className="font-semibold">
                  Environnement de développement — l&apos;email d&apos;invitation n&apos;est pas réellement envoyé ici (voir
                  app/core/email.py), le lien est affiché ci-dessous pour faciliter les tests.
                </p>
                <p className="mt-1">
                  Lien de définition du mot de passe pour <strong>{lastCreated.user.email}</strong> :
                </p>
                <code className="mt-1 block break-all rounded bg-white px-2 py-1">{lastCreated.dev_reset_token}</code>
              </div>
            )}
            <Button type="submit" icon="plus" disabled={creating} className="self-start">
              {creating ? "Création..." : "Créer"}
            </Button>
          </Card>
        </form>
      )}

      <ConfirmDialog
        open={pendingToggle !== null}
        title={pendingToggle?.user.is_active ? "Désactiver ce compte ?" : "Réactiver ce compte ?"}
        message={
          pendingToggle?.user.is_active ? (
            <>
              <strong>{pendingToggle.user.full_name}</strong> ne pourra plus se connecter. Ses données sont gardées et le compte peut être
              réactivé à tout moment.
            </>
          ) : (
            <>
              <strong>{pendingToggle?.user.full_name}</strong> pourra de nouveau se connecter avec son mot de passe.
            </>
          )
        }
        confirmLabel={pendingToggle?.user.is_active ? "Désactiver" : "Activer"}
        tone={pendingToggle?.user.is_active ? "danger" : "primary"}
        onConfirm={() => pendingToggle && void handleToggleActive(pendingToggle.user.id, !pendingToggle.user.is_active)}
        onCancel={() => setPendingToggle(null)}
      />

      <ConfirmDialog
        open={confirmingPhotoRemoval !== null}
        title="Retirer la photo ?"
        message={
          <>
            La photo d&apos;identité de <strong>{confirmingPhotoRemoval?.user.full_name}</strong> sera supprimée. Les initiales
            s&apos;afficheront à sa place.
          </>
        }
        confirmLabel="Retirer la photo"
        tone="danger"
        onConfirm={() => confirmingPhotoRemoval && void handlePhotoRemove(confirmingPhotoRemoval.user.id)}
        onCancel={() => setConfirmingPhotoRemoval(null)}
      />
    </div>
  );
}
