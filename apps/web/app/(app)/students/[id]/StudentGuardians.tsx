"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import {
  guardians as guardiansClient,
  studentGuardians,
  type Guardian,
  type GuardianRelationship,
  type StudentGuardian,
} from "@/lib/students/client";
import { users as usersClient, type UserWithRoles } from "@/lib/users/client";

const RELATIONSHIP_LABELS: Record<GuardianRelationship, string> = {
  father: "Père",
  mother: "Mère",
  guardian: "Tuteur",
  other: "Autre",
};

// Sprint 1.11 — liaison d'un Guardian existant à un compte utilisateur PARENT existant (PATCH
// /guardians/{id}, endpoint déjà validé — voir students/client.ts::guardians.update). Panneau
// isolé (mêmes conventions que AppreciationCell dans grades/GradeBookPanel.tsx : état local,
// pas de nouvelle abstraction de type "modal") pour ne pas alourdir la liste principale.
function GuardianLinkPanel({
  guardian,
  parentUsers,
  parentUsersLoading,
  parentUsersError,
  onLinked,
  onCancel,
}: {
  guardian: Guardian;
  parentUsers: UserWithRoles[] | null;
  parentUsersLoading: boolean;
  parentUsersError: string | null;
  onLinked: () => Promise<void>;
  onCancel: () => void;
}) {
  const [selectedUserId, setSelectedUserId] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [linking, setLinking] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);

  const parentOptions = useMemo(
    () => (parentUsers ?? []).filter((u) => u.roles.some((r) => r.role_code === "PARENT")),
    [parentUsers],
  );
  const selected = parentOptions.find((u) => u.user.id === selectedUserId) ?? null;

  async function handleConfirm() {
    if (!selected) return;
    setLinking(true);
    setLinkError(null);
    try {
      await guardiansClient.update(guardian.id, { user_id: selected.user.id });
      await onLinked();
    } catch (err) {
      setLinkError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
      setConfirming(false);
    } finally {
      setLinking(false);
    }
  }

  return (
    <div className="mt-2 flex flex-col gap-2 rounded border border-dashed border-slate-300 bg-slate-50 p-3 text-sm">
      <p className="font-medium text-slate-700">Lier « {guardian.full_name} » à un compte parent</p>

      {parentUsersLoading && <p className="text-xs text-slate-400">Chargement des comptes parent...</p>}
      {parentUsersError && <p className="text-xs text-red-700">{parentUsersError}</p>}

      {!parentUsersLoading && !parentUsersError && parentOptions.length === 0 && (
        <p className="text-xs text-slate-500">Aucun compte parent disponible dans cette école.</p>
      )}

      {!parentUsersLoading && !parentUsersError && parentOptions.length > 0 && !confirming && (
        <>
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Sélectionner un compte parent
            <select
              value={selectedUserId}
              onChange={(e) => setSelectedUserId(e.target.value)}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              <option value="">—</option>
              {parentOptions.map((u) => (
                <option key={u.user.id} value={u.user.id}>
                  {u.user.full_name} — {u.user.email}
                </option>
              ))}
            </select>
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setConfirming(true)}
              disabled={!selectedUserId}
              className="rounded bg-slate-900 px-3 py-1.5 text-xs text-white disabled:opacity-50"
            >
              Lier le compte
            </button>
            <button type="button" onClick={onCancel} className="rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100">
              Annuler
            </button>
          </div>
        </>
      )}

      {confirming && selected && (
        <>
          <p className="text-xs text-slate-700">
            Voulez-vous lier ce tuteur à « {selected.user.full_name} — {selected.user.email} » ?
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => void handleConfirm()}
              disabled={linking}
              className="rounded bg-slate-900 px-3 py-1.5 text-xs text-white disabled:opacity-50"
            >
              {linking ? "Liaison..." : "Confirmer la liaison"}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              disabled={linking}
              className="rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100 disabled:opacity-50"
            >
              Annuler
            </button>
          </div>
        </>
      )}

      {linkError && <p className="text-xs text-red-700">{linkError}</p>}
    </div>
  );
}

const newGuardianInitial = {
  full_name: "",
  relationship_type: "guardian" as GuardianRelationship,
  phone: "",
  email: "",
  is_emergency_contact: false,
};

