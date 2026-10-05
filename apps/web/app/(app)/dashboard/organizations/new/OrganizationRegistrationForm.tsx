"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError } from "@/lib/api/client";
import {
  createPlatformOrganization,
  type PlatformOrganizationCreate,
  type PlatformOrganizationCreated,
} from "@/lib/platform/client";

const SLUG_PATTERN = /^[a-z0-9-]+$/;
const COUNTRY_PATTERN = /^[A-Za-z]{2}$/;
const CURRENCY_PATTERN = /^[A-Z]{3}$/;
const TIMEZONE_PATTERN = /^[A-Za-z_]+(\/[A-Za-z0-9_+-]+)+$/;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

type FormState = {
  orgName: string;
  orgSlug: string;
  orgCountry: string;
  orgTimezone: string;
  orgCurrency: string;
  schoolName: string;
  schoolSlug: string;
  schoolAddress: string;
  schoolPhone: string;
  schoolEmail: string;
  schoolTimezone: string;
  schoolCurrency: string;
  adminFullName: string;
  adminEmail: string;
  adminPhone: string;
  adminPassword: string;
  adminPasswordConfirm: string;
};

type FormErrors = Partial<Record<keyof FormState, string>>;

const initialState: FormState = {
  orgName: "",
  orgSlug: "",
  orgCountry: "TG",
  orgTimezone: "Africa/Lome",
  orgCurrency: "XOF",
  schoolName: "",
  schoolSlug: "principale",
  schoolAddress: "",
  schoolPhone: "",
  schoolEmail: "",
  schoolTimezone: "Africa/Lome",
  schoolCurrency: "XOF",
  adminFullName: "",
  adminEmail: "",
  adminPhone: "",
  adminPassword: "",
  adminPasswordConfirm: "",
};

export function validateForm(form: FormState): FormErrors {
  const errors: FormErrors = {};
  const required = (value: string) => value.trim().length >= 2;

  if (!required(form.orgName)) errors.orgName = "Le nom de l'organisation est obligatoire (2 caractères min.).";
  if (!SLUG_PATTERN.test(form.orgSlug)) errors.orgSlug = "Minuscules, chiffres et tirets uniquement.";
  if (!COUNTRY_PATTERN.test(form.orgCountry)) errors.orgCountry = "Code pays à 2 lettres (ex. TG).";
  if (!TIMEZONE_PATTERN.test(form.orgTimezone)) errors.orgTimezone = "Fuseau horaire IANA (ex. Africa/Lome).";
  if (!CURRENCY_PATTERN.test(form.orgCurrency)) errors.orgCurrency = "Devise à 3 lettres majuscules (ex. XOF).";

  if (!required(form.schoolName)) errors.schoolName = "Le nom de l'école est obligatoire (2 caractères min.).";
  if (!SLUG_PATTERN.test(form.schoolSlug)) errors.schoolSlug = "Minuscules, chiffres et tirets uniquement.";
  if (form.schoolEmail && !EMAIL_PATTERN.test(form.schoolEmail)) errors.schoolEmail = "Email de l'école invalide.";
  if (!TIMEZONE_PATTERN.test(form.schoolTimezone)) errors.schoolTimezone = "Fuseau horaire IANA (ex. Africa/Lome).";
  if (!CURRENCY_PATTERN.test(form.schoolCurrency)) errors.schoolCurrency = "Devise à 3 lettres majuscules (ex. XOF).";

  if (!required(form.adminFullName)) errors.adminFullName = "Le nom complet est obligatoire (2 caractères min.).";
  if (!EMAIL_PATTERN.test(form.adminEmail)) errors.adminEmail = "Adresse email valide requise.";
  if (form.adminPassword.length < 8) errors.adminPassword = "Le mot de passe doit contenir au moins 8 caractères.";
  if (form.adminPassword.length > 128) errors.adminPassword = "Le mot de passe ne doit pas dépasser 128 caractères.";
  if (form.adminPasswordConfirm !== form.adminPassword) {
    errors.adminPasswordConfirm = "La confirmation ne correspond pas au mot de passe.";
  }

  return errors;
}

