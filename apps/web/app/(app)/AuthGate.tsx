"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth/useAuth";

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 p-8 text-center">
      {children}
    </div>
  );
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const {
    status,
    schoolContextStatus,
    availableSchools,
    schoolContextError,
    selectSchool,
    retrySchoolContext,
    logout,
  } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "anonymous") router.push("/login");
  }, [status, router]);

  if (status !== "authenticated" || schoolContextStatus === "loading") {
    return (
      <Centered>
        <p className="text-sm text-slate-500">Chargement...</p>
      </Centered>
    );
  }

  if (schoolContextStatus === "error") {
    return (
      <Centered>
        <p role="alert" className="max-w-sm text-sm text-red-700">
          {schoolContextError}
        </p>
        <div className="flex gap-3">
          <button type="button" onClick={retrySchoolContext} className="rounded bg-slate-900 px-4 py-2 text-sm text-white">
            Réessayer
          </button>
          <button
            type="button"
            onClick={() => void logout().then(() => router.push("/login"))}
            className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700"
          >
            Se reconnecter
          </button>
        </div>
      </Centered>
    );
  }

  if (schoolContextStatus === "empty") {
    return (
      <Centered>
        <p className="max-w-sm text-sm text-slate-600">Aucune école accessible avec ce compte.</p>
        <button
          type="button"
          onClick={() => void logout().then(() => router.push("/login"))}
          className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700"
        >
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
