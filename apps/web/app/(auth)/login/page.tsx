"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { BrandFull, BrandSymbol } from "@/components/branding/BrandLogo";
import { ApiError } from "@/lib/auth/client";
import { isParentOnlyAccount } from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/useAuth";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setStatus("loading");
    setError(null);
    try {
      const me = await login(email, password);
      // Phase 28A — un compte dont tous les rôles sont PARENT n'a rien à faire dans l'espace
      // admin (voir lib/auth/roles.ts) : redirection directe vers son propre portail.
      router.push(isParentOnlyAccount(me.roles) ? "/parent" : "/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
      setStatus("error");
    }
  }

  return (
    <main className="flex min-h-screen flex-col bg-brand-bg lg:flex-row">
      {/* Panneau de marque — identité EduLinkage, dégradé subtil bleu → cyan purement CSS
          (aucune image générée), pleine largeur sur mobile/tablette, colonne dédiée en desktop. */}
      <div className="relative flex items-center justify-center overflow-hidden bg-brand-navy px-8 py-12 lg:w-[45%] lg:py-0">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 rounded-full bg-gradient-to-br from-brand-blue to-brand-cyan opacity-20 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-24 -right-16 h-80 w-80 rounded-full bg-gradient-to-tr from-brand-cyan to-brand-blue opacity-20 blur-3xl"
        />
        <div className="relative z-10 flex max-w-sm flex-col items-center gap-6 py-8 text-center">
          <BrandFull className="h-auto w-full max-w-[260px]" priority />
          <p className="text-sm font-medium text-slate-300">Une école, des liens, un avenir.</p>
          <p className="hidden text-sm leading-relaxed text-slate-400 lg:block">
            La plateforme qui connecte administrateurs, enseignants et familles autour de la
            réussite scolaire.
          </p>
        </div>
      </div>

      {/* Panneau formulaire */}
      <div className="flex flex-1 items-center justify-center px-6 py-12 sm:px-10">
        <div className="w-full max-w-sm">
          <BrandSymbol className="mb-6 h-10 w-10 lg:hidden" priority />

          <h1 className="text-2xl font-bold text-brand-text">Connexion</h1>
          <p className="mt-1 text-sm text-slate-500">Accédez à votre espace EduLinkage.</p>

          <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-4">
            <label className="flex flex-col gap-1.5 text-sm font-medium text-brand-text">
              Email
              <input
                type="email"
                placeholder="Email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-brand-text shadow-sm outline-none transition focus:border-brand-blue focus:ring-2 focus:ring-brand-blue/20"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm font-medium text-brand-text">
              Mot de passe
              <input
                type="password"
                placeholder="Mot de passe"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="rounded-lg border border-slate-200 bg-white px-3.5 py-2.5 text-sm text-brand-text shadow-sm outline-none transition focus:border-brand-blue focus:ring-2 focus:ring-brand-blue/20"
              />
            </label>

            <button
              type="submit"
              disabled={status === "loading"}
              className="mt-2 rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:opacity-95 disabled:opacity-50"
            >
              {status === "loading" ? "Connexion..." : "Se connecter"}
            </button>

            {error && (
              <p role="alert" className="text-sm text-red-600">
                {error}
              </p>
            )}
          </form>

          <Link
            href="/forgot-password"
            className="mt-6 inline-block text-sm font-medium text-brand-blue hover:underline"
          >
            Mot de passe oublié ?
          </Link>
        </div>
      </div>
    </main>
  );
}
