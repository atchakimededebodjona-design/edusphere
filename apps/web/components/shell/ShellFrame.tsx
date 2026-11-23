"use client";

import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";
import { MobileTabBar } from "@/components/shell/MobileTabBar";
import { SideNav } from "@/components/shell/SideNav";
import { useAuth } from "@/lib/auth/useAuth";
import { activeHref, type MenuGroup, type MenuItem } from "@/lib/navigation/menus";
import { confirmLogoutWithUnsentEntries } from "@/lib/offline/outbox";
import { useCurrentSchoolLogo } from "@/lib/schools/useSchoolLogo";

// Refonte, phase 1 (2026-11-23) — cadre commun des espaces connectés (administration, plateforme,
// partenaire, enseignant, parent) : menu latéral sur ordinateur, barre du haut, contenu, barre du bas sur
// téléphone. Chaque espace ne fournit que son menu et sa barre du haut.
export function ShellFrame({
  menu,
  bottom,
  sideTitle,
  sideSubtitle,
  sideHeader,
  topBar,
  banner,
  logoutLabel,
  onLogout,
  children,
}: {
  menu: MenuGroup[];
  bottom: MenuItem[];
  sideTitle: string;
  sideSubtitle?: string;
  sideHeader?: ReactNode;
  topBar: ReactNode;
  banner?: ReactNode;
  logoutLabel: string;
  onLogout: () => void;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const active = activeHref(pathname, menu.flatMap((group) => group.items.map((item) => item.href)));

  return (
    <div className="min-h-screen bg-slate-50 md:flex">
      <SideNav groups={menu} active={active} title={sideTitle} subtitle={sideSubtitle} header={sideHeader} />
      <div className="flex min-w-0 flex-1 flex-col">
        {topBar}
        <main className="shell-main min-w-0 flex-1 px-4 pt-4 md:px-8 md:pt-8">
          {banner}
          {children}
        </main>
      </div>
      <MobileTabBar items={bottom} groups={menu} active={active} logoutLabel={logoutLabel} onLogout={onLogout} />
    </div>
  );
}

/** Déconnexion commune : prévient si des saisies ou encaissements n'ont pas encore été envoyés. */
export function useShellLogout(): () => Promise<void> {
  const { logout } = useAuth();
  const router = useRouter();
  return async () => {
    if (!(await confirmLogoutWithUnsentEntries())) return;
    await logout();
    router.replace("/login");
  };
}

/** Logo de l'école en tête du menu latéral, sur une pastille blanche (lisible sur le navy) ; place gardée
 * pendant le chargement, rien sans logo. */
export function SchoolLogoBlock() {
  const { currentSchool } = useAuth();
  const logo = useCurrentSchoolLogo();
  if (!logo.url && !logo.pending) return null;
  return (
    <div className={`flex h-24 items-center justify-center rounded-xl p-2 ${logo.url ? "bg-white" : ""}`}>
      {logo.url && (
        // Blob authentifié : next/image ne s'applique pas.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={logo.url}
          alt={currentSchool ? `Logo de ${currentSchool.name}` : "Logo de l'école"}
          className="h-20 w-auto max-w-full object-contain"
        />
      )}
    </div>
  );
}
