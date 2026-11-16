"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { BrandSymbol } from "@/components/branding/BrandLogo";
import { useAuth } from "@/lib/auth/useAuth";
import { confirmLogoutWithUnsentEntries } from "@/lib/offline/outbox";
import { useCurrentSchoolLogo } from "@/lib/schools/useSchoolLogo";

// Navigation dédiée au portail enseignant. Aucun menu d'administration (École, Utilisateurs, Mise en
// place, Frais, Paiements) : ces entrées n'existent pas dans cet espace.
export const TEACHER_NAV = [
  { href: "/teacher", label: "Tableau de bord" },
  { href: "/teacher/classes", label: "Mes classes" },
  { href: "/teacher/students", label: "Mes élèves" },
  { href: "/teacher/attendance", label: "Présences" },
  { href: "/teacher/grades", label: "Notes & évaluations" },
  { href: "/teacher/report-cards", label: "Bulletins" },
  { href: "/teacher/announcements", label: "Annonces" },
  { href: "/teacher/notifications", label: "Notifications" },
  { href: "/teacher/profile", label: "Mon profil" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/teacher") return pathname === "/teacher";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function TeacherShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, currentSchool } = useAuth();
  const schoolLogo = useCurrentSchoolLogo();

  async function handleLogout() {
    // Phase 32, lot 2 — des saisies non envoyées (appel, notes) seraient perdues : on prévient.
    if (!(await confirmLogoutWithUnsentEntries())) return;
    await logout();
    router.replace("/login");
  }

  return (
    <div className="min-h-screen bg-slate-50 md:flex">
      <aside className="hidden w-60 shrink-0 flex-col bg-brand-navy px-4 py-6 text-slate-100 md:flex">
        {/* 2026-11-16 : logo de l'école de l'enseignant (même source que le menu de l'espace
            administration, voir lib/schools/useSchoolLogo.ts), posé sur une pastille blanche pour
            rester lisible sur ce fond sombre. Place réservée pendant le chargement ; rien sans logo.
            La marque EduLinkage est dans la barre du haut. */}
        {(schoolLogo.url || schoolLogo.pending) && (
          <div
            className={`mb-4 flex h-24 items-center justify-center rounded-lg p-2 ${schoolLogo.url ? "bg-white" : ""}`}
          >
            {schoolLogo.url && (
              // Blob authentifié : next/image ne s'applique pas.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={schoolLogo.url}
                alt={currentSchool ? `Logo de ${currentSchool.name}` : "Logo de l'école"}
                className="h-20 w-auto max-w-full object-contain"
              />
            )}
          </div>
        )}
        <p className="px-2 text-sm font-semibold">Espace enseignant</p>
        <p className="px-2 pb-6 text-xs text-slate-400">{currentSchool?.name ?? ""}</p>
        <nav aria-label="Navigation enseignant" className="flex flex-col gap-1">
          {TEACHER_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              aria-current={isActive(pathname, item.href) ? "page" : undefined}
              className={`rounded px-3 py-2 text-sm ${isActive(pathname, item.href) ? "bg-white/15 font-medium" : "text-slate-300 hover:bg-white/10"}`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* 2026-11-16 : marque EduLinkage, qui ramène à la page d'accueil publique comme dans l'espace
            administration (components/app-shell/TopBar.tsx). La session reste ouverte : « Mon
            espace » y ramène ici (/dashboard renvoie un enseignant vers /teacher). */}
        <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-slate-200 bg-white px-4 py-3">
          <Link href="/" className="flex items-center gap-2 rounded hover:opacity-80" title="Page d'accueil EduLinkage">
            <BrandSymbol className="h-9 w-9" priority />
            <span className="text-lg font-bold text-slate-900">EduLinkage</span>
          </Link>
          <div className="flex min-w-0 items-center gap-4">
            <div className="min-w-0 text-right">
              <p className="truncate text-sm font-semibold text-slate-900">{user?.full_name ?? ""}</p>
              <p className="text-xs text-slate-500">Enseignant</p>
            </div>
            <button type="button" onClick={handleLogout} className="shrink-0 text-sm text-slate-600 underline">
              Se déconnecter
            </button>
          </div>
        </header>

        {/* Navigation mobile : barre horizontale défilante, mêmes entrées que la barre latérale. */}
        <nav aria-label="Navigation enseignant mobile" className="flex gap-2 overflow-x-auto border-b border-slate-200 bg-white px-3 py-2 md:hidden">
          {TEACHER_NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`shrink-0 rounded-full px-3 py-1 text-xs ${isActive(pathname, item.href) ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-700"}`}
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <main className="flex-1 p-4 md:p-8">{children}</main>
      </div>
    </div>
  );
}
