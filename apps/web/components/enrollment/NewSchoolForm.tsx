"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api/client";
import type { SchoolAddPayload, SchoolAdded } from "@/lib/platform/client";

// PR #19 — formulaire PARTAGÉ « nouvel établissement + son administrateur », utilisé par les deux
// parcours « organisation existante » (Platform Owner et Partenaire). Il ne contient AUCUN champ
// d'organisation : l'organisation est déjà choisie par le parent et ne peut pas être recréée ici.
// Les contrôles (doublons, périmètre, permissions) sont faits par l'API ; ceux d'ici ne servent
// qu'au confort de saisie.
//
// PR #20 — option « administrateur existant » : seul l'email est envoyé. L'API réutilise le compte
// UNIQUEMENT s'il administre déjà (SCHOOL_ADMIN ou DIRECTOR) cette même organisation ; le compte
// n'est jamais modifié (mot de passe inchangé). Sinon refus générique (409). Cette case ne fait que
// masquer des champs : elle ne contourne aucun contrôle.

const SLUG_PATTERN = /^[a-z0-9-]+$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function slugify(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 255);
}

function normalizedName(value: string): string {
  return value.trim().replace(/\s+/g, " ").toLocaleLowerCase("fr-FR");
}

export function addSchoolErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Une erreur est survenue. Vérifiez votre connexion et réessayez.";
  switch (err.status) {
    case 401:
      return "Votre session a expiré. Reconnectez-vous pour continuer.";
    case 403:
      return "Vous n'avez pas l'autorisation d'ajouter un établissement.";
    case 404:
      return "Organisation introuvable ou hors de votre périmètre.";
    case 409:
      return err.message === "A school with this name already exists in this organization"
        ? "Un établissement portant ce nom existe déjà dans cette organisation."
        : "Cet identifiant d'établissement est déjà utilisé, ou cet email ne peut pas être utilisé pour administrer cet établissement.";
    case 422:
      return err.message.includes("required to create a new")
        ? "Aucun compte administrateur existant n'a été trouvé pour cet email : décochez « administrateur existant » et renseignez son nom et un mot de passe initial."
        : `Certaines informations sont invalides : ${err.message}`;
    default:
      return err.status >= 500 ? "Une erreur serveur est survenue. Réessayez dans quelques instants." : err.message;
  }
}

/** Message de succès selon ce que l'API a réellement fait pour l'administrateur (PR #20). */
export function schoolAddedMessage(added: SchoolAdded, verb: string = "ajouté à"): string {
  const where = `Établissement « ${added.school.name} » ${verb} « ${added.organization.name} ».`;
  switch (added.admin_access) {
    case "SCHOOL_ROLE_ADDED":
      return `${where} Compte administrateur existant réutilisé : ${added.admin.email} administre désormais aussi cet établissement (mot de passe inchangé).`;
    case "ORGANIZATION_WIDE_ROLE":
      return `${where} ${added.admin.email} administre déjà tous les établissements de cette organisation : aucun rôle supplémentaire n'a été nécessaire.`;
    default:
      return `${where} Son administrateur peut se connecter.`;
  }
}

type FormState = {
  schoolName: string;
  schoolSlug: string;
  adminFullName: string;
  adminEmail: string;
  adminPassword: string;
  adminPasswordConfirm: string;
};

const EMPTY: FormState = {
  schoolName: "",
  schoolSlug: "",
  adminFullName: "",
  adminEmail: "",
  adminPassword: "",
  adminPasswordConfirm: "",
};

