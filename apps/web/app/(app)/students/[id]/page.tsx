"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/useAuth";
import { students, type Sex, type Student, type StudentStatus } from "@/lib/students/client";
import { StudentPhoto } from "@/app/(app)/students/[id]/StudentPhoto";
import { StudentGuardians } from "@/app/(app)/students/[id]/StudentGuardians";
import { StudentEnrollments } from "@/app/(app)/students/[id]/StudentEnrollments";
import { StudentDocuments } from "@/app/(app)/students/[id]/StudentDocuments";

const STATUS_OPTIONS: { value: StudentStatus; label: string }[] = [
  { value: "ACTIVE", label: "Actif" },
  { value: "INACTIVE", label: "Inactif" },
  { value: "GRADUATED", label: "Diplômé" },
  { value: "WITHDRAWN", label: "Retiré" },
  { value: "TRANSFERRED", label: "Transféré" },
];

export default function StudentDetailPage() {
  const params = useParams<{ id: string }>();
  const studentId = params.id;
  const { permissions } = useAuth();
  const canManage = permissions.includes("students.manage");

  const [student, setStudent] = useState<Student | null>(null);
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    matricule: "",
    date_of_birth: "",
    sex: "F" as Sex,
    place_of_birth: "",
    address: "",
    status: "ACTIVE" as StudentStatus,
    status_change_reason: "",
  });
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void students.get(studentId).then((s) => {
      setStudent(s);
      setForm({
        first_name: s.first_name,
        last_name: s.last_name,
        matricule: s.matricule,
        date_of_birth: s.date_of_birth,
        sex: s.sex,
        place_of_birth: s.place_of_birth ?? "",
        address: s.address ?? "",
        status: s.status,
        status_change_reason: "",
      });
    });
  }, [studentId]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSaveStatus("saving");
    setError(null);
    try {
      const updated = await students.update(studentId, form);
      setStudent(updated);
      setForm((prev) => ({ ...prev, status_change_reason: "" }));
      setSaveStatus("saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
      setSaveStatus("error");
    }
  }

  if (!student) return <p className="text-sm text-slate-500">Chargement...</p>;

  return (
    <div className="flex max-w-2xl flex-col gap-8">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">
          {student.last_name} {student.first_name}
        </h1>
        <p className="text-sm text-slate-500">Matricule {student.matricule}</p>
      </div>

      <StudentPhoto studentId={studentId} canManage={canManage} />

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold text-slate-900">Informations</h2>
        <div className="flex flex-wrap gap-3">
          <input
            placeholder="Matricule"
            value={form.matricule}
            onChange={(e) => setForm((prev) => ({ ...prev, matricule: e.target.value }))}
            disabled={!canManage}
            className="rounded border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
          />
          <input
            placeholder="Prénom"
            value={form.first_name}
            onChange={(e) => setForm((prev) => ({ ...prev, first_name: e.target.value }))}
            disabled={!canManage}
            className="rounded border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
          />
          <input
            placeholder="Nom"
            value={form.last_name}
            onChange={(e) => setForm((prev) => ({ ...prev, last_name: e.target.value }))}
            disabled={!canManage}
            className="rounded border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
          />
          <input
            type="date"
            value={form.date_of_birth}
            onChange={(e) => setForm((prev) => ({ ...prev, date_of_birth: e.target.value }))}
            disabled={!canManage}
            className="rounded border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
          />
          <select
            value={form.sex}
            onChange={(e) => setForm((prev) => ({ ...prev, sex: e.target.value as Sex }))}
            disabled={!canManage}
            className="rounded border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
          >
            <option value="F">Féminin</option>
            <option value="M">Masculin</option>
          </select>
          <input
            placeholder="Lieu de naissance"
            value={form.place_of_birth}
            onChange={(e) => setForm((prev) => ({ ...prev, place_of_birth: e.target.value }))}
            disabled={!canManage}
            className="rounded border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
          />
          <input
            placeholder="Adresse"
            value={form.address}
            onChange={(e) => setForm((prev) => ({ ...prev, address: e.target.value }))}
            disabled={!canManage}
            className="rounded border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
          />
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Statut
            <select
              value={form.status}
              onChange={(e) => setForm((prev) => ({ ...prev, status: e.target.value as StudentStatus }))}
              disabled={!canManage}
              className="rounded border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-1 flex-col gap-1 text-xs text-slate-600">
            Motif du changement de statut (si applicable)
            <input
              value={form.status_change_reason}
              onChange={(e) => setForm((prev) => ({ ...prev, status_change_reason: e.target.value }))}
              disabled={!canManage}
              className="rounded border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
            />
          </label>
        </div>

        {canManage && (
          <button
            type="submit"
            disabled={saveStatus === "saving"}
            className="w-fit rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {saveStatus === "saving" ? "Enregistrement..." : "Enregistrer"}
          </button>
        )}
        {saveStatus === "saved" && <p className="text-sm text-green-700">Modifications enregistrées.</p>}
        {error && <p className="text-sm text-red-700">{error}</p>}
      </form>

      <StudentGuardians studentId={studentId} schoolId={student.school_id} canManage={canManage} />
      <StudentEnrollments studentId={studentId} schoolId={student.school_id} canManage={canManage} />
      <StudentDocuments studentId={studentId} canManage={canManage} />
    </div>
  );
}
