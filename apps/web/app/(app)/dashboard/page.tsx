"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { isPlatformAdmin } from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/useAuth";
import { schoolRoleCodes } from "@/lib/navigation/menus";
import { PlatformDashboard } from "./PlatformDashboard";
import { SchoolDashboard } from "./SchoolDashboard";

// Accueil selon le rôle (refonte, validé le 2026-11-23) : un compte qui n'a que le rôle caisse dans l'école
// arrive directement sur la caisse. Simple redirection d'affichage : les droits restent vérifiés par l'API.
export default function DashboardPage() {
  const { user, roles, currentSchoolId, currentOrganizationId } = useAuth();
  const router = useRouter();
  const codes = schoolRoleCodes(roles, currentSchoolId, currentOrganizationId);
  const cashierOnly = !isPlatformAdmin(user) && codes.length > 0 && codes.every((code) => code === "CAISSIER");

  useEffect(() => {
    if (cashierOnly) router.replace("/cashier");
  }, [cashierOnly, router]);

  if (cashierOnly) return <p className="text-sm text-slate-600">Ouverture de la caisse...</p>;
  return isPlatformAdmin(user) ? <PlatformDashboard /> : <SchoolDashboard />;
}