export function toPayload(form: FormState): PlatformOrganizationCreate {
  return {
    organization: {
      name: form.orgName.trim(),
      slug: form.orgSlug,
      country_code: form.orgCountry.toUpperCase(),
      timezone: form.orgTimezone,
      currency: form.orgCurrency,
    },
    school: {
      name: form.schoolName.trim(),
      slug: form.schoolSlug,
      address: form.schoolAddress.trim() || null,
      phone: form.schoolPhone.trim() || null,
      email: form.schoolEmail.trim() || null,
      timezone: form.schoolTimezone,
      currency: form.schoolCurrency,
    },
    admin: {
      full_name: form.adminFullName.trim(),
      email: form.adminEmail.trim(),
      phone: form.adminPhone.trim() || null,
      password: form.adminPassword,
    },
  };
}

// Messages utilisateur par statut HTTP. Le backend renvoie le détail technique ; on ne l'affiche
// que pour les 422, où il indique le champ fautif.
export function errorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Une erreur est survenue. Vérifiez votre connexion et réessayez.";
  switch (err.status) {
    case 401:
      return "Votre session a expiré. Reconnectez-vous pour continuer.";
    case 403:
      return "Accès réservé à l'administrateur de la plateforme.";
    case 409:
      return "Ce slug d'organisation ou cet email administrateur est déjà utilisé.";
    case 422:
      return `Certaines informations sont invalides : ${err.message}`;
    default:
      return err.status >= 500
        ? "Une erreur serveur est survenue. Réessayez dans quelques instants."
        : err.message;
  }
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm font-medium text-brand-text">
      {label}
      {children}
      {error && <span className="text-xs font-normal text-red-600">{error}</span>}
    </label>
  );
}

const inputClass =
  "rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-brand-text shadow-sm outline-none transition focus:border-brand-blue focus:ring-2 focus:ring-brand-blue/20";

