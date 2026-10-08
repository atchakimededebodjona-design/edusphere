"use client";

import { useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { auditLogs, type AuditLogsPage } from "@/lib/audit/client";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { users, type UserWithRoles } from "@/lib/users/client";

const PAGE_SIZE = 20;

// Valeurs documentées par audit/service.py (ACTION_*) — même liste côté frontend, aucune
// nouvelle action n'apparaît ici tant qu'un futur PR ne l'ajoute pas des deux côtés.
const ACTION_LABELS: Record<string, string> = {
  "payment.cancelled": "Paiement annulé",
  "student_fee.amount_due_adjusted": "Montant dû ajusté",
  "user.role_changed": "Rôle utilisateur changé",
  "user.status_changed": "Statut utilisateur changé",
  "report_card.published": "Bulletin publié",
  "students.bulk_promoted": "Promotion en masse",
  "students.bulk_assigned": "Affectation en masse",
};

const ENTITY_TYPE_LABELS: Record<string, string> = {
  Payment: "Paiement",
  StudentFee: "Frais élève",
  User: "Utilisateur",
  ReportCard: "Bulletin",
  StudentPromotion: "Promotion",
  StudentAssignment: "Affectation",
};

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

export default function AuditLogsPageView() {
  const { currentSchoolId } = useAuth();
  const [page, setPage] = useState(1);
  const [actionFilter, setActionFilter] = useState("");
  const [entityTypeFilter, setEntityTypeFilter] = useState("");
  const [actorFilter, setActorFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const [members, setMembers] = useState<UserWithRoles[]>([]);
  const [data, setData] = useState<AuditLogsPage | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  async function reload(schoolId: string) {
    setLoadError(null);
    try {
      const result = await auditLogs.list(schoolId, {
        page,
        pageSize: PAGE_SIZE,
        action: actionFilter || undefined,
        entityType: entityTypeFilter || undefined,
        actorUserId: actorFilter || undefined,
        dateFrom: dateFrom || undefined,
        dateTo: dateTo || undefined,
      });
      setData(result);
    } catch (err) {
      setLoadError(toErrorMessage(err));
    }
  }

  useEffect(() => {
    if (currentSchoolId) void reload(currentSchoolId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSchoolId, page, actionFilter, entityTypeFilter, actorFilter, dateFrom, dateTo]);

  useEffect(() => {
    if (currentSchoolId) void users.list(currentSchoolId).then(setMembers).catch(() => setMembers([]));
  }, [currentSchoolId]);

  function resetToFirstPage<T>(setter: (value: T) => void) {
    return (value: T) => {
      setPage(1);
      setter(value);
    };
  }

  if (loadError) {
    return <ErrorRetry message={loadError} onRetry={() => currentSchoolId && void reload(currentSchoolId)} />;
  }

  if (!currentSchoolId || data === null) {
    return <p className="text-sm text-slate-500">Chargement...</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Journal d&apos;audit</h1>
        <p className="text-sm text-slate-500">
          {data.total} événement(s){data.total > 0 ? ` — page ${data.page} / ${data.total_pages}` : ""}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="flex flex-col gap-1 text-sm text-slate-600">
          Du
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => resetToFirstPage(setDateFrom)(e.target.value)}
            className="rounded border border-slate-300 px-2 py-1"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-600">
          Au
          <input
            type="date"
            value={dateTo}
            onChange={(e) => resetToFirstPage(setDateTo)(e.target.value)}
            className="rounded border border-slate-300 px-2 py-1"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-600">
          Action
          <select
            value={actionFilter}
            onChange={(e) => resetToFirstPage(setActionFilter)(e.target.value)}
            className="rounded border border-slate-300 px-2 py-1"
          >
            <option value="">Toutes</option>
            {Object.entries(ACTION_LABELS).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-600">
          Type d&apos;entité
          <select
            value={entityTypeFilter}
            onChange={(e) => resetToFirstPage(setEntityTypeFilter)(e.target.value)}
            className="rounded border border-slate-300 px-2 py-1"
          >
            <option value="">Tous</option>
            {Object.entries(ENTITY_TYPE_LABELS).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-600">
          Utilisateur
          <select
            value={actorFilter}
            onChange={(e) => resetToFirstPage(setActorFilter)(e.target.value)}
            className="rounded border border-slate-300 px-2 py-1"
          >
            <option value="">Tous</option>
            {members.map((m) => (
              <option key={m.user.id} value={m.user.id}>
                {m.user.full_name}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Date</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Utilisateur</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Action</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Entité</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Résumé</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.items.map((entry) => (
              <tr key={entry.id} data-testid="audit-log-row">
                <td className="px-3 py-2 whitespace-nowrap">{formatDateTime(entry.created_at)}</td>
                <td className="px-3 py-2">{entry.actor_email ?? <span className="text-slate-400">Compte supprimé</span>}</td>
                <td className="px-3 py-2">{ACTION_LABELS[entry.action] ?? entry.action}</td>
                <td className="px-3 py-2">{ENTITY_TYPE_LABELS[entry.entity_type] ?? entry.entity_type}</td>
                <td className="px-3 py-2">{entry.summary}</td>
              </tr>
            ))}
            {data.items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-center text-slate-400">
                  Aucun événement d&apos;audit.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {data.total_pages > 1 && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="rounded border border-slate-300 px-3 py-1 text-slate-700 disabled:opacity-40"
          >
            Précédent
          </button>
          <span className="text-slate-500">
            Page {data.page} / {data.total_pages}
          </span>
          <button
            type="button"
            disabled={page >= data.total_pages}
            onClick={() => setPage((p) => p + 1)}
            className="rounded border border-slate-300 px-3 py-1 text-slate-700 disabled:opacity-40"
          >
            Suivant
          </button>
        </div>
      )}
    </div>
  );
}
