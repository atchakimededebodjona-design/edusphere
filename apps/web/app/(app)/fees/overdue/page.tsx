"use client";

import { useEffect, useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import {
  overdueFees,
  type OverdueContactChannel,
  type OverdueFeeGuardianContact,
  type OverdueFeesPage,
  type ReminderStage,
} from "@/lib/fees/client";

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

const STATUS_STYLES: Record<OverdueContactChannel, string> = {
  IN_APP_SENT: "bg-emerald-50 text-emerald-700 border-emerald-200",
  EMAIL_ATTEMPTED: "bg-slate-100 text-slate-700 border-slate-200",
  EMAIL_TRANSPORT_ACCEPTED: "bg-amber-50 text-amber-700 border-amber-200",
  EMAIL_TRANSPORT_FAILED: "bg-red-50 text-red-700 border-red-200",
  SMS_ATTEMPTED: "bg-slate-100 text-slate-700 border-slate-200",
  SMS_TRANSPORT_ACCEPTED: "bg-amber-50 text-amber-700 border-amber-200",
  SMS_TRANSPORT_FAILED: "bg-red-50 text-red-700 border-red-200",
  NO_CHANNEL: "bg-red-50 text-red-700 border-red-200",
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
      <span className="text-slate-700">
        {guardian.full_name}
        {guardian.email && <span className="text-slate-400"> — {guardian.email}</span>}
      </span>
      <div className="flex flex-wrap gap-1">
        {guardian.statuses.map((status) => (
          <span
            key={status}
            className={`rounded border px-1.5 py-0.5 text-[11px] font-medium ${STATUS_STYLES[status]}`}
          >
            {STATUS_LABELS[status]}
          </span>
        ))}
      </div>
      {guardian.reminder_stage && (
        <span className="text-[11px] text-slate-500">
          {STAGE_LABELS[guardian.reminder_stage]}
          {guardian.last_reminder_at && ` — dernière relance le ${formatDate(guardian.last_reminder_at)}`}
          {next && ` — prochaine relance le ${new Date(next).toLocaleDateString("fr-FR")}`}
        </span>
      )}
    </div>
  );
}

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

  if (!currentSchoolId || data === null) {
    return <p className="text-sm text-slate-500">Chargement...</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Frais en retard</h1>
        <p className="text-sm text-slate-500">
          {data.total} frais en retard{data.total > 0 ? ` — page ${data.page} / ${data.total_pages}` : ""}
        </p>
      </div>

      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Élève</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Frais</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Échéance</th>
              <th className="px-3 py-2 text-right font-medium text-slate-600">Retard</th>
              <th className="px-3 py-2 text-right font-medium text-slate-600">Montant restant</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600">Contact tuteurs</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.items.map((item) => (
              <tr key={item.student_fee_id}>
                <td className="px-3 py-2">
                  {item.student_first_name} {item.student_last_name}
                  <div className="text-xs text-slate-400">{item.student_matricule}</div>
                </td>
                <td className="px-3 py-2">{item.fee_schedule_name}</td>
                <td className="px-3 py-2">{item.due_date}</td>
                <td className="px-3 py-2 text-right">{item.overdue_days} j</td>
                <td className="px-3 py-2 text-right">
                  {item.remaining_balance} {item.currency}
                </td>
                <td className="px-3 py-2">
                  {item.guardians.length === 0 ? (
                    <span className="text-slate-400">Aucun tuteur rattaché</span>
                  ) : (
                    <div className="flex flex-col gap-2">
                      {item.guardians.map((guardian) => (
                        <GuardianContact key={guardian.guardian_id} guardian={guardian} dueDate={item.due_date} />
                      ))}
                    </div>
                  )}
                </td>
              </tr>
            ))}
            {data.items.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-4 text-center text-slate-400">
                  Aucun frais en retard.
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
