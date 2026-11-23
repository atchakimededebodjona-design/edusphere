"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { Modal } from "@/components/ui/Dialog";
import type { MenuGroup, MenuItem } from "@/lib/navigation/menus";

// Refonte, phase 1 (2026-11-23) — barre de navigation fixée en bas sur téléphone : 4 raccourcis du
// quotidien choisis selon le rôle (lib/navigation/menus.ts) et « Plus », qui ouvre le menu complet et la
// déconnexion. Masquée à partir de md (le menu latéral prend le relais).
//
// Sa hauteur réelle est publiée dans --bottom-nav-height : le contenu se réserve cet espace (.shell-main,
// globals.css) et les bandeaux du bas (components/pwa/PwaSupport.tsx) s'affichent juste au-dessus.
export function MobileTabBar({
  items,
  groups,
  active,
  logoutLabel,
  onLogout,
}: {
  items: MenuItem[];
  groups: MenuGroup[];
  active: string | null;
  logoutLabel: string;
  onLogout: () => void;
}) {
  const bar = useRef<HTMLElement>(null);
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  useEffect(() => {
    const element = bar.current;
    if (!element) return;
    const root = document.documentElement;
    const publish = () => {
      const height = element.offsetHeight;
      if (height > 0) {
        root.style.setProperty("--bottom-nav-height", `${height}px`);
        // La barre couvre déjà la zone du geste d'accueil des iPhone : les bandeaux posés au-dessus n'ont
        // pas à la réserver une seconde fois.
        root.style.setProperty("--banner-pad-bottom", "0.5rem");
      } else {
        root.style.removeProperty("--bottom-nav-height");
        root.style.removeProperty("--banner-pad-bottom");
      }
    };
    publish();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(publish);
    observer?.observe(element);
    window.addEventListener("resize", publish);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", publish);
      root.style.removeProperty("--bottom-nav-height");
      root.style.removeProperty("--banner-pad-bottom");
    };
  }, []);

  const inBar = items.some((item) => item.href === active);

  return (
    <>
      <nav
        ref={bar}
        aria-label="Navigation mobile"
        className="fixed inset-x-0 z-40 border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] md:hidden"
        style={{ bottom: 0 }}
      >
        <ul className="grid" style={{ gridTemplateColumns: `repeat(${items.length + 1}, minmax(0, 1fr))` }}>
          {items.map((item) => {
            const isActive = item.href === active;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={isActive ? "page" : undefined}
                  className={`flex min-h-14 flex-col items-center justify-center gap-0.5 px-1 text-[11px] font-medium ${
                    isActive ? "text-primary-700" : "text-slate-600"
                  }`}
                >
                  <Icon name={item.icon} className="h-[22px] w-[22px]" />
                  <span className="max-w-full truncate">{item.short ?? item.label}</span>
                </Link>
              </li>
            );
          })}
          <li>
            <button
              type="button"
              onClick={() => setMenuOpen(true)}
              aria-haspopup="dialog"
              aria-expanded={menuOpen}
              className={`flex min-h-14 w-full flex-col items-center justify-center gap-0.5 px-1 text-[11px] font-medium ${
                active !== null && !inBar ? "text-primary-700" : "text-slate-600"
              }`}
            >
              <Icon name="menu" className="h-[22px] w-[22px]" />
              <span>Plus</span>
            </button>
          </li>
        </ul>
      </nav>

      <Modal open={menuOpen} onClose={() => setMenuOpen(false)} title="Menu" placement="sheet">
        <nav aria-label="Menu complet" className="flex flex-col gap-4">
          {groups.map((group, index) => (
            <div key={group.title ?? `group-${index}`} className="flex flex-col gap-1">
              {group.title && (
                <p className="px-2 text-xs font-semibold uppercase tracking-wider text-slate-600">{group.title}</p>
              )}
              {group.items.map((item) => {
                const isActive = item.href === active;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={isActive ? "page" : undefined}
                    onClick={() => setMenuOpen(false)}
                    className={`flex min-h-12 items-center gap-3 rounded-lg px-2 text-sm font-medium ${
                      isActive ? "bg-primary-50 text-primary-800" : "text-slate-800 hover:bg-slate-100"
                    }`}
                  >
                    <Icon name={item.icon} className="h-5 w-5 shrink-0 text-slate-600" />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          ))}
          <button
            type="button"
            onClick={() => {
              setMenuOpen(false);
              onLogout();
            }}
            className="flex min-h-12 items-center gap-3 rounded-lg border-t border-slate-200 px-2 pt-2 text-sm font-medium text-red-700 hover:bg-red-50"
          >
            <Icon name="logout" className="h-5 w-5 shrink-0" />
            {logoutLabel}
          </button>
        </nav>
      </Modal>
    </>
  );
}
