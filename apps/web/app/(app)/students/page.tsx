"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/useAuth";
import { students, type Sex, type Student, type StudentStatus } from "@/lib/students/client";

const STATUS_LABELS: Record<StudentStatus, string> = {
  ACTIVE: "Actif",
  INACTIVE: "Inactif",
  GRADUATED: "Diplômé",
  WITHDRAWN: "Retiré",
  TRANSFERRED: "Transféré",
};

const initialForm = {
  matricule: "",
  first_name: "",
  last_name: "",
  date_of_birth: "",
  sex: "F" as Sex,
  place_of_birth: "",
  address: "",
};

export default function StudentsPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("students.manage");

  const [items, setItems] = useState<Student[] | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StudentStatus | "">("");
  const [form, setForm] = useState(initialForm);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentSchoolId) return;
    void students.list(currentSchoolId, { search: search || undefined, status: statusFilter || undefined }).then(setItems);
  }, [currentSchoolId, search, statusFilter]);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    if (!currentSchoolId) return;
    setCreating(true);
    setError(null);
    try {
      const created = await students.create({ school_id: currentSchoolId, ...form });
      setItems((prev) => [...(prev ?? []), created]);
      setForm(initialForm);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setCreating(false);
    }
  }

  if (!currentSchoolId) return <p className="text-sm text-slate-500">Chargement...</p>;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Élèves</h1>

      <div className="flex flex-wrap gap-3">
        <input
          placeholder="Rechercher (nom, matricule)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-64 rounded border border-slate-300 px-3 py-2 text-sm"
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StudentStatus | "")}
          className="rounded border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="">Tous statuts</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Matricule</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Nom</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Statut</th>
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
                  Aucun élève.
                </td>
              </tr>
            ) : (
              items.map((s) => (
                <tr key={s.id} className="hover:bg-slate-50">
                  <td className="px-3 py-2">
                    <Link href={`/students/${s.id}`} className="text-slate-900 underline">
                      {s.matricule}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    {s.last_name} {s.first_name}
                  </td>
                  <td className="px-3 py-2">{STATUS_LABELS[s.status]}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {canManage && (
        <form onSubmit={handleCreate} className="flex flex-col gap-3 rounded border border-dashed border-slate-300 p-4">
          <h2 className="text-sm font-semibold text-slate-900">Nouvel élève</h2>
          <div className="flex flex-wrap gap-3">
            <input
              placeholder="Matricule"
              value={form.matricule}
              onChange={(e) => setForm((prev) => ({ ...prev, matricule: e.target.value }))}
              required
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <input
              placeholder="Prénom"
              value={form.first_name}
              onChange={(e) => setForm((prev) => ({ ...prev, first_name: e.target.value }))}
              required
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <input
              placeholder="Nom"
              value={form.last_name}
              onChange={(e) => setForm((prev) => ({ ...prev, last_name: e.target.value }))}
              required
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <input
              type="date"
              value={form.date_of_birth}
              onChange={(e) => setForm((prev) => ({ ...prev, date_of_birth: e.target.value }))}
              required
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <select
              value={form.sex}
              onChange={(e) => setForm((prev) => ({ ...prev, sex: e.target.value as Sex }))}
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="F">Féminin</option>
              <option value="M">Masculin</option>
            </select>
            <input
              placeholder="Lieu de naissance"
              value={form.place_of_birth}
              onChange={(e) => setForm((prev) => ({ ...prev, place_of_birth: e.target.value }))}
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <input
              placeholder="Adresse"
              value={form.address}
              onChange={(e) => setForm((prev) => ({ ...prev, address: e.target.value }))}
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
          <button
            type="submit"
            disabled={creating}
            className="w-fit rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {creating ? "Ajout..." : "Ajouter"}
          </button>
          {error && <p className="text-sm text-red-700">{error}</p>}
        </form>
      )}
    </div>
  );
}
