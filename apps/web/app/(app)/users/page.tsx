"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/useAuth";
import { ASSIGNABLE_ROLES, users, type RoleCode, type UserCreateResponse, type UserWithRoles } from "@/lib/users/client";

const ROLE_LABELS: Record<string, string> = Object.fromEntries(ASSIGNABLE_ROLES.map((r) => [r.value, r.label]));

const initialForm = {
  email: "",
  full_name: "",
  phone: "",
  role_code: "TEACHER" as RoleCode,
};

export default function UsersPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("users.manage");

  const [items, setItems] = useState<UserWithRoles[] | null>(null);
  const [form, setForm] = useState(initialForm);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastCreated, setLastCreated] = useState<UserCreateResponse | null>(null);

  useEffect(() => {
    if (!currentSchoolId) return;
    void users.list(currentSchoolId).then(setItems);
  }, [currentSchoolId]);

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
      void users.list(currentSchoolId).then(setItems);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setCreating(false);
    }
  }

  if (!currentSchoolId) return <p className="text-sm text-slate-500">Chargement...</p>;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Utilisateurs</h1>

      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Nom</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Email</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Rôles</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items === null ? (
              <tr>
                <td colSpan={3} className="px-3 py-4 text-center text-slate-400">
                  Chargement...
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={3} className="px-3 py-4 text-center text-slate-400">
                  Aucun utilisateur.
                </td>
              </tr>
            ) : (
              items.map((u) => (
                <tr key={u.user.id}>
                  <td className="px-3 py-2">{u.user.full_name}</td>
                  <td className="px-3 py-2">{u.user.email}</td>
                  <td className="px-3 py-2">
                    {u.roles.map((r) => ROLE_LABELS[r.role_code] ?? r.role_code).join(", ")}
                  </td>
                </tr>
              ))
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
              {ASSIGNABLE_ROLES.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={creating}
            className="w-fit rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {creating ? "Création..." : "Créer"}
          </button>
          {error && <p className="text-sm text-red-700">{error}</p>}
          {lastCreated?.dev_reset_token && (
            <div className="rounded border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900">
              <p className="font-semibold">
                Environnement de développement uniquement — en production, un email serait envoyé.
              </p>
              <p className="mt-1">
                Token de définition du mot de passe pour <strong>{lastCreated.user.email}</strong> :
              </p>
              <code className="mt-1 block break-all rounded bg-white px-2 py-1">{lastCreated.dev_reset_token}</code>
            </div>
          )}
        </form>
      )}
    </div>
  );
}
