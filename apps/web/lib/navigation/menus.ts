// Refonte, phase 1 (2026-11-23) — navigation de tous les espaces connectés, au même endroit : menus
// regroupés avec icônes (menu latéral sur ordinateur, feuille « Plus » sur téléphone) et choix des
// entrées de la barre du bas selon le rôle. Mêmes routes, mêmes libellés et mêmes permissions
// qu'avant : le menu n'est qu'un confort, l'API reste seule juge des droits.
import type { IconName } from "@/components/ui/Icon";
import type { RoleAssignment } from "@/lib/auth/client";

export type MenuItem = {
  href: string;
  label: string;
  icon: IconName;
  /** Permission nécessaire pour afficher l'entrée (aucune : toujours affichée). */
  permission?: string;
  /** Libellé court de la barre du bas sur téléphone. */
  short?: string;
};

export type MenuGroup = { title: string | null; items: MenuItem[] };

export type Space = "school" | "platform" | "partner" | "teacher" | "parent";

export const SCHOOL_MENU: MenuGroup[] = [
  { title: null, items: [{ href: "/dashboard", label: "Tableau de bord", icon: "grid", short: "Accueil" }] },
  {
    title: "Scolarité",
    items: [
      { href: "/students", label: "Élèves", icon: "student", permission: "students.read" },
      { href: "/promotions", label: "Réinscriptions", icon: "repeat", permission: "students.manage" },
      { href: "/attendance", label: "Présences", icon: "checkSquare", permission: "attendance.read" },
      { href: "/grades", label: "Notes", icon: "chart", permission: "grades.read" },
      { href: "/report-cards", label: "Bulletins", icon: "fileText", permission: "report_cards.read" },
    ],
  },
  {
    title: "Finances",
    items: [
      { href: "/fees", label: "Frais scolaires", icon: "wallet", permission: "fees.read", short: "Frais" },
      { href: "/fees/overdue", label: "Frais en retard", icon: "clock", permission: "fees.read", short: "Retards" },
      { href: "/cashier", label: "Caisse", icon: "cash", permission: "payments.manage" },
      { href: "/cashier/cash-register", label: "Ma caisse", icon: "register", permission: "cash.register.manage" },
      { href: "/cashier/supervision", label: "Supervision caisse", icon: "shield", permission: "cash.register.review", short: "Supervision" },
      { href: "/payments", label: "Paiements", icon: "receipt", permission: "payments.read" },
    ],
  },
  {
    title: "Communication",
    items: [
      { href: "/announcements", label: "Annonces", icon: "megaphone", permission: "announcements.manage" },
      { href: "/notifications", label: "Notifications", icon: "bell" },
    ],
  },
  {
    title: "Établissement",
    items: [
      { href: "/school", label: "École", icon: "school", permission: "schools.read" },
      { href: "/setup", label: "Mise en place", icon: "listChecks", permission: "academics.manage" },
      { href: "/academics", label: "Académique", icon: "layers", permission: "academics.read" },
      { href: "/users", label: "Utilisateurs", icon: "users", permission: "users.read" },
      { href: "/subscription", label: "Abonnement", icon: "card", permission: "subscriptions.read" },
      { href: "/audit-logs", label: "Journal d'audit", icon: "clipboard", permission: "audit.read", short: "Audit" },
    ],
  },
];

export const PLATFORM_MENU: MenuGroup[] = [
  { title: null, items: [{ href: "/dashboard", label: "Tableau de bord", icon: "grid", short: "Accueil" }] },
  {
    title: "Clients",
    items: [
      { href: "/platform/organizations", label: "Groupes scolaires", icon: "building", permission: "platform.organizations.read", short: "Groupes" },
      { href: "/platform/schools", label: "Établissements", icon: "school", permission: "platform.schools.read", short: "Écoles" },
      { href: "/platform/accounts", label: "Comptes", icon: "users", permission: "platform.accounts.read" },
    ],
  },
  {
    title: "Revenus",
    items: [
      { href: "/platform/subscriptions", label: "Abonnements", icon: "card", permission: "platform.subscriptions.read" },
      { href: "/platform/subscription-invoices", label: "Factures d'abonnement", icon: "receipt", permission: "platform.subscriptions.read", short: "Factures" },
      { href: "/platform/subscription-grids", label: "Grille tarifaire", icon: "table", permission: "platform.subscriptions.read", short: "Tarifs" },
      { href: "/platform/commissions", label: "Commissions", icon: "percent", permission: "platform.commissions.read" },
    ],
  },
  {
    title: "Réseau",
    items: [{ href: "/platform/partners", label: "Partenaires", icon: "link", permission: "platform.partners.read" }],
  },
];

export const PARTNER_MENU: MenuGroup[] = [
  {
    title: null,
    items: [
      { href: "/partner", label: "Tableau de bord", icon: "grid", permission: "partner.dashboard.read", short: "Accueil" },
      { href: "/partner/schools", label: "Mes écoles", icon: "school", permission: "partner.schools.read", short: "Écoles" },
      { href: "/partner/accounts", label: "Comptes", icon: "users", permission: "partner.accounts.read" },
      { href: "/partner/commissions", label: "Mes commissions", icon: "percent", permission: "partner.commissions.read", short: "Commissions" },
    ],
  },
];

