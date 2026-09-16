"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth/useAuth";

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 p-8 text-center">
      {children}
    </div>
  );
}

function ErrorRetryScreen({
  message,
  onRetry,
  onReconnect,
}: {
  message: string;
  onRetry: () => void;
  onReconnect: () => void;
}) {
  return (
    <Centered>
      <p role="alert" className="max-w-sm text-sm text-red-700">
        {message}
      </p>
      <div className="flex gap-3">
        <button type="button" onClick={onRetry} className="rounded bg-slate-900 px-4 py-2 text-sm text-white">
          Réessayer
        </button>
        <button
          type="button"
          onClick={onReconnect}
          className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700"
        >
          Se reconnecter
        </button>
      </div>
    </Centered>
  );
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const {
    status,
    organizationContextStatus,
    availableOrganizations,
    organizationContextError,
    selectOrganization,
    schoolContextStatus,
    availableSchools,
    schoolContextError,
    selectSchool,
    retryTenantContext,
    logout,
  } = useAuth();
  const router = useRouter();

  // Une fois l'application réellement entrée (organisation ET école résolues au moins une fois),
  // un changement volontaire de contexte déclenché depuis le sélecteur permanent
  // (components/app-shell/TenantSwitcher.tsx, via selectOrganization/selectSchool) fait
  // transitoirement repasser schoolContextStatus par "loading"/"selection-needed" — ce n'est plus
  // la résolution initiale et ne doit plus reprendre toute la page : le sélecteur affiche lui-même
  // ce sous-état (liste d'écoles, chargement, erreur) dans son propre panneau, sans quitter le
  // tableau de bord. Réinitialisé à la déconnexion pour qu'une reconnexion (même ou autre compte)
  // retraverse normalement le flux de résolution initiale ci-dessous.
  const hasEnteredAppRef = useRef(false);

  useEffect(() => {
    if (status === "anonymous") {
      hasEnteredAppRef.current = false;
      router.push("/login");
    }
  }, [status, router]);

  const reconnect = () => void logout().then(() => router.push("/login"));

  if (status === "authenticated" && organizationContextStatus === "resolved" && schoolContextStatus === "resolved") {
    hasEnteredAppRef.current = true;
  }

  if (hasEnteredAppRef.current && status === "authenticated") {
    return <>{children}</>;
  }

  if (status !== "authenticated" || organizationContextStatus === "loading") {
    return (
      <Centered>
        <p className="text-sm text-slate-500">Chargement...</p>
      </Centered>
    );
  }

  if (organizationContextStatus === "error") {
    return (
      <ErrorRetryScreen
        message={organizationContextError ?? "Une erreur est survenue."}
        onRetry={retryTenantContext}
        onReconnect={reconnect}
      />
    );
  }

  if (organizationContextStatus === "empty") {
    return (
      <Centered>
        <p className="max-w-sm text-sm text-slate-600">Aucune organisation ou école accessible avec ce compte.</p>
        <button type="button" onClick={reconnect} className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700">
          Se déconnecter
        </button>
      </Centered>
    );
  }

  if (organizationContextStatus === "selection-needed") {
    return (
      <Centered>
        <h1 className="text-lg font-semibold text-slate-900">Choisissez une organisation</h1>
        <p className="max-w-sm text-sm text-slate-500">
          Votre compte est rattaché à plusieurs organisations. Sélectionnez celle avec laquelle vous
          souhaitez travailler.
        </p>
        <ul className="flex w-full max-w-sm flex-col gap-2">
          {availableOrganizations.map((organization) => (
            <li key={organization.id}>
              <button
                type="button"
                onClick={() => selectOrganization(organization.id)}
                className="w-full rounded border border-slate-300 px-4 py-2 text-left text-sm hover:bg-slate-100"
              >
                {organization.name}
              </button>
            </li>
          ))}
        </ul>
      </Centered>
    );
  }

  // organizationContextStatus === "resolved" à partir d'ici : passage au statut école.

  if (schoolContextStatus === "loading") {
    return (
      <Centered>
        <p className="text-sm text-slate-500">Chargement...</p>
      </Centered>
    );
  }

  if (schoolContextStatus === "error") {
    return (
      <ErrorRetryScreen
        message={schoolContextError ?? "Une erreur est survenue."}
        onRetry={retryTenantContext}
        onReconnect={reconnect}
      />
    );
  }

  if (schoolContextStatus === "empty") {
    return (
      <Centered>
        <p className="max-w-sm text-sm text-slate-600">Aucune organisation ou école accessible avec ce compte.</p>
        <button type="button" onClick={reconnect} className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700">
          Se déconnecter
        </button>
      </Centered>
    );
  }

  if (schoolContextStatus === "selection-needed") {
    return (
      <Centered>
        <h1 className="text-lg font-semibold text-slate-900">Choisissez une école</h1>
        <p className="max-w-sm text-sm text-slate-500">
          Votre compte administre plusieurs écoles. Sélectionnez celle avec laquelle vous souhaitez
          travailler.
        </p>
        <ul className="flex w-full max-w-sm flex-col gap-2">
          {availableSchools.map((school) => (
            <li key={school.id}>
              <button
                type="button"
                onClick={() => selectSchool(school.id)}
                className="w-full rounded border border-slate-300 px-4 py-2 text-left text-sm hover:bg-slate-100"
              >
                {school.name}
              </button>
            </li>
          ))}
        </ul>
      </Centered>
    );
  }

  return <>{children}</>;
}
