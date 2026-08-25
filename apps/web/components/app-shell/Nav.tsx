"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/lib/auth/useAuth";

type NavItem = {
  href: string;
  label: string;
  permission?: string;
};

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Tableau de bord" },
  { href: "/school", label: "École", permission: "schools.read" },
  { href: "/academics", label: "Académique", permission: "academics.read" },
  { href: "/students", label: "Élèves", permission: "students.read" },
  { href: "/grades", label: "Notes", permission: "grades.read" },
  { href: "/report-cards", label: "Bulletins", permission: "report_cards.read" },
];

export function Nav() {
  const { permissions } = useAuth();
  const pathname = usePathname();

  const items = NAV_ITEMS.filter((item) => !item.permission || permissions.includes(item.permission));

  return (
    <nav className="flex w-56 flex-col gap-1 border-r border-slate-200 bg-white p-4">
      {items.map((item) => {
        const active = pathname === item.href || (item.href !== "/" && pathname.startsWith(`${item.href}/`));
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
    </nav>
  );
}
