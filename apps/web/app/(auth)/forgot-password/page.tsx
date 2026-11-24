"use client";

import { useState } from "react";
import Link from "next/link";
import { AuthFrame, authButtonClass, authInputClass, authLabelClass } from "@/components/auth/AuthFrame";
import { ApiError, forgotPassword } from "@/lib/auth/client";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "sent" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setStatus("loading");
    setError(null);
    try {
      await forgotPassword(email);
      // Même message que l'email existe ou non (cf. auth/service.py::request_password_reset) —
      // ne jamais révéler si un compte existe.
      setStatus("sent");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
      setStatus("error");
    }
  }

  return (
    <AuthFrame
      title="Mot de passe oublié"
      footer={
        <Link href="/login" className="inline-flex min-h-11 items-center text-sm font-medium text-brand-blue hover:underline">
          Retour à la connexion
        </Link>
      }
    >
      {status === "sent" ? (
        <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          Si un compte existe pour cette adresse, un email contenant un lien de réinitialisation
          vient d&apos;être envoyé.
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <p className="text-sm text-slate-600">
            Indiquez votre adresse email : si un compte existe, vous recevrez un lien pour définir
            un nouveau mot de passe.
          </p>
          <label className={authLabelClass}>
            Email
            <input
              type="email"
              placeholder="Email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className={authInputClass}
            />
          </label>
          <button type="submit" disabled={status === "loading"} className={authButtonClass}>
            {status === "loading" ? "Envoi..." : "Envoyer le lien"}
          </button>
          {error && (
            <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </p>
          )}
        </form>
      )}
    </AuthFrame>
  );
}
