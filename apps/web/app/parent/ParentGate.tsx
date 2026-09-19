"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { hasAnyParentRole } from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/useAuth";

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 p-8 text-center">
      {children}
    </div>
  );
}

// Phase 28A — délibérément plus simple que app/(app)/AuthGate.tsx : le portail parent n'a besoin
// d'aucune résolution organisation/école (voir apps/api/app/modules/parent/service.py — un parent
// voit ses enfants toutes écoles confondues, sans notion de "tenant actif"). Seul le statut de
// connexion compte ici.
export function ParentGate({ children }: { children: React.ReactNode }) {
  const { status, roles } = useAuth();
  const router = useRouter();

  const isAnonymous = status === "anonymous";
  // Un compte authentifié mais sans aucun rôle PARENT (ex. un admin qui a tapé /parent dans la
  // barre d'adresse) n'a rien à voir ici — renvoyé vers son espace habituel plutôt que de voir un
  // portail vide qui ne le concerne pas. Un compte qui cumule PARENT et un autre rôle reste
  // autorisé (voir lib/auth/roles.ts::hasAnyParentRole).
  const isWrongAudience = status === "authenticated" && !hasAnyParentRole(roles);

  useEffect(() => {
    if (isAnonymous) router.replace("/login");
    else if (isWrongAudience) router.replace("/");
  }, [isAnonymous, isWrongAudience, router]);

  if (status === "loading" || isAnonymous || isWrongAudience) {
    return (
      <Centered>
        <p className="text-sm text-slate-500">Chargement...</p>
      </Centered>
    );
  }

  return <>{children}</>;
}
