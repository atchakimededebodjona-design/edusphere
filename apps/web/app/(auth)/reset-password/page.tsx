"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, resetPassword } from "@/lib/auth/client";

function ResetPasswordForm() {
  const router = useRouter();
  const token = useSearchParams().get("token");

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!token) return;
    if (password !== confirm) {
      setError("Les deux mots de passe ne correspondent pas.");
      setStatus("error");
      return;
    }
    setStatus("loading");
    setError(null);
    try {
      await resetPassword(token, password);
      setStatus("done");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
      setStatus("error");
    }
  }

  if (!token) {
    return (
      <p className="max-w-sm text-center text-sm text-red-700">
        Ce lien est invalide. Demandez un nouveau lien de réinitialisation.
      </p>
    );
  }

  if (status === "done") {
    return (
      <div className="flex flex-col items-center gap-4">
        <p className="max-w-sm text-center text-sm text-slate-600">
          Votre mot de passe a été défini. Vous pouvez maintenant vous connecter.
        </p>
        <button
          type="button"
          onClick={() => router.push("/login")}
          className="rounded bg-slate-900 px-4 py-2 text-sm text-white"
        >
          Aller à la connexion
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex w-full max-w-sm flex-col gap-4">
      <input
        type="password"
        placeholder="Nouveau mot de passe (8 caractères min.)"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        minLength={8}
        className="rounded border border-slate-300 px-3 py-2"
      />
      <input
        type="password"
        placeholder="Confirmer le mot de passe"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        required
        minLength={8}
        className="rounded border border-slate-300 px-3 py-2"
      />
      <button
        type="submit"
        disabled={status === "loading"}
        className="rounded bg-slate-900 px-3 py-2 text-white disabled:opacity-50"
      >
        {status === "loading" ? "Enregistrement..." : "Définir le mot de passe"}
      </button>
      {error && <p className="text-sm text-red-700">{error}</p>}
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-slate-50 p-8">
      <h1 className="text-2xl font-bold text-slate-900">Définir votre mot de passe</h1>
      <Suspense fallback={<p className="text-sm text-slate-500">Chargement...</p>}>
        <ResetPasswordForm />
      </Suspense>
      <Link href="/login" className="text-sm text-slate-600 underline">
        Retour à la connexion
      </Link>
    </main>
  );
}
