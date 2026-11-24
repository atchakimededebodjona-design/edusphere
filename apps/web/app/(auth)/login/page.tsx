"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AuthFrame, authButtonClass, authInputClass, authLabelClass } from "@/components/auth/AuthFrame";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { ApiError } from "@/lib/auth/client";
import { isParentOnlyAccount, isPartnerOnlyAccount, isTeacherOnlyAccount } from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/useAuth";
import { forgetAccount, listOfflineAccounts, type OfflineAccount } from "@/lib/offline/vault";

function formatDay(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

// 2026-11-24 — l'API explique elle-même l'échec en français (« Compte inexistant », « Mot de passe
// incorrect », compte désactivé : app/modules/auth/service.py). Seul le blocage après trop d'essais
// arrive en anglais : il est traduit ici.
function loginErrorMessage(err: unknown): string {
  if (!(err instanceof ApiError)) return "Une erreur est survenue.";
  if (err.status === 429) return "Trop d'essais de connexion. Patientez quelques minutes, puis réessayez.";
  return err.message;
}

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  // Connexion sans internet — comptes verrouillés sur cet appareil (lib/offline/vault.ts).
  const [offlineAccounts, setOfflineAccounts] = useState<OfflineAccount[]>([]);
  const refreshOfflineAccounts = useCallback(() => {
    void listOfflineAccounts().then(setOfflineAccounts);
  }, []);
  useEffect(() => refreshOfflineAccounts(), [refreshOfflineAccounts]);

  async function handleForget(account: OfflineAccount) {
    const question = `Effacer ${account.email} de cet appareil ?\n\nSes informations gardées et ses saisies non envoyées (appel, notes) seront supprimées ; il faudra internet pour se reconnecter. Les encaissements non envoyés restent sur l'appareil et partiront à sa prochaine connexion avec internet.`;
    if (!window.confirm(question)) return;
    await forgetAccount(account.userId);
    refreshOfflineAccounts();
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setStatus("loading");
    setError(null);
    try {
      const me = await login(email, password);
      // Phase 28A — un compte dont tous les rôles sont PARENT n'a rien à faire dans l'espace
      // admin (voir lib/auth/roles.ts) : redirection directe vers son propre portail.
      // La landing page publique vivant désormais sur "/", un compte non-parent est envoyé vers
      // son tableau de bord ("/dashboard") plutôt que vers la page marketing.
      // PR #17 — un partenaire commercial pur est envoyé vers son espace `/partner` (navigation
      // uniquement : l'API reste seule juge des accès).
      router.push(
        isParentOnlyAccount(me.roles)
          ? "/parent"
          : isPartnerOnlyAccount(me.user, me.roles)
            ? "/partner"
            : isTeacherOnlyAccount(me.user, me.roles)
              ? "/teacher"
              : "/dashboard",
      );
    } catch (err) {
      setError(loginErrorMessage(err));
      setStatus("error");
      refreshOfflineAccounts();
    }
  }

  return (
    <AuthFrame title="Connexion" subtitle="Accédez à votre espace EduLinkage.">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
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
        <label className={authLabelClass}>
          Mot de passe
          <PasswordInput
            placeholder="Mot de passe"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className={authInputClass}
          />
        </label>

        <button
          type="submit"
          disabled={status === "loading"}
          className={`mt-2 ${authButtonClass}`}
        >
          {status === "loading" ? "Connexion..." : "Se connecter"}
        </button>

        {error && (
          <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
            {error}
          </p>
        )}
      </form>

      <Link
        href="/forgot-password"
        className="mt-6 inline-flex min-h-11 items-center text-sm font-medium text-brand-blue hover:underline"
      >
        Mot de passe oublié ?
      </Link>

      {offlineAccounts.length > 0 && (
        <section
          aria-labelledby="offline-accounts-title"
          data-testid="offline-accounts"
          className="mt-8 rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700"
        >
          <h2 id="offline-accounts-title" className="font-semibold text-brand-text">
            Connexion possible sans internet
          </h2>
          <p className="mt-1 text-xs text-slate-600">
            Ces comptes peuvent se reconnecter sur cet appareil avec leur mot de passe, même sans internet.
            Leurs informations y sont gardées chiffrées.
          </p>
          <ul className="mt-3 flex flex-col gap-2">
            {offlineAccounts.map((account) => (
              <li key={account.userId} className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-medium text-slate-900">{account.email}</p>
                  <p className="text-xs text-slate-600">
                    {account.blocked
                      ? "Trop d'essais : prochaine connexion avec internet"
                      : `Sans internet jusqu'au ${formatDay(account.usableUntil)}`}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void handleForget(account)}
                  className="inline-flex min-h-9 shrink-0 items-center rounded-lg px-2 text-xs font-medium text-slate-700 underline hover:bg-slate-100"
                >
                  Effacer de cet appareil
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </AuthFrame>
  );
}
