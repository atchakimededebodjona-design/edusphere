"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { TeacherShell } from "@/components/teacher-shell/TeacherShell";
import { hasTeacherRole } from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/useAuth";

// Garde frontend du portail enseignant : seul un compte porteur d'un rôle TEACHER scopé à une école
// y entre. Les autres comptes (STAFF, DIRECTOR, SCHOOL_ADMIN, platform admin) sont renvoyés vers
// l'espace admin. La protection réelle est côté backend (apps/api/app/modules/teacher/service.py).
export function TeacherGate({ children }: { children: React.ReactNode }) {
  const { status, user, roles } = useAuth();
  const router = useRouter();
  const allowed = status === "authenticated" && hasTeacherRole(user, roles);

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
    else if (status === "authenticated" && !hasTeacherRole(user, roles)) router.replace("/dashboard");
  }, [status, user, roles, router]);

  if (!allowed) {
    return <p className="p-6 text-sm text-slate-400">Vérification des droits...</p>;
  }
  return <TeacherShell>{children}</TeacherShell>;
}
