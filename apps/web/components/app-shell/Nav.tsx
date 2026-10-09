"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BrandSymbol } from "@/components/branding/BrandLogo";
import { hasTeacherRole, isPartnerOnlyAccount, isPlatformAdmin } from "@/lib/auth/roles";
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
  { href: "/promotions", label: "Réinscriptions", permission: "students.manage" },
  { href: "/attendance", label: "Présences", permission: "attendance.read" },
  { href: "/grades", label: "Notes", permission: "grades.read" },
  { href: "/report-cards", label: "Bulletins", permission: "report_cards.read" },
  { href: "/fees", label: "Frais scolaires", permission: "fees.read" },
  { href: "/fees/overdue", label: "Frais en retard", permission: "fees.read" },
  { href: "/payments", label: "Paiements", permission: "payments.read" },
  { href: "/notifications", label: "Notifications" },
  { href: "/announcements", label: "Annonces", permission: "announcements.manage" },
  { href: "/users", label: "Utilisateurs", permission: "users.read" },
  { href: "/audit-logs", label: "Journal d'audit", permission: "audit.read" },
];

// PR #17 — menus des espaces Plateforme et Partenaire. Filtrés par code de permission pour la
// lisibilité uniquement : CE N'EST PAS UNE FRONTIÈRE DE SÉCURITÉ (chaque endpoint `/platform/*` et
// `/partner/*` vérifie lui-même sa permission côté API, voir app/(app)/AuthGate.tsx).
// Libellés volontairement distincts des cartes du tableau de bord plateforme ("Organisations",
// "Écoles"...) pour ne pas créer d'ambiguïté de texte à l'écran (voir e2e/platform-admin.spec.ts).
const PLATFORM_NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Tableau de bord" },
  { href: "/platform/organizations", label: "Groupes scolaires", permission: "platform.organizations.read" },
  { href: "/platform/schools", label: "Établissements", permission: "platform.schools.read" },
  { href: "/platform/accounts", label: "Comptes", permission: "platform.accounts.read" },
  { href: "/platform/partners", label: "Partenaires", permission: "platform.partners.read" },
];

const PARTNER_NAV_ITEMS: NavItem[] = [
  { href: "/partner", label: "Tableau de bord", permission: "partner.dashboard.read" },
  { href: "/partner/schools", label: "Mes écoles", permission: "partner.schools.read" },
  { href: "/partner/accounts", label: "Comptes", permission: "partner.accounts.read" },
];

export function Nav() {
  const { permissions, user, roles } = useAuth();
  const pathname = usePathname();

  // Un compte plateforme (SUPER_ADMIN) cumule TOUTES les permissions du catalogue RBAC (voir
  // rbac/seed.py) et verrait donc ici la quasi-totalité des liens de gestion scolaire — qui
  // supposent tous une école courante (currentSchoolId), toujours nulle pour ce compte (aucune
  // organisation/école, voir lib/auth/roles.ts::isPlatformAdmin). Seul le tableau de bord
  // (qui bascule lui-même vers la vue plateforme, voir app/(app)/dashboard/page.tsx) a un sens ici.
  // PR #17 — même logique pour un PLATFORM_OWNER (is_platform_admin=true) : uniquement le menu
  // plateforme ; un partenaire pur ne voit que le menu partenaire. Rappel : navigation seulement,
  // jamais un contrôle d'accès (l'API refuse elle-même tout endpoint hors permission).
  const allowed = (item: NavItem) => !item.permission || permissions.includes(item.permission);
  const items = isPlatformAdmin(user)
    ? PLATFORM_NAV_ITEMS.filter(allowed)
    : isPartnerOnlyAccount(user, roles)
      ? PARTNER_NAV_ITEMS.filter(allowed)
      : NAV_ITEMS.filter(allowed);

  // Compte mixte (rôle TEACHER en plus d'un rôle admin/staff) : reste sur l'espace admin par
  // défaut (voir lib/auth/roles.ts::isTeacherOnlyAccount, jamais vrai pour ce cas — aucune
  // redirection automatique), avec un accès explicite vers son espace enseignant. Un enseignant
  // pur ne voit jamais cette barre : AuthGate le renvoie vers /teacher avant même ce rendu.
  const showTeacherLink = !isPlatformAdmin(user) && hasTeacherRole(user, roles);

  return (
    <nav className="flex w-56 flex-col gap-1 border-r border-slate-200 bg-white p-4">
      <div className="mb-4 flex justify-center">
        <BrandSymbol className="h-10 w-10" />
      </div>
      {items.map((item) => {
        // `/partner` est aussi le préfixe de ses sous-pages : correspondance exacte pour cet accueil.
        const active =
          pathname === item.href || (item.href !== "/partner" && pathname.startsWith(`${item.href}/`));
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
      {showTeacherLink && (
        <Link
          href="/teacher"
          className={`rounded px-3 py-2 text-sm font-medium ${
            pathname === "/teacher" || pathname.startsWith("/teacher/")
              ? "bg-slate-900 text-white"
              : "text-slate-700 hover:bg-slate-100"
          }`}
        >
          Espace enseignant
        </Link>
      )}
    </nav>
  );
}
