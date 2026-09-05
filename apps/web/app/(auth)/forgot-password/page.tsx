"use client";

import { useState } from "react";
import Link from "next/link";
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
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-slate-50 p-8">
      <h1 className="text-2xl font-bold text-slate-900">Mot de passe oublié</h1>
      {status === "sent" ? (
        <p className="max-w-sm text-center text-sm text-slate-600">
          Si un compte existe pour cette adresse, un email contenant un lien de réinitialisation
          vient d&apos;être envoyé.
        </p>
      ) : (
        <form onSubmit={handleSubmit} className="flex w-full max-w-sm flex-col gap-4">
          <p className="text-sm text-slate-500">
            Indiquez votre adresse email : si un compte existe, vous recevrez un lien pour définir
            un nouveau mot de passe.
          </p>
          <input
            type="email"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            className="rounded border border-slate-300 px-3 py-2"
          />
          <button
            type="submit"
            disabled={status === "loading"}
            className="rounded bg-slate-900 px-3 py-2 text-white disabled:opacity-50"
          >
            {status === "loading" ? "Envoi..." : "Envoyer le lien"}
          </button>
          {error && <p className="text-sm text-red-700">{error}</p>}
        </form>
      )}
      <Link href="/login" className="text-sm text-slate-600 underline">
        Retour à la connexion
      </Link>
    </main>
  );
}
