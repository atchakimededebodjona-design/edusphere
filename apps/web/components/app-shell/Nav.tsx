"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandSymbol } from "@/components/branding/BrandLogo";
import { isPlatformAdmin } from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/useAuth";

type NavItem = {
  href: string;
  label: string;
  permission?: string;
};

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Tableau de bord" },
  { href: "/setup", label: "Mise en place", permission: "academics.manage" },
  { href: "/school", label: "École", permission: "schools.read" },
  { href: "/academics", label: "Académique", permission: "academics.read" },
  { href: "/students", label: "Élèves", permission: "students.read" },
  { href: "/attendance", label: "Présences", permission: "attendance.read" },
  { href: "/grades", label: "Notes", permission: "grades.read" },
  { href: "/report-cards", label: "Bulletins", permission: "report_cards.read" },
  { href: "/fees", label: "Frais scolaires", permission: "fees.read" },
  { href: "/fees/overdue", label: "Frais en retard", permission: "fees.read" },
  { href: "/payments", label: "Paiements", permission: "payments.read" },
  { href: "/notifications", label: "Notifications" },
  { href: "/announcements", label: "Annonces", permission: "announcements.manage" },
  { href: "/users", label: "Utilisateurs", permission: "users.read" },
];

export function Nav() {
  const { permissions, user } = useAuth();
  const pathname = usePathname();

  // Un compte plateforme (SUPER_ADMIN) cumule TOUTES les permissions du catalogue RBAC (voir
  // rbac/seed.py) et verrait donc ici la quasi-totalité des liens de gestion scolaire — qui
  // supposent tous une école courante (currentSchoolId), toujours nulle pour ce compte (aucune
  // organisation/école, voir lib/auth/roles.ts::isPlatformAdmin). Seul le tableau de bord
  // (qui bascule lui-même vers la vue plateforme, voir app/(app)/dashboard/page.tsx) a un sens ici.
  const items = isPlatformAdmin(user)
    ? NAV_ITEMS.filter((item) => item.href === "/dashboard")
    : NAV_ITEMS.filter((item) => !item.permission || permissions.includes(item.permission));

  return (
    <nav className="flex w-56 flex-col gap-1 border-r border-slate-200 bg-white p-4">
      <div className="mb-4 flex justify-center">
        <BrandSymbol className="h-10 w-10" />
      </div>
      {items.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`rounded px-3 py-2 text-sm font-medium ${
              active ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
