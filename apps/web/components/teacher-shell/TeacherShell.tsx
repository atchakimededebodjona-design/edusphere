"use client";

import { NewAnnouncementBanner } from "@/components/notifications/NewAnnouncementBanner";
import { SchoolLogoBlock, ShellFrame, useShellLogout } from "@/components/shell/ShellFrame";
import { ShellTopBar } from "@/components/shell/ShellTopBar";
import { useAuth } from "@/lib/auth/useAuth";
import { TEACHER_MENU, bottomItems } from "@/lib/navigation/menus";
import { useUnreadNotifications } from "@/lib/notifications/useUnreadNotifications";
import { useMyPhoto } from "@/lib/photos/useMyPhoto";

// Portail enseignant. Aucun menu d'administration (École, Utilisateurs, Mise en place, Frais, Paiements) :
// ces entrées n'existent pas dans cet espace. Refonte, phase 1 (2026-11-23) : cadre commun
// (components/shell/ShellFrame.tsx) ; sur téléphone, barre du bas Accueil, Appel, Notes, Élèves, Plus.
export function TeacherShell({ children }: { children: React.ReactNode }) {
  const { user, currentSchool } = useAuth();
  const onLogout = useShellLogout();
  const unread = useUnreadNotifications(Boolean(user));
  const myPhoto = useMyPhoto();
  const logout = () => void onLogout();

  return (
    <ShellFrame
      menu={TEACHER_MENU}
      bottom={bottomItems(TEACHER_MENU, "teacher")}
      sideTitle="Espace enseignant"
      sideSubtitle={currentSchool?.name}
      sideHeader={<SchoolLogoBlock />}
      logoutLabel="Se déconnecter"
      onLogout={logout}
      banner={<NewAnnouncementBanner inboxHref="/teacher/announcements" />}
      topBar={
        <ShellTopBar
          brandHref="/"
          notificationsHref="/teacher/notifications"
          unreadCount={unread.count}
          unreadTestId="teacher-unread-count"
          userName={user?.full_name ?? ""}
          roleText="Enseignant"
          photoPath={myPhoto.path}
          photoVersion={myPhoto.version}
          photoTestId="teacher-header-photo"
          profileHref="/teacher/profile"
          logoutLabel="Se déconnecter"
          onLogout={logout}
        />
      }
    >
      {children}
    </ShellFrame>
  );
}
