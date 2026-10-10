"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { isPlatformAdmin } from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/useAuth";
import { ExistingOrganizationPanel } from "./ExistingOrganizationPanel";
import { OrganizationRegistrationForm } from "./OrganizationRegistrationForm";

type Mode = "new" | "existing";

// Protection frontend uniquement : le contrôle réel est côté backend (require_platform_admin sur
// POST /api/v1/platform/organizations ; permission `platform.schools.enroll` sur
// POST /api/v1/platform/organizations/{id}/schools). Un non-platform admin est renvoyé vers son
// tableau de bord.
//
// PR #19 — « Inscrire une école » : deux parcours explicites. « Nouvelle organisation » (défaut,
// comportement historique : organisation + première école + administrateur) ou « Organisation
// existante » (ajout d'un établissement, l'organisation n'est jamais recréée). `?mode=existing`
// ouvre directement le second parcours.
export default function NewOrganizationPage() {
  const { status, user } = useAuth();
  const router = useRouter();
  const allowed = status === "authenticated" && isPlatformAdmin(user);
  const [mode, setMode] = useState<Mode>("new");

  useEffect(() => {
    if (status === "authenticated" && !isPlatformAdmin(user)) {
      router.replace("/dashboard");
    }
  }, [status, user, router]);

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("mode") === "existing") setMode("existing");
  }, []);

  if (!allowed) {
    return <p className="text-sm text-slate-400">Vérification des droits...</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-slate-700">Inscrire une école</legend>
        <div className="flex flex-wrap gap-4 text-sm text-slate-700">
          <label className="flex items-center gap-2">
            <input type="radio" name="enrollment-mode" checked={mode === "new"} onChange={() => setMode("new")} />
            Nouvelle organisation
          </label>
          <label className="flex items-center gap-2">
            <input
              type="radio"
              name="enrollment-mode"
              checked={mode === "existing"}
              onChange={() => setMode("existing")}
            />
            Organisation existante
          </label>
        </div>
      </fieldset>

      {mode === "new" ? (
        <>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Inscrire une organisation</h1>
            <p className="mt-1 text-sm text-slate-600">
              Crée l&apos;organisation, son école principale et le premier administrateur de l&apos;école.
            </p>
          </div>
          <OrganizationRegistrationForm />
        </>
      ) : (
        <>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Ajouter un établissement à une organisation existante</h1>
            <p className="mt-1 text-sm text-slate-600">
              Sélectionnez l&apos;organisation : le nouvel établissement et son administrateur y seront rattachés,
              sans créer de nouvelle organisation.
            </p>
          </div>
          <ExistingOrganizationPanel />
        </>
      )}
    </div>
  );
}
