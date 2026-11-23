import Link from "next/link";
import { Icon } from "@/components/ui/Icon";
import { Skeleton } from "@/components/ui/Surface";
import { initials } from "@/lib/photos/passport.mjs";
import type { Student } from "@/lib/students/client";

/** Pastille aux initiales de l'enfant (l'espace parent n'affiche pas de photo). */
export function ChildInitials({ child, size = "md" }: { child: Pick<Student, "first_name" | "last_name">; size?: "md" | "lg" }) {
  return (
    <span
      aria-hidden="true"
      className={`flex shrink-0 items-center justify-center rounded-full bg-primary-50 font-display font-bold text-primary-700 ${
        size === "lg" ? "h-14 w-14 text-lg" : "h-11 w-11 text-sm"
      }`}
    >
      {initials(`${child.first_name} ${child.last_name}`)}
    </span>
  );
}

// Refonte, phase 2 (2026-11-23) — carte d'un enfant (accueil et liste « Mes enfants ») : toute la carte
// mène à sa fiche.
export function ChildCard({ child }: { child: Student }) {
  return (
    <Link
      href={`/parent/children/${child.id}`}
      className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 transition-colors hover:border-primary-300 hover:bg-primary-50/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600"
    >
      <ChildInitials child={child} />
      <span className="min-w-0 flex-1">
        <span className="block truncate font-semibold text-slate-900">
          {child.first_name} {child.last_name}
        </span>
        <span className="block text-sm text-slate-600">Matricule {child.matricule}</span>
      </span>
      <span className="flex shrink-0 items-center gap-1 text-sm font-medium text-primary-700">
        <span className="hidden sm:inline">Voir la fiche</span>
        <Icon name="chevronRight" className="h-5 w-5" />
      </span>
    </Link>
  );
}

/** Cartes grises le temps du chargement de la liste des enfants. */
export function ChildrenSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-hidden="true">
      {[0, 1].map((index) => (
        <div key={index} className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4">
          <Skeleton className="h-11 w-11 rounded-full" />
          <div className="flex-1">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="mt-2 h-3 w-24" />
          </div>
        </div>
      ))}
    </div>
  );
}
