"use client";

import { useEffect, useState } from "react";
import { DataTable, Pager, TableSkeleton } from "@/components/ui/DataTable";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { Card, EmptyState, PageHeader } from "@/components/ui/Surface";
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
  // Caisse scolaire, lot 3 (audit/service.py::ACTION_*)
  "payment.recorded": "Paiement enregistré",
  "cash.session.opened": "Caisse ouverte",
  "cash.movement.created": "Mouvement de caisse",
  "cash.count.created": "Comptage de caisse",
  "cash.session.closed": "Caisse clôturée",
  "cash.variance.justified": "Écart de caisse justifié",
};

const ENTITY_TYPE_LABELS: Record<string, string> = {
  Payment: "Paiement",
  StudentFee: "Frais élève",
  User: "Utilisateur",
  ReportCard: "Bulletin",
  StudentPromotion: "Promotion",
  StudentAssignment: "Affectation",
  CashSession: "Session de caisse",
  CashMovement: "Mouvement de caisse",
  CashCount: "Comptage de caisse",
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
    return <TableSkeleton />;
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Journal d'audit"
        description={`${data.total} événement(s)${data.total > 0 ? ` — page ${data.page} / ${data.total_pages}` : ""}`}
      />

      <Card>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
          Du
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => resetToFirstPage(setDateFrom)(e.target.value)}
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
          Au
          <input
            type="date"
            value={dateTo}
            onChange={(e) => resetToFirstPage(setDateTo)(e.target.value)}
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
          Action
          <select
            value={actionFilter}
            onChange={(e) => resetToFirstPage(setActionFilter)(e.target.value)}
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
          >
            <option value="">Toutes</option>
            {Object.entries(ACTION_LABELS).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
          Type d&apos;entité
          <select
            value={entityTypeFilter}
            onChange={(e) => resetToFirstPage(setEntityTypeFilter)(e.target.value)}
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
          >
            <option value="">Tous</option>
            {Object.entries(ENTITY_TYPE_LABELS).map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
          Utilisateur
          <select
            value={actorFilter}
            onChange={(e) => resetToFirstPage(setActorFilter)(e.target.value)}
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
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

      </Card>

      <DataTable
        caption="Journal d'audit"
        rows={data.items}
        rowKey={(entry) => entry.id}
        rowTestId={() => "audit-log-row"}
        empty={<EmptyState icon="shield" title="Aucun événement d'audit." />}
        columns={[
          { key: "date", header: "Date", cell: (entry) => <span className="whitespace-nowrap">{formatDateTime(entry.created_at)}</span> },
          {
            key: "actor",
            header: "Utilisateur",
            cell: (entry) => <span className="break-all">{entry.actor_email ?? <span className="text-slate-600">Compte supprimé</span>}</span>,
          },
          { key: "action", header: "Action", cell: (entry) => ACTION_LABELS[entry.action] ?? entry.action },
          { key: "entity", header: "Entité", cell: (entry) => ENTITY_TYPE_LABELS[entry.entity_type] ?? entry.entity_type },
          // Ordre d'origine sur ordinateur ; sur téléphone, le résumé ouvre la carte (DataTable, `title`).
          { key: "summary", header: "Résumé", mobile: "title", cell: (entry) => entry.summary },
        ]}
      />

      <Pager page={data.page} totalPages={data.total_pages} onPage={setPage} />
    </div>
  );
}
