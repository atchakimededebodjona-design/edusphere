"use client";

import { useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { toErrorMessage, useAsyncData } from "@/lib/api/useAsyncData";
import { enrollPartnerSchool, listPartnerSchools } from "@/lib/partners/client";
import { ExistingOrganizationEnroll } from "./ExistingOrganizationEnroll";

const SLUG_PATTERN = /^[a-z0-9-]+$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type FormState = {
  orgName: string;
  orgSlug: string;
  orgCountry: string;
  schoolName: string;
  adminFullName: string;
  adminEmail: string;
  adminPassword: string;
};

const initialState: FormState = {
  orgName: "",
  orgSlug: "",
  orgCountry: "TG",
  schoolName: "",
  adminFullName: "",
  adminEmail: "",
  adminPassword: "",
};

function validate(form: FormState): string | null {
  if (form.orgName.trim().length < 2 || form.schoolName.trim().length < 2) {
    return "Les noms de l'organisation et de l'école doivent comporter au moins 2 caractères.";
  }
  if (!SLUG_PATTERN.test(form.orgSlug) || form.orgSlug.length < 2) {
    return "Identifiant d'organisation : lettres minuscules, chiffres et tirets uniquement.";
  }
  if (!/^[A-Za-z]{2}$/.test(form.orgCountry)) return "Code pays sur 2 lettres (ex. TG).";
  if (form.adminFullName.trim().length < 2) return "Nom de l'administrateur requis.";
  if (!EMAIL_PATTERN.test(form.adminEmail.trim())) return "Email de l'administrateur invalide.";
  if (form.adminPassword.length < 8) return "Le mot de passe doit comporter au moins 8 caractères.";
  return null;
}

// PR #17 — inscription minimale d'une école par le partenaire. Le partenaire n'est jamais
// transmis par le client : l'API le dérive du compte connecté.
function EnrollSchoolForm({ onEnrolled }: { onEnrolled: () => void }) {
  const [form, setForm] = useState<FormState>(initialState);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const set = (key: keyof FormState) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    const problem = validate(form);
    if (problem) {
      setError(problem);
      return;
    }
    setSubmitting(true);
    try {
      const created = await enrollPartnerSchool({
        organization: {
          name: form.orgName.trim(),
          slug: form.orgSlug,
          country_code: form.orgCountry.toUpperCase(),
          timezone: "Africa/Lome",
          currency: "XOF",
        },
        school: {
          name: form.schoolName.trim(),
          slug: "principale",
          address: null,
          phone: null,
          email: null,
          timezone: "Africa/Lome",
          currency: "XOF",
        },
        admin: {
          full_name: form.adminFullName.trim(),
          email: form.adminEmail.trim(),
          phone: null,
          password: form.adminPassword,
        },
      });
      setSuccess(`École « ${created.school.name} » inscrite. L'administrateur peut maintenant se connecter.`);
      setForm(initialState);
      onEnrolled();
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  const input = "rounded border border-slate-300 px-3 py-2 text-sm";
  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded border border-slate-200 p-4">
      <h2 className="font-semibold text-slate-900">Inscrire une nouvelle école</h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <input className={input} placeholder="Nom de l'organisation" value={form.orgName} onChange={set("orgName")} />
        <input className={input} placeholder="Identifiant (ex. groupe-scolaire-x)" value={form.orgSlug} onChange={set("orgSlug")} />
        <input className={input} placeholder="Pays (ex. TG)" value={form.orgCountry} onChange={set("orgCountry")} />
        <input className={input} placeholder="Nom de l'école" value={form.schoolName} onChange={set("schoolName")} />
        <input className={input} placeholder="Nom de l'administrateur" value={form.adminFullName} onChange={set("adminFullName")} />
        <input className={input} type="email" placeholder="Email de l'administrateur" value={form.adminEmail} onChange={set("adminEmail")} />
        <input
          className={input}
          type="password"
          autoComplete="new-password"
          placeholder="Mot de passe initial (8 caractères min.)"
          value={form.adminPassword}
          onChange={set("adminPassword")}
        />
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      {success && <p className="text-sm text-emerald-700">{success}</p>}
      <div>
        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
        >
          {submitting ? "Inscription..." : "Inscrire l'école"}
        </button>
      </div>
    </form>
  );
}

export default function PartnerSchoolsPage() {
  const { data, error, isLoading, retry } = useAsyncData(listPartnerSchools, []);
  // PR #19 — « Nouvelle organisation » (parcours historique) ou « Organisation existante » (ajout
  // d'un établissement dans une organisation de VOTRE périmètre, vérifié côté API).
  const [mode, setMode] = useState<"new" | "existing">("new");

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Mes écoles</h1>
        <p className="text-sm text-slate-600">Écoles inscrites via votre compte partenaire.</p>
      </div>
      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-slate-700">+ Inscrire une école</legend>
        <div className="flex flex-wrap gap-4 text-sm text-slate-700">
          <label className="flex items-center gap-2">
            <input type="radio" name="partner-enrollment-mode" checked={mode === "new"} onChange={() => setMode("new")} />
            Nouvelle organisation
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="partner-enrollment-mode"
              checked={mode === "existing"}
              onChange={() => setMode("existing")}
            />
            Organisation existante
          </label>
        </div>
      </fieldset>
      {mode === "new" ? <EnrollSchoolForm onEnrolled={retry} /> : <ExistingOrganizationEnroll onEnrolled={retry} />}
      {error && <ErrorRetry message={error} onRetry={retry} />}
      {isLoading && !error && <p className="text-sm text-slate-400">Chargement...</p>}
      {data &&
        (data.length === 0 ? (
          <p className="text-sm text-slate-500">Aucune école inscrite pour le moment.</p>
        ) : (
          <div className="overflow-x-auto rounded border border-slate-200">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">École</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Organisation</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Élèves</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Inscrite le</th>
                  <th className="px-3 py-2 text-left font-medium text-slate-600">Statut</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.map((school) => (
                  <tr key={school.school_id}>
                    <td className="px-3 py-2 text-slate-700">{school.school_name}</td>
                    <td className="px-3 py-2 text-slate-700">{school.organization_name}</td>
                    <td className="px-3 py-2 text-slate-700">{school.student_count}</td>
                    <td className="px-3 py-2 text-slate-700">{new Date(school.enrolled_at).toLocaleDateString("fr-FR")}</td>
                    <td className="px-3 py-2 text-slate-700">{school.status === "ACTIVE" ? "Active" : school.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
    </div>
  );
}
