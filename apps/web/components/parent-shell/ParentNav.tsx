"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/parent", label: "Tableau de bord" },
  { href: "/parent/children", label: "Mes enfants" },
  { href: "/parent/notifications", label: "Notifications" },
];

// Barre horizontale (pas de colonne latérale fixe comme components/app-shell/Nav.tsx) :
// mobile-first, se replie naturellement en largeur téléphone grâce à `flex-wrap`, contrairement à
// une colonne de 224px qui grignoterait l'essentiel de l'écran sur un petit appareil.
export function ParentNav() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-wrap gap-1 border-b border-slate-200 bg-white px-4 py-2 sm:px-6">
      {NAV_ITEMS.map((item) => {
        const active = pathname === item.href || (item.href !== "/parent" && pathname.startsWith(`${item.href}/`));
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`rounded px-3 py-1.5 text-sm font-medium ${
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
