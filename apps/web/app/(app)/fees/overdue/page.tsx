"use client";

import { useEffect, useState } from "react";
import { DataTable, Pager, TableSkeleton, type Column } from "@/components/ui/DataTable";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { Badge, EmptyState, PageHeader, type Tone } from "@/components/ui/Surface";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { formatApiAmount } from "@/lib/fees/allocation";
import {
  overdueFees,
  type OverdueContactChannel,
  type OverdueFeeGuardianContact,
  type OverdueFeeItem,
  type OverdueFeesPage,
  type ReminderStage,
} from "@/lib/fees/client";
import { formatDateFR } from "@/lib/format/date";

const PAGE_SIZE = 20;

// Sprint 1.6 — un transport SMTP accepté n'est jamais une preuve de remise réelle : jamais
// "livré"/"reçu"/"envoyé" seul dans ces libellés (voir SPRINT 1.6 DISCOVERY REPORT §4/§11).
const STATUS_LABELS: Record<OverdueContactChannel, string> = {
  IN_APP_SENT: "Notifié in-app",
  EMAIL_ATTEMPTED: "Email en attente de confirmation",
  EMAIL_TRANSPORT_ACCEPTED: "Email transmis",
  EMAIL_TRANSPORT_FAILED: "Échec d'envoi",
  // PR #16 — mêmes libellés prudents que pour l'email : un SMS "transmis" n'est jamais une
  // preuve de remise au téléphone, seulement que le fournisseur l'a accepté pour traitement.
  SMS_ATTEMPTED: "SMS en attente de confirmation",
  SMS_TRANSPORT_ACCEPTED: "SMS transmis",
  SMS_TRANSPORT_FAILED: "Échec d'envoi SMS",
  NO_CHANNEL: "Aucun canal",
};

// Phase 3 (2026-11-24) — mêmes teintes qu'avant, en pastilles communes.
const STATUS_TONES: Record<OverdueContactChannel, Tone> = {
  IN_APP_SENT: "success",
  EMAIL_ATTEMPTED: "neutral",
  EMAIL_TRANSPORT_ACCEPTED: "warning",
  EMAIL_TRANSPORT_FAILED: "danger",
  SMS_ATTEMPTED: "neutral",
  SMS_TRANSPORT_ACCEPTED: "warning",
  SMS_TRANSPORT_FAILED: "danger",
  NO_CHANNEL: "danger",
};

// PR #15 — cadence de relance (voir fees/models.py::REMINDER_STAGES).
const STAGE_LABELS: Record<ReminderStage, string> = {
  J0: "Palier initial (J0)",
  J7: "Relance à J+7",
  J30: "Relance à J+30",
};

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("fr-FR");
}

// Prochaine relance CALCULÉE côté client depuis `due_date` (jamais renvoyée par l'API — voir
// cahier des charges PR #15 §11, "prochaine relance calculable à partir de due_date") : aucune
// donnée n'est stockée pour ça, uniquement les seuils fixes J+7/J+30 déjà connus du frontend.
function nextReminderDate(dueDate: string, stage: ReminderStage | null): string | null {
  if (stage === null) return null; // NO_CHANNEL : aucune relance possible, rien à prévoir.
  const next = new Date(dueDate);
  if (stage === "J0") next.setDate(next.getDate() + 7);
  else if (stage === "J7") next.setDate(next.getDate() + 30);
  else return null; // J30 : dernier palier déjà atteint, plus aucune relance prévue.
  return next.toISOString().slice(0, 10);
}

function GuardianContact({ guardian, dueDate }: { guardian: OverdueFeeGuardianContact; dueDate: string }) {
  const next = nextReminderDate(dueDate, guardian.reminder_stage);
  return (
    <div className="flex flex-col gap-1">
      <span className="break-words text-slate-800">
        <span className="font-medium">{guardian.full_name}</span>
        {guardian.email && <span className="text-slate-600"> — {guardian.email}</span>}
      </span>
      <div className="flex flex-wrap gap-1">
        {guardian.statuses.map((status) => (
          <Badge key={status} tone={STATUS_TONES[status]}>
            {STATUS_LABELS[status]}
          </Badge>
        ))}
      </div>
      {guardian.reminder_stage && (
        <span className="text-xs text-slate-600">
          {STAGE_LABELS[guardian.reminder_stage]}
          {guardian.last_reminder_at && ` — dernière relance le ${formatDate(guardian.last_reminder_at)}`}
          {next && ` — prochaine relance le ${new Date(next).toLocaleDateString("fr-FR")}`}
        </span>
      )}
    </div>
  );
}

const COLUMNS: Column<OverdueFeeItem>[] = [
  {
    key: "student",
    header: "Élève",
    mobile: "title",
    cell: (item) => (
      <div className="min-w-0">
        <p className="font-medium text-slate-900">
          {item.student_first_name} {item.student_last_name}
        </p>
        <p className="text-xs font-normal text-slate-600">{item.student_matricule}</p>
      </div>
    ),
  },
  { key: "fee", header: "Frais", cell: (item) => item.fee_schedule_name },
  { key: "due", header: "Échéance", cell: (item) => formatDateFR(item.due_date) },
  {
    key: "late",
    header: "Retard",
    align: "right",
    cell: (item) => <Badge tone={item.overdue_days >= 30 ? "danger" : "warning"}>{item.overdue_days} j</Badge>,
  },
  {
    key: "remaining",
    header: "Montant restant",
    align: "right",
    cell: (item) => <span className="font-semibold text-slate-900">{formatApiAmount(item.remaining_balance, item.currency)}</span>,
  },
  {
    key: "guardians",
    header: "Contact tuteurs",
    mobile: "full",
    cell: (item) =>
      item.guardians.length === 0 ? (
        <span className="text-slate-600">Aucun tuteur rattaché</span>
      ) : (
        <div className="flex flex-col gap-3">
          {item.guardians.map((guardian) => (
            <GuardianContact key={guardian.guardian_id} guardian={guardian} dueDate={item.due_date} />
          ))}
        </div>
      ),
  },
];

export default function OverdueFeesPageView() {
  const { currentSchoolId } = useAuth();
  const [page, setPage] = useState(1);
  const [data, setData] = useState<OverdueFeesPage | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  async function reload(schoolId: string, targetPage: number) {
    setLoadError(null);
    try {
      const result = await overdueFees.list(schoolId, { page: targetPage, pageSize: PAGE_SIZE });
      setData(result);
    } catch (err) {
      setLoadError(toErrorMessage(err));
    }
  }

  useEffect(() => {
    if (currentSchoolId) void reload(currentSchoolId, page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSchoolId, page]);

  if (loadError) {
    return <ErrorRetry message={loadError} onRetry={() => currentSchoolId && void reload(currentSchoolId, page)} />;
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Frais en retard"
        description={
          data === null
            ? "Frais dont l'échéance est passée, avec le suivi des relances envoyées aux tuteurs."
            : `${data.total} frais en retard${data.total > 0 ? ` — page ${data.page} / ${data.total_pages}` : ""}`
        }
      />

      {!currentSchoolId || data === null ? (
        <TableSkeleton />
      ) : (
        <>
          <DataTable
            caption="Frais en retard"
            columns={COLUMNS}
            rows={data.items}
            rowKey={(item) => item.student_fee_id}
            empty={<EmptyState icon="checkSquare" title="Aucun frais en retard." description="Toutes les échéances passées sont réglées." />}
          />
          <Pager page={data.page} totalPages={data.total_pages} onPage={setPage} />
        </>
      )}
    </div>
  );
}
