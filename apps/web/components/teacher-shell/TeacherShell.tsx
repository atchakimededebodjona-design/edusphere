"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth/useAuth";

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
  const { user, logout } = useAuth();

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  return (
    <div className="min-h-screen bg-slate-50 md:flex">
      <aside className="hidden w-60 shrink-0 flex-col bg-brand-navy px-4 py-6 text-slate-100 md:flex">
        <p className="px-2 text-sm font-semibold">Espace enseignant</p>
        <p className="px-2 pb-6 text-xs text-slate-400">EduLinkage</p>
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
        <header className="flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-900">{user?.full_name ?? ""}</p>
            <p className="text-xs text-slate-500">Enseignant</p>
          </div>
          <button type="button" onClick={handleLogout} className="text-sm text-slate-600 underline">
            Se déconnecter
          </button>
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