export function OrganizationRegistrationForm() {
  const router = useRouter();
  const [form, setForm] = useState<FormState>(initialState);
  const [errors, setErrors] = useState<FormErrors>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [created, setCreated] = useState<PlatformOrganizationCreated | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Garde synchrone contre les doubles soumissions (un setState n'est pas immédiat).
  const inFlight = useRef(false);

  function update(field: keyof FormState) {
    return (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      const value = event.target.value;
      setForm((prev) => ({ ...prev, [field]: value }));
    };
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;

    const validation = validateForm(form);
    setErrors(validation);
    setSubmitError(null);
    if (Object.keys(validation).length > 0) return;

    inFlight.current = true;
    setSubmitting(true);
    try {
      const result = await createPlatformOrganization(toPayload(form));
      setCreated(result);
    } catch (err) {
      setSubmitError(errorMessage(err));
    } finally {
      inFlight.current = false;
      setSubmitting(false);
    }
  }

  if (created) {
    return (
      <section role="status" className="flex flex-col gap-4 rounded-xl border border-emerald-200 bg-emerald-50 p-6">
        <h2 className="text-lg font-semibold text-emerald-900">Organisation créée avec succès</h2>
        <dl className="grid grid-cols-1 gap-2 text-sm text-emerald-950 sm:grid-cols-[max-content_1fr] sm:gap-x-4">
          <dt className="font-medium">Organisation</dt>
          <dd>{created.organization.name}</dd>
          <dt className="font-medium">École</dt>
          <dd>{created.school.name}</dd>
          <dt className="font-medium">Administrateur</dt>
          <dd>{created.admin.email}</dd>
        </dl>
        <p className="text-sm text-emerald-900">
          L&apos;administrateur de l&apos;école se connecte avec les identifiants initiaux que vous avez définis.
          Votre session reste ouverte.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/dashboard"
            className="rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-4 py-2.5 text-sm font-semibold text-white"
          >
            Retour au tableau de bord
          </Link>
          <button
            type="button"
            onClick={() => {
              setCreated(null);
              setForm(initialState);
              setErrors({});
            }}
            className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700"
          >
            Créer une autre organisation
          </button>
        </div>
      </section>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex max-w-3xl flex-col gap-8">
      <fieldset className="flex flex-col gap-4">
        <legend className="text-base font-semibold text-brand-text">1. Organisation</legend>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Nom de l'organisation" error={errors.orgName}>
            <input className={inputClass} value={form.orgName} onChange={update("orgName")} required />
          </Field>
          <Field label="Slug" error={errors.orgSlug}>
            <input className={inputClass} value={form.orgSlug} onChange={update("orgSlug")} required />
          </Field>
          <Field label="Pays (code)" error={errors.orgCountry}>
            <input className={inputClass} value={form.orgCountry} onChange={update("orgCountry")} maxLength={2} required />
          </Field>
          <Field label="Fuseau horaire" error={errors.orgTimezone}>
            <input className={inputClass} value={form.orgTimezone} onChange={update("orgTimezone")} required />
          </Field>
          <Field label="Devise" error={errors.orgCurrency}>
            <input className={inputClass} value={form.orgCurrency} onChange={update("orgCurrency")} maxLength={3} required />
          </Field>
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="text-base font-semibold text-brand-text">2. École principale</legend>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Nom de l'école" error={errors.schoolName}>
            <input className={inputClass} value={form.schoolName} onChange={update("schoolName")} required />
          </Field>
          <Field label="Slug" error={errors.schoolSlug}>
            <input className={inputClass} value={form.schoolSlug} onChange={update("schoolSlug")} required />
          </Field>
          <Field label="Adresse">
            <input className={inputClass} value={form.schoolAddress} onChange={update("schoolAddress")} />
          </Field>
          <Field label="Téléphone">
            <input className={inputClass} value={form.schoolPhone} onChange={update("schoolPhone")} />
          </Field>
          <Field label="Email" error={errors.schoolEmail}>
            <input type="email" className={inputClass} value={form.schoolEmail} onChange={update("schoolEmail")} />
          </Field>
          <Field label="Fuseau horaire" error={errors.schoolTimezone}>
            <input className={inputClass} value={form.schoolTimezone} onChange={update("schoolTimezone")} required />
          </Field>
          <Field label="Devise" error={errors.schoolCurrency}>
            <input className={inputClass} value={form.schoolCurrency} onChange={update("schoolCurrency")} maxLength={3} required />
          </Field>
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="text-base font-semibold text-brand-text">3. Administrateur de l&apos;école</legend>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Nom complet" error={errors.adminFullName}>
            <input className={inputClass} value={form.adminFullName} onChange={update("adminFullName")} required />
          </Field>
          <Field label="Email" error={errors.adminEmail}>
            <input type="email" className={inputClass} value={form.adminEmail} onChange={update("adminEmail")} required />
          </Field>
          <Field label="Téléphone">
            <input className={inputClass} value={form.adminPhone} onChange={update("adminPhone")} />
          </Field>
          <span className="hidden sm:block" aria-hidden="true" />
          <Field label="Mot de passe initial" error={errors.adminPassword}>
            <input
              type="password"
              className={inputClass}
              value={form.adminPassword}
              onChange={update("adminPassword")}
              autoComplete="new-password"
              minLength={8}
              required
            />
          </Field>
          <Field label="Confirmation du mot de passe" error={errors.adminPasswordConfirm}>
            <input
              type="password"
              className={inputClass}
              value={form.adminPasswordConfirm}
              onChange={update("adminPasswordConfirm")}
              autoComplete="new-password"
              required
            />
          </Field>
        </div>
      </fieldset>

      {submitError && (
        <p role="alert" className="text-sm text-red-600">
          {submitError}
        </p>
      )}

      <div className="flex flex-wrap gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:opacity-95 disabled:opacity-50"
        >
          {submitting ? "Création en cours..." : "Créer l'organisation"}
        </button>
        <button
          type="button"
          onClick={() => router.push("/dashboard")}
          disabled={submitting}
          className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-medium text-slate-700 disabled:opacity-50"
        >
          Annuler
        </button>
      </div>
    </form>
  );
}
