"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, register, type RegisterPayload } from "@/lib/auth/client";
import { useAuth } from "@/lib/auth/useAuth";

const initialForm: RegisterPayload = {
  organization_name: "",
  organization_slug: "",
  country_code: "TG",
  school_name: "",
  school_slug: "",
  admin_full_name: "",
  admin_email: "",
  admin_password: "",
};

export default function RegisterPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState<RegisterPayload>(initialForm);
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  function update(field: keyof RegisterPayload) {
    return (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((prev) => ({ ...prev, [field]: event.target.value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setStatus("loading");
    setError(null);
    try {
      await register(form);
      // register() ne persiste pas la session (voir lib/auth/client.ts) — on ré-authentifie via
      // le contexte pour hydrater la session et /me avec les mêmes identifiants.
      await login(form.admin_email, form.admin_password);
      router.push("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
      setStatus("error");
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-slate-50 p-8">
      <h1 className="text-2xl font-bold text-slate-900">Inscrire mon école</h1>
      <form onSubmit={handleSubmit} className="flex w-full max-w-sm flex-col gap-3">
        <input
          placeholder="Nom de l'organisation"
          value={form.organization_name}
          onChange={update("organization_name")}
          required
          className="rounded border border-slate-300 px-3 py-2"
        />
        <input
          placeholder="Identifiant (slug) de l'organisation"
          value={form.organization_slug}
          onChange={update("organization_slug")}
          required
          pattern="[a-z0-9\-]+"
          className="rounded border border-slate-300 px-3 py-2"
        />
        <input
          placeholder="Nom de l'école"
          value={form.school_name}
          onChange={update("school_name")}
          required
          className="rounded border border-slate-300 px-3 py-2"
        />
        <input
          placeholder="Identifiant (slug) de l'école"
          value={form.school_slug}
          onChange={update("school_slug")}
          required
          pattern="[a-z0-9\-]+"
          className="rounded border border-slate-300 px-3 py-2"
        />
        <input
          placeholder="Votre nom complet"
          value={form.admin_full_name}
          onChange={update("admin_full_name")}
          required
          className="rounded border border-slate-300 px-3 py-2"
        />
        <input
          type="email"
          placeholder="Votre email"
          value={form.admin_email}
          onChange={update("admin_email")}
          required
          className="rounded border border-slate-300 px-3 py-2"
        />
        <input
          type="password"
          placeholder="Mot de passe (8 caractères min.)"
          value={form.admin_password}
          onChange={update("admin_password")}
          required
          minLength={8}
          className="rounded border border-slate-300 px-3 py-2"
        />
        <button
          type="submit"
          disabled={status === "loading"}
          className="rounded bg-slate-900 px-3 py-2 text-white disabled:opacity-50"
        >
          {status === "loading" ? "Création..." : "Créer mon compte"}
        </button>
        {error && <p className="text-sm text-red-700">{error}</p>}
      </form>
    </main>
  );
}
