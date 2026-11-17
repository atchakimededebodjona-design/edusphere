"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isParentOnlyAccount, isTeacherOnlyAccount } from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/useAuth";

// 2026-11-17 — page ouverte en touchant une notification téléphone (sw/service-worker.js) : le
// serveur ne sait pas dans quel espace se trouve chaque destinataire, cette page l'envoie vers SES
// annonces (parent, enseignant ou administration). Sans session : page de connexion.
export default function OpenNotificationsPage() {
  const { status, user, roles } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "loading") return;
    if (status === "anonymous") {
      router.replace("/login");
      return;
    }
    if (isParentOnlyAccount(roles)) router.replace("/parent/notifications");
    else if (user && isTeacherOnlyAccount(user, roles)) router.replace("/teacher/announcements");
    else router.replace("/notifications");
  }, [status, user, roles, router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-8">
      <p className="text-sm text-slate-500">Ouverture de vos annonces...</p>
    </main>
  );
}
