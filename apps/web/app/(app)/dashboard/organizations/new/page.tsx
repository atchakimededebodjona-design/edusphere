"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isPlatformAdmin } from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/useAuth";
import { OrganizationRegistrationForm } from "./OrganizationRegistrationForm";

// Protection frontend uniquement : le contrôle réel est côté backend (require_platform_admin sur
// POST /api/v1/platform/organizations). Un non-platform admin est renvoyé vers son tableau de bord.
export default function NewOrganizationPage() {
  const { status, user } = useAuth();
  const router = useRouter();
  const allowed = status === "authenticated" && isPlatformAdmin(user);

  useEffect(() => {
    if (status === "authenticated" && !isPlatformAdmin(user)) {
      router.replace("/dashboard");
    }
  }, [status, user, router]);

  if (!allowed) {
    return <p className="text-sm text-slate-400">Vérification des droits...</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Inscrire une organisation</h1>
        <p className="mt-1 text-sm text-slate-600">
          Crée l&apos;organisation, son école principale et le premier administrateur de l&apos;école.
        </p>
      </div>
      <OrganizationRegistrationForm />
    </div>
  );
}