export const TEACHER_MENU: MenuGroup[] = [
  { title: null, items: [{ href: "/teacher", label: "Tableau de bord", icon: "grid", short: "Accueil" }] },
  {
    title: "Mes classes",
    items: [
      { href: "/teacher/classes", label: "Mes classes", icon: "board", short: "Classes" },
      { href: "/teacher/students", label: "Mes élèves", icon: "student", short: "Élèves" },
      { href: "/teacher/attendance", label: "Présences", icon: "checkSquare", short: "Appel" },
      { href: "/teacher/grades", label: "Notes & évaluations", icon: "chart", short: "Notes" },
      { href: "/teacher/report-cards", label: "Bulletins", icon: "fileText" },
    ],
  },
  {
    title: "Communication",
    items: [
      { href: "/teacher/announcements", label: "Annonces", icon: "megaphone" },
      { href: "/teacher/notifications", label: "Notifications", icon: "bell" },
    ],
  },
  { title: "Compte", items: [{ href: "/teacher/profile", label: "Mon profil", icon: "user", short: "Profil" }] },
];

export const PARENT_MENU: MenuGroup[] = [
  {
    title: null,
    items: [
      { href: "/parent", label: "Tableau de bord", icon: "grid", short: "Accueil" },
      { href: "/parent/children", label: "Mes enfants", icon: "users", short: "Enfants" },
      { href: "/parent/notifications", label: "Notifications", icon: "bell" },
    ],
  },
];

export const MENUS: Record<Space, MenuGroup[]> = {
  school: SCHOOL_MENU,
  platform: PLATFORM_MENU,
  partner: PARTNER_MENU,
  teacher: TEACHER_MENU,
  parent: PARENT_MENU,
};

/** Menu réduit aux entrées permises ; les groupes vides disparaissent. */
export function allowedMenu(groups: MenuGroup[], permissions: string[]): MenuGroup[] {
  return groups
    .map((group) => ({ ...group, items: group.items.filter((item) => !item.permission || permissions.includes(item.permission)) }))
    .filter((group) => group.items.length > 0);
}

/** Entrée active : la plus longue adresse qui correspond à la page (« Ma caisse » plutôt que « Caisse »). */
export function activeHref(pathname: string, hrefs: string[]): string | null {
  let best: string | null = null;
  for (const href of hrefs) {
    const matches = pathname === href || pathname.startsWith(`${href}/`);
    if (matches && (best === null || href.length > best.length)) best = href;
  }
  return best;
}

// Barre du bas sur téléphone : les écrans du quotidien de chaque profil, dans cet ordre (les entrées non
// permises sont sautées), puis « Plus » qui ouvre le menu complet.
const BOTTOM_PRIORITY: Record<string, string[]> = {
  school: ["/dashboard", "/students", "/payments", "/announcements", "/attendance", "/notifications"],
  cashier: ["/cashier", "/cashier/cash-register", "/payments", "/notifications"],
  accountant: ["/dashboard", "/fees", "/payments", "/fees/overdue"],
  platform: ["/dashboard", "/platform/schools", "/platform/subscription-invoices", "/platform/accounts"],
  partner: ["/partner", "/partner/schools", "/partner/commissions", "/partner/accounts"],
  teacher: ["/teacher", "/teacher/attendance", "/teacher/grades", "/teacher/students"],
  parent: ["/parent", "/parent/children", "/parent/notifications"],
};

const BOTTOM_SIZE = 4;

/** Profil de la barre du bas : dans l'espace école, la caisse et la comptabilité ont leurs propres raccourcis. */
export function bottomProfile(space: Space, schoolRoleCodes: string[]): string {
  if (space !== "school" || schoolRoleCodes.length === 0) return space;
  if (schoolRoleCodes.every((code) => code === "CAISSIER")) return "cashier";
  if (schoolRoleCodes.every((code) => code === "ACCOUNTANT")) return "accountant";
  return "school";
}

export function bottomItems(groups: MenuGroup[], profile: string): MenuItem[] {
  const all = groups.flatMap((group) => group.items);
  const byHref = new Map(all.map((item) => [item.href, item]));
  const picked: MenuItem[] = [];
  for (const href of BOTTOM_PRIORITY[profile] ?? []) {
    const item = byHref.get(href);
    if (item && picked.length < BOTTOM_SIZE) picked.push(item);
  }
  for (const item of all) {
    if (picked.length >= BOTTOM_SIZE) break;
    if (!picked.includes(item)) picked.push(item);
  }
  return picked;
}

/** Rôles du compte qui s'appliquent à l'école choisie (rôle de l'école, ou rôle de l'organisation sans école). */
export function schoolRoleCodes(roles: RoleAssignment[], schoolId: string | null, organizationId: string | null): string[] {
  return roles
    .filter((role) => (schoolId !== null && role.school_id === schoolId) || (role.school_id === null && role.organization_id !== null && role.organization_id === organizationId))
    .map((role) => role.role_code);
}

const ROLE_LABELS: Record<string, string> = {
  SCHOOL_ADMIN: "Administration",
  DIRECTOR: "Direction",
  ACCOUNTANT: "Comptabilité",
  CAISSIER: "Caisse",
  STAFF: "Personnel",
  TEACHER: "Enseignant",
  PARENT: "Parent",
};

export function roleLabel(space: Space, codes: string[]): string {
  if (space === "platform") return "Plateforme";
  if (space === "partner") return "Partenaire";
  if (space === "teacher") return "Enseignant";
  if (space === "parent") return "Parent";
  for (const code of ["SCHOOL_ADMIN", "DIRECTOR", "ACCOUNTANT", "CAISSIER", "STAFF", "TEACHER"]) {
    if (codes.includes(code)) return ROLE_LABELS[code];
  }
  return "Administration";
}
