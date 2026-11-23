"use client";

import { NewAnnouncementBanner } from "@/components/notifications/NewAnnouncementBanner";
import { ShellFrame, useShellLogout } from "@/components/shell/ShellFrame";
import { ShellTopBar } from "@/components/shell/ShellTopBar";
import { useAuth } from "@/lib/auth/useAuth";
import { PARENT_MENU, bottomItems } from "@/lib/navigation/menus";
import { useUnreadNotifications } from "@/lib/notifications/useUnreadNotifications";
import { useMyPhoto } from "@/lib/photos/useMyPhoto";

// Espace parent. Refonte, phase 1 (2026-11-23) : même cadre que les autres espaces
// (components/shell/ShellFrame.tsx). Sur téléphone, où il est surtout consulté, barre du bas (Accueil,
// Enfants, Notifications, Plus) au lieu des onglets du haut.
export function ParentShell({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const onLogout = useShellLogout();
  const unread = useUnreadNotifications(Boolean(user));
  const myPhoto = useMyPhoto();
  const logout = () => void onLogout();

  return (
    <ShellFrame
      menu={PARENT_MENU}
      bottom={bottomItems(PARENT_MENU, "parent")}
      sideTitle="Espace parent"
      logoutLabel="Déconnexion"
      onLogout={logout}
      banner={<NewAnnouncementBanner inboxHref="/parent/notifications" />}
      topBar={
        <ShellTopBar
          brandHref="/parent"
          notificationsHref="/parent/notifications"
          unreadCount={unread.count}
          userName={user?.full_name ?? ""}
          roleText="Parent"
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
