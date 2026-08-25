"use client";

import { useEffect, useMemo, useState } from "react";
import { ApiError } from "@/lib/api/client";
import {
  guardians as guardiansClient,
  studentGuardians,
  type Guardian,
  type GuardianRelationship,
  type StudentGuardian,
} from "@/lib/students/client";

const RELATIONSHIP_LABELS: Record<GuardianRelationship, string> = {
  father: "Père",
  mother: "Mère",
  guardian: "Tuteur",
  other: "Autre",
};

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
}: {
  studentId: string;
  schoolId: string;
  canManage: boolean;
}) {
  const [directory, setDirectory] = useState<Guardian[] | null>(null);
  const [links, setLinks] = useState<StudentGuardian[] | null>(null);
  const [selectedGuardianId, setSelectedGuardianId] = useState("");
  const [newGuardian, setNewGuardian] = useState(newGuardianInitial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void guardiansClient.list(schoolId).then(setDirectory);
    void studentGuardians.list(studentId).then(setLinks);
  }, [schoolId, studentId]);

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

  if (directory === null || links === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-slate-900">Tuteurs</h2>
      <ul className="flex flex-col gap-1">
        {links.map((link) => {
          const guardian = directory.find((g) => g.id === link.guardian_id);
          return (
            <li key={link.id} className="flex items-center justify-between rounded border border-slate-200 px-3 py-1.5 text-sm">
              <span>
                {guardian?.full_name ?? link.guardian_id} — {guardian ? RELATIONSHIP_LABELS[guardian.relationship_type] : ""}
                {link.is_primary_contact && " (contact principal)"}
                {guardian?.phone && ` — ${guardian.phone}`}
              </span>
              {canManage && (
                <button type="button" onClick={() => handleDetach(link.id)} disabled={busy} className="text-xs text-red-700 underline">
                  Détacher
                </button>
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