export function StudentGuardians({
  studentId,
  schoolId,
  canManage,
  canLinkParentAccount,
}: {
  studentId: string;
  schoolId: string;
  canManage: boolean;
  // Sprint 1.11 hotfix — distinct de `canManage` (students.manage) : la liaison à un compte
  // parent appelle en plus GET /users, qui exige `users.read`. Calculé par l'appelant (page.tsx,
  // déjà en possession de `permissions` via useAuth) plutôt que recalculé ici, pour ne pas
  // dupliquer la lecture des permissions à deux endroits.
  canLinkParentAccount: boolean;
}) {
  const [directory, setDirectory] = useState<Guardian[] | null>(null);
  const [links, setLinks] = useState<StudentGuardian[] | null>(null);
  const [selectedGuardianId, setSelectedGuardianId] = useState("");
  const [newGuardian, setNewGuardian] = useState(newGuardianInitial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Sprint 1.11 — liaison Guardian -> compte PARENT. `parentUsers` chargé une seule fois, à la
  // demande (jamais au chargement de la page — un appelant avec seulement `students.manage`,
  // ex. STAFF, peut ne pas avoir `users.read` ; voir la gestion d'erreur 403 ci-dessous), puis
  // réutilisé pour chaque tuteur lié dans la même session.
  const [linkingGuardianId, setLinkingGuardianId] = useState<string | null>(null);
  const [parentUsers, setParentUsers] = useState<UserWithRoles[] | null>(null);
  const [parentUsersLoading, setParentUsersLoading] = useState(false);
  const [parentUsersError, setParentUsersError] = useState<string | null>(null);

  const loadAll = useCallback(() => {
    setLoadError(null);
    Promise.all([guardiansClient.list(schoolId), studentGuardians.list(studentId)])
      .then(([directoryResult, linksResult]) => {
        setDirectory(directoryResult);
        setLinks(linksResult);
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [schoolId, studentId]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  function handleOpenLinkPanel(guardianId: string) {
    setLinkingGuardianId(guardianId);
    if (parentUsers === null && !parentUsersLoading) {
      setParentUsersLoading(true);
      setParentUsersError(null);
      usersClient
        .list(schoolId)
        .then(setParentUsers)
        .catch((err) => setParentUsersError(err instanceof ApiError ? err.message : "Une erreur est survenue."))
        .finally(() => setParentUsersLoading(false));
    }
  }

  async function handleGuardianLinked() {
    // Recharge depuis l'API (pas seulement la réponse du PATCH) pour confirmer la persistance
    // réelle — même motif que grades/GradeBookPanel.tsx::AppreciationCell.
    const refreshedDirectory = await guardiansClient.list(schoolId);
    setDirectory(refreshedDirectory);
    setLinkingGuardianId(null);
  }

  const available = useMemo(
    () => (directory ?? []).filter((g) => !links?.some((l) => l.guardian_id === g.id)),
    [directory, links],
  );

  async function handleAttachExisting(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedGuardianId) return;
    setBusy(true);
    setError(null);
    try {
      const link = await studentGuardians.attach(studentId, { guardian_id: selectedGuardianId });
      setLinks((prev) => [...(prev ?? []), link]);
      setSelectedGuardianId("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateAndAttach(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const guardian = await guardiansClient.create({
        school_id: schoolId,
        full_name: newGuardian.full_name,
        relationship_type: newGuardian.relationship_type,
        phone: newGuardian.phone || null,
        email: newGuardian.email || null,
        is_emergency_contact: newGuardian.is_emergency_contact,
      });
      setDirectory((prev) => [...(prev ?? []), guardian]);
      const link = await studentGuardians.attach(studentId, { guardian_id: guardian.id });
      setLinks((prev) => [...(prev ?? []), link]);
      setNewGuardian(newGuardianInitial);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDetach(linkId: string) {
    setBusy(true);
    setError(null);
    try {
      await studentGuardians.detach(studentId, linkId);
      setLinks((prev) => (prev ?? []).filter((l) => l.id !== linkId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  if (loadError) return <ErrorRetry message={loadError} onRetry={loadAll} />;
  if (directory === null || links === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-slate-900">Tuteurs</h2>
      <ul className="flex flex-col gap-1">
        {links.map((link) => {
          const guardian = directory.find((g) => g.id === link.guardian_id);
          const linkedParent = guardian?.user_id
            ? (parentUsers ?? []).find((u) => u.user.id === guardian.user_id)
            : null;
          return (
            <li key={link.id} className="rounded border border-slate-200 px-3 py-1.5 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span>
                  {guardian?.full_name ?? link.guardian_id} — {guardian ? RELATIONSHIP_LABELS[guardian.relationship_type] : ""}
                  {link.is_primary_contact && " (contact principal)"}
                  {guardian?.phone && ` — ${guardian.phone}`}
                </span>
                <div className="flex items-center gap-2">
                  {guardian?.user_id ? (
                    <span className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-800">
                      Compte parent lié{linkedParent && ` (${linkedParent.user.email})`}
                    </span>
                  ) : (
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">Sans compte</span>
                  )}
                  {canLinkParentAccount && guardian && !guardian.user_id && (
                    <button
                      type="button"
                      onClick={() => handleOpenLinkPanel(guardian.id)}
                      className="text-xs text-slate-700 underline"
                    >
                      Lier à un compte parent
                    </button>
                  )}
                  {canManage && (
                    <button type="button" onClick={() => handleDetach(link.id)} disabled={busy} className="text-xs text-red-700 underline">
                      Détacher
                    </button>
                  )}
                </div>
              </div>
              {guardian && linkingGuardianId === guardian.id && (
                <GuardianLinkPanel
                  guardian={guardian}
                  parentUsers={parentUsers}
                  parentUsersLoading={parentUsersLoading}
                  parentUsersError={parentUsersError}
                  onLinked={handleGuardianLinked}
                  onCancel={() => setLinkingGuardianId(null)}
                />
              )}
            </li>
          );
        })}
        {links.length === 0 && <li className="text-sm text-slate-400">Aucun tuteur rattaché.</li>}
      </ul>

      {canManage && (
        <div className="flex flex-col gap-3">
          {available.length > 0 && (
            <form onSubmit={handleAttachExisting} className="flex items-end gap-3">
              <label className="flex flex-col gap-1 text-xs text-slate-600">
                Rattacher un tuteur existant
                <select
                  value={selectedGuardianId}
                  onChange={(e) => setSelectedGuardianId(e.target.value)}
                  required
                  className="rounded border border-slate-300 px-2 py-1 text-sm"
                >
                  <option value="">—</option>
                  {available.map((g) => (
                    <option key={g.id} value={g.id}>
                      {g.full_name}
                    </option>
                  ))}
                </select>
              </label>
              <button type="submit" disabled={busy} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
                Rattacher
              </button>
            </form>
          )}

          <form onSubmit={handleCreateAndAttach} className="flex flex-wrap items-end gap-3 rounded border border-dashed border-slate-300 p-3">
            <span className="w-full text-xs font-medium text-slate-600">Nouveau tuteur</span>
            <input
              placeholder="Nom complet"
              value={newGuardian.full_name}
              onChange={(e) => setNewGuardian((prev) => ({ ...prev, full_name: e.target.value }))}
              required
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
            <select
              value={newGuardian.relationship_type}
              onChange={(e) => setNewGuardian((prev) => ({ ...prev, relationship_type: e.target.value as GuardianRelationship }))}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              {Object.entries(RELATIONSHIP_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
            <input
              placeholder="Téléphone"
              value={newGuardian.phone}
              onChange={(e) => setNewGuardian((prev) => ({ ...prev, phone: e.target.value }))}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
            <input
              type="email"
              placeholder="Email"
              value={newGuardian.email}
              onChange={(e) => setNewGuardian((prev) => ({ ...prev, email: e.target.value }))}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
            <label className="flex items-center gap-1 text-xs text-slate-600">
              <input
                type="checkbox"
                checked={newGuardian.is_emergency_contact}
                onChange={(e) => setNewGuardian((prev) => ({ ...prev, is_emergency_contact: e.target.checked }))}
              />
              Contact d&apos;urgence
            </label>
            <button type="submit" disabled={busy} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
              Créer et rattacher
            </button>
          </form>
        </div>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  );
}
