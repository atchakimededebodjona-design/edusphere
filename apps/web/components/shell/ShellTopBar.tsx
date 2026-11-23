import Link from "next/link";
import type { ReactNode } from "react";
import { BrandSymbol } from "@/components/branding/BrandLogo";
import { PhotoThumb } from "@/components/photos/PhotoThumb";
import { Icon } from "@/components/ui/Icon";

// Refonte, phase 1 (2026-11-23) — barre du haut commune : marque (lien vers la page d'accueil publique),
// choix de l'école (espace administration), cloche avec le nombre de non-lues, photo ou initiales du
// compte, déconnexion. Sur téléphone, la déconnexion passe dans la feuille « Plus » de la barre du bas.
export function ShellTopBar({
  brandHref,
  switcher,
  notificationsHref,
  unreadCount,
  unreadTestId,
  userName,
  roleText,
  photoPath,
  photoVersion,
  photoTestId,
  profileHref,
  logoutLabel,
  onLogout,
}: {
  brandHref: string;
  switcher?: ReactNode;
  notificationsHref: string;
  unreadCount: number;
  unreadTestId?: string;
  userName: string;
  roleText: string;
  photoPath: string | null;
  photoVersion: number;
  photoTestId?: string;
  profileHref?: string;
  logoutLabel: string;
  onLogout: () => void;
}) {
  const identity = (
    <>
      <PhotoThumb path={photoPath} version={photoVersion} name={userName} size="sm" testId={photoTestId} />
      <span className="hidden min-w-0 text-left leading-tight sm:block">
        <span className="block max-w-[12rem] truncate text-sm font-semibold text-slate-900">{userName}</span>
        <span className="block text-xs text-slate-600">{roleText}</span>
      </span>
    </>
  );

  return (
    <header className="sticky top-0 z-40 flex min-h-16 items-center justify-between gap-3 border-b border-slate-200 bg-white/95 px-4 py-2 backdrop-blur md:px-6">
      {/* 2026-11-16 : la marque ramène à la page d'accueil publique ; la session reste ouverte. */}
      <Link href={brandHref} className="flex shrink-0 items-center gap-2 rounded-lg hover:opacity-80" title="Page d'accueil EduLinkage">
        <BrandSymbol className="h-9 w-9" priority />
        <span className="hidden font-display text-lg font-bold text-slate-900 sm:inline">EduLinkage</span>
      </Link>
      <div className="flex min-w-0 items-center gap-2 sm:gap-3">
        {switcher}
        <Link
          href={notificationsHref}
          className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          aria-label="Notifications"
        >
          <Icon name="bell" />
          {unreadCount > 0 && (
            <span
              data-testid={unreadTestId}
              className="absolute right-0.5 top-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-red-600 px-1 text-[11px] font-semibold text-white"
            >
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          )}
        </Link>
        {profileHref ? (
          <Link href={profileHref} title="Mon profil" className="flex min-w-0 items-center gap-2 rounded-lg p-1 hover:bg-slate-100">
            {identity}
          </Link>
        ) : (
          <span className="flex min-w-0 items-center gap-2 p-1">{identity}</span>
        )}
        <button
          type="button"
          onClick={onLogout}
          className="hidden min-h-10 shrink-0 items-center gap-2 rounded-lg border border-slate-300 px-3 text-sm text-slate-700 hover:bg-slate-50 md:inline-flex"
        >
          <Icon name="logout" className="h-4 w-4" />
          {logoutLabel}
        </button>
      </div>
    </header>
  );
}