export function NewSchoolForm({
  organizationName,
  existingSchoolNames,
  onSubmit,
}: {
  organizationName: string;
  existingSchoolNames: string[];
  onSubmit: (payload: SchoolAddPayload) => Promise<string>;
}) {
  const [form, setForm] = useState<FormState>(EMPTY);
  const [slugTouched, setSlugTouched] = useState(false);
  const [existingAdmin, setExistingAdmin] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const set = (key: keyof FormState) => (event: React.ChangeEvent<HTMLInputElement>) => {
    const value = event.target.value;
    setForm((prev) => {
      const next = { ...prev, [key]: value };
      if (key === "schoolName" && !slugTouched) next.schoolSlug = slugify(value);
      return next;
    });
    if (key === "schoolSlug") setSlugTouched(true);
  };

  function validate(): string | null {
    if (form.schoolName.trim().length < 2) return "Le nom de l'établissement est obligatoire (2 caractères min.).";
    if (existingSchoolNames.some((name) => normalizedName(name) === normalizedName(form.schoolName))) {
      return "Un établissement portant ce nom existe déjà dans cette organisation.";
    }
    if (form.schoolSlug.length < 2 || !SLUG_PATTERN.test(form.schoolSlug)) {
      return "Identifiant de l'établissement : minuscules, chiffres et tirets uniquement.";
    }
    if (!EMAIL_PATTERN.test(form.adminEmail.trim())) return "Adresse email valide requise.";
    if (existingAdmin) return null;
    if (form.adminFullName.trim().length < 2) return "Le nom de l'administrateur est obligatoire (2 caractères min.).";
    if (form.adminPassword.length < 8) return "Le mot de passe doit contenir au moins 8 caractères.";
    if (form.adminPassword.length > 128) return "Le mot de passe ne doit pas dépasser 128 caractères.";
    if (form.adminPasswordConfirm !== form.adminPassword) return "La confirmation ne correspond pas au mot de passe.";
    return null;
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSuccess(null);
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    setSubmitting(true);
    try {
      const message = await onSubmit({
        school: {
          name: form.schoolName.trim(),
          slug: form.schoolSlug,
          address: null,
          phone: null,
          email: null,
          timezone: "Africa/Lome",
          currency: "XOF",
        },
        // Administrateur existant : seul l'email part — jamais de mot de passe ni de nom.
        admin: existingAdmin
          ? { email: form.adminEmail.trim() }
          : {
              full_name: form.adminFullName.trim(),
              email: form.adminEmail.trim(),
              phone: null,
              password: form.adminPassword,
            },
      });
      setSuccess(message);
      setForm(EMPTY);
      setSlugTouched(false);
    } catch (err) {
      setError(addSchoolErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  const input = "rounded border border-slate-300 px-3 py-2 text-sm";
  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 rounded border border-slate-200 p-4">
      <h3 className="font-semibold text-slate-900">Nouvel établissement dans « {organizationName} »</h3>
      <p className="text-xs text-slate-500">
        Aucune nouvelle organisation n&apos;est créée : l&apos;établissement est rattaché à l&apos;organisation
        sélectionnée.
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm text-slate-700">
          Nom du nouvel établissement
          <input className={input} value={form.schoolName} onChange={set("schoolName")} />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-700">
          Identifiant de l&apos;établissement
          <input className={input} value={form.schoolSlug} onChange={set("schoolSlug")} />
        </label>
      </div>
      <label className="flex items-start gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          className="mt-1"
          checked={existingAdmin}
          onChange={(e) => setExistingAdmin(e.target.checked)}
        />
        <span>
          L&apos;administrateur possède déjà un compte dans cette organisation
          <span className="block text-xs text-slate-500">
            Son compte et son mot de passe actuels sont conservés ; il administrera aussi ce nouvel établissement.
          </span>
        </span>
      </label>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {!existingAdmin && (
          <label className="flex flex-col gap-1 text-sm text-slate-700">
            Nom de l&apos;administrateur
            <input className={input} value={form.adminFullName} onChange={set("adminFullName")} />
          </label>
        )}
        <label className="flex flex-col gap-1 text-sm text-slate-700">
          Email de l&apos;administrateur
          <input className={input} type="email" value={form.adminEmail} onChange={set("adminEmail")} />
        </label>
        {!existingAdmin && (
          <>
            <label className="flex flex-col gap-1 text-sm text-slate-700">
              Mot de passe initial de l&apos;administrateur
              <input
                className={input}
                type="password"
                autoComplete="new-password"
                value={form.adminPassword}
                onChange={set("adminPassword")}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-slate-700">
              Confirmation du mot de passe de l&apos;administrateur
              <input
                className={input}
                type="password"
                autoComplete="new-password"
                value={form.adminPasswordConfirm}
                onChange={set("adminPasswordConfirm")}
              />
            </label>
          </>
        )}
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
          className="rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:opacity-95 disabled:opacity-50"
        >
          {submitting ? "Ajout en cours..." : "Ajouter l'établissement"}
        </button>
      </div>
    </form>
  );
}

export function ExistingSchoolsList({ schools }: { schools: { id: string; name: string }[] }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-sm font-medium text-slate-700">Établissements existants</p>
      {schools.length === 0 ? (
        <p className="text-sm text-slate-500">Aucun établissement.</p>
      ) : (
        <ul className="flex flex-col gap-1" aria-label="Établissements existants">
          {schools.map((school) => (
            <li key={school.id} className="text-sm text-slate-700">
              ✓ {school.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
