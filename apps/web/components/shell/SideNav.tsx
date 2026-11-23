import Link from "next/link";
import type { ReactNode } from "react";
import { Icon } from "@/components/ui/Icon";
import type { MenuGroup } from "@/lib/navigation/menus";

// Refonte, phase 1 (2026-11-23) — menu latéral commun à tous les espaces (ordinateur et tablette) : fond
// navy de la marque, entrées regroupées avec icônes, entrée active en bleu. Masqué sur téléphone, où la
// barre du bas et la feuille « Plus » prennent le relais (components/shell/MobileTabBar.tsx).
export function SideNav({
  groups,
  active,
  title,
  subtitle,
  header,
}: {
  groups: MenuGroup[];
  active: string | null;
  title: string;
  subtitle?: string;
  header?: ReactNode;
}) {
  return (
    <aside className="hidden w-64 shrink-0 flex-col gap-4 bg-navy px-3 py-5 text-slate-100 md:sticky md:top-0 md:flex md:h-screen md:overflow-y-auto">
      {header}
      <div className="px-3">
        <p className="font-display text-sm font-bold text-white">{title}</p>
        {subtitle && <p className="truncate text-xs text-slate-400">{subtitle}</p>}
      </div>
      <nav aria-label="Navigation principale" className="flex flex-col gap-4">
        {groups.map((group, index) => (
          <div key={group.title ?? `group-${index}`} className="flex flex-col gap-0.5">
            {group.title && (
              <p className="px-3 pb-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">{group.title}</p>
            )}
            {group.items.map((item) => {
              const isActive = item.href === active;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={isActive ? "page" : undefined}
                  className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    isActive ? "bg-primary-600 text-white" : "text-slate-300 hover:bg-white/10 hover:text-white"
                  }`}
                >
                  <Icon name={item.icon} className="h-[18px] w-[18px] shrink-0" />
                  <span className="min-w-0">{item.label}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}
