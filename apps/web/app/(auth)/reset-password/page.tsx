"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { AuthFrame, authButtonClass, authInputClass, authLabelClass } from "@/components/auth/AuthFrame";
import { useRouter, useSearchParams } from "next/navigation";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { ApiError, resetPassword } from "@/lib/auth/client";
import {
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  PASSWORD_RULE_HINT,
  passwordLengthProblem,
  translatePasswordRefusal,
} from "@/lib/auth/passwordRule";

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
    const lengthProblem = passwordLengthProblem(password);
    if (lengthProblem) {
      setError(lengthProblem);
      setStatus("error");
      return;
    }
    setStatus("loading");
    setError(null);
    try {
      await resetPassword(token, password);
      setStatus("done");
    } catch (err) {
      // Phase 4 C (2026-11-24) — le refus du jeton arrivait en anglais (« Invalid or expired reset token »).
      setError(
        err instanceof ApiError
          ? err.message.includes("reset token")
            ? "Ce lien n'est plus valable : il a expiré, a déjà servi ou est incomplet. Demandez un nouveau lien depuis « Mot de passe oublié »."
            : translatePasswordRefusal(err.message)
          : "Une erreur est survenue.",
      );
      setStatus("error");
    }
  }

  if (!token) {
    return (
      <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
        Ce lien est invalide.{" "}
        <Link href="/forgot-password" className="font-medium underline">
          Demandez un nouveau lien de réinitialisation.
        </Link>
      </p>
    );
  }

  if (status === "done") {
    return (
      <div className="flex flex-col gap-4">
        <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          Votre mot de passe a été défini. Vous pouvez maintenant vous connecter.
        </p>
        <button type="button" onClick={() => router.push("/login")} className={authButtonClass}>
          Aller à la connexion
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <label className={authLabelClass}>
        Nouveau mot de passe
      <PasswordInput
        placeholder={`Nouveau mot de passe (${PASSWORD_RULE_HINT})`}
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        required
        minLength={PASSWORD_MIN_LENGTH}
        maxLength={PASSWORD_MAX_LENGTH}
        autoComplete="new-password"
        className={authInputClass}
      />
      </label>
      <label className={authLabelClass}>
        Confirmation
      <PasswordInput
        toggleLabel="Afficher la confirmation"
        placeholder="Confirmer le mot de passe"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        required
        minLength={PASSWORD_MIN_LENGTH}
        maxLength={PASSWORD_MAX_LENGTH}
        autoComplete="new-password"
        className={authInputClass}
      />
      </label>
      <p className="text-xs text-slate-600">
        Au moins {PASSWORD_MIN_LENGTH} caractères. Une courte phrase facile à retenir convient bien ; évitez les mots de passe
        courants.
      </p>
      <button type="submit" disabled={status === "loading"} className={authButtonClass}>
        {status === "loading" ? "Enregistrement..." : "Définir le mot de passe"}
      </button>
      {error && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      )}
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <AuthFrame
      title="Définir votre mot de passe"
      footer={
        <Link href="/login" className="inline-flex min-h-11 items-center text-sm font-medium text-brand-blue hover:underline">
          Retour à la connexion
        </Link>
      }
    >
      <Suspense fallback={<p className="text-sm text-slate-600">Chargement...</p>}>
        <ResetPasswordForm />
      </Suspense>
    </AuthFrame>
  );
}
