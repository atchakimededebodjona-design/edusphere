"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { ApiError } from "@/lib/api/client";
import { parentChildren } from "@/lib/parent/client";
import type { Student } from "@/lib/students/client";
import { ChildAttendance } from "@/app/parent/children/[id]/ChildAttendance";
import { ChildGrades } from "@/app/parent/children/[id]/ChildGrades";
import { ChildReportCards } from "@/app/parent/children/[id]/ChildReportCards";
import { ChildFees } from "@/app/parent/children/[id]/ChildFees";

type TabKey = "attendance" | "grades" | "report-cards" | "fees";

const TABS: { key: TabKey; label: string }[] = [
  { key: "attendance", label: "Présence" },
  { key: "grades", label: "Notes" },
  { key: "report-cards", label: "Bulletins" },
  { key: "fees", label: "Frais" },
];

// Sécurité : la liste `/parent/children` est déjà scopée côté serveur à l'utilisateur courant
// (voir apps/api/app/modules/parent/service.py::list_children). Trouver l'enfant par id dans
// cette liste n'est qu'une commodité d'affichage (nom, matricule) — ce n'est JAMAIS ce qui protège
// les données : chaque onglet ci-dessous refait son propre appel `/parent/children/{id}/...`, qui
// revalide indépendamment côté serveur que cet élève est bien un enfant de l'utilisateur courant
// (`_get_child_or_404`). Un id dans l'URL n'est donc jamais une preuve d'autorisation à lui seul.
export default function ChildDetailPage() {
  const params = useParams<{ id: string }>();
  const studentId = params.id;

  const [children, setChildren] = useState<Student[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>("attendance");

  const load = useCallback(() => {
    setError(null);
    setChildren(null);
    parentChildren
      .list()
      .then(setChildren)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) return <ErrorRetry message={error} onRetry={load} />;
  if (children === null) return <p className="text-sm text-slate-500">Chargement...</p>;

  const child = children.find((c) => c.id === studentId);
  if (!child) {
    return (
      <p className="max-w-md text-sm text-slate-600">
        Cet élève n&apos;est pas rattaché à votre compte, ou n&apos;existe pas.
      </p>
    );
  }

  return (
    <div className="flex max-w-3xl flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">
          {child.first_name} {child.last_name}
        </h1>
        <p className="text-sm text-slate-500">Matricule {child.matricule}</p>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`rounded-t px-3 py-2 text-sm font-medium ${
              tab === t.key ? "border-b-2 border-slate-900 text-slate-900" : "text-slate-500 hover:text-slate-800"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="pt-2">
        {tab === "attendance" && <ChildAttendance studentId={child.id} />}
        {tab === "grades" && <ChildGrades studentId={child.id} />}
        {tab === "report-cards" && (
          <ChildReportCards studentId={child.id} studentLabel={`${child.first_name}_${child.last_name}`} />
        )}
        {tab === "fees" && <ChildFees studentId={child.id} />}
      </div>
    </div>
  );
}
