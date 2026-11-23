"use client";

import { TenantSwitcher } from "@/components/app-shell/TenantSwitcher";
import { NewAnnouncementBanner } from "@/components/notifications/NewAnnouncementBanner";
import { SchoolLogoBlock, ShellFrame, useShellLogout } from "@/components/shell/ShellFrame";
import { ShellTopBar } from "@/components/shell/ShellTopBar";
import { hasTeacherRole, isPartnerOnlyAccount, isPlatformAdmin } from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/useAuth";
import {
  MENUS,
  allowedMenu,
  bottomItems,
  bottomProfile,
  roleLabel,
  schoolRoleCodes,
  type MenuGroup,
  type Space,
} from "@/lib/navigation/menus";
import { useUnreadNotifications } from "@/lib/notifications/useUnreadNotifications";
import { useMyPhoto } from "@/lib/photos/useMyPhoto";

// Espace administration (écoles), plateforme et partenaire. Refonte, phase 1 (2026-11-23) : cadre commun
// (components/shell/ShellFrame.tsx), menu regroupé avec icônes, barre du bas sur téléphone. Les entrées
// et leurs permissions sont celles d'avant (lib/navigation/menus.ts).
export function AppShell({ children }: { children: React.ReactNode }) {
  const { user, roles, permissions, currentSchool, currentSchoolId, currentOrganizationId } = useAuth();
  const onLogout = useShellLogout();
  const unread = useUnreadNotifications(Boolean(user));
  const myPhoto = useMyPhoto();

  const space: Space = isPlatformAdmin(user) ? "platform" : isPartnerOnlyAccount(user, roles) ? "partner" : "school";
  const codes = schoolRoleCodes(roles, currentSchoolId, currentOrganizationId);
  const menu: MenuGroup[] = allowedMenu(MENUS[space], permissions);
  // Compte à la fois administration et enseignant : passage vers l'espace enseignant, comme avant.
  if (space === "school" && hasTeacherRole(user, roles)) {
    menu.push({ title: "Autres espaces", items: [{ href: "/teacher", label: "Espace enseignant", icon: "board" }] });
  }
  const bottom = bottomItems(menu, bottomProfile(space, codes));
  const sideTitle = space === "platform" ? "Plateforme" : space === "partner" ? "Espace partenaire" : "Administration";
  const logout = () => void onLogout();

  return (
    <ShellFrame
      menu={menu}
      bottom={bottom}
      sideTitle={sideTitle}
      sideSubtitle={space === "school" ? currentSchool?.name : undefined}
      sideHeader={space === "school" ? <SchoolLogoBlock /> : null}
      logoutLabel="Déconnexion"
      onLogout={logout}
      banner={<NewAnnouncementBanner inboxHref="/notifications" />}
      topBar={
        <ShellTopBar
          brandHref="/"
          switcher={user ? <TenantSwitcher /> : null}
          notificationsHref="/notifications"
          unreadCount={unread.count}
          userName={user?.full_name ?? ""}
          roleText={roleLabel(space, codes)}
          photoPath={myPhoto.path}
          photoVersion={myPhoto.version}
          logoutLabel="Déconnexion"
          onLogout={logout}
        />
      }
    >
      {children}
    </ShellFrame>
  );
}
