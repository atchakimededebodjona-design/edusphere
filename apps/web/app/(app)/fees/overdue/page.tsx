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
} from "@/lib/fees/client";

const PAGE_SIZE = 20;

const STATUS_LABELS: Record<OverdueContactChannel, string> = {
  IN_APP_SENT: "Notifié in-app",
  EMAIL_SENT: "Email envoyé",
  NO_CHANNEL: "Aucun canal",
};

const STATUS_STYLES: Record<OverdueContactChannel, string> = {
  IN_APP_SENT: "bg-emerald-50 text-emerald-700 border-emerald-200",
  EMAIL_SENT: "bg-amber-50 text-amber-700 border-amber-200",
  NO_CHANNEL: "bg-red-50 text-red-700 border-red-200",
};

function GuardianContact({ guardian }: { guardian: OverdueFeeGuardianContact }) {
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
                        <GuardianContact key={guardian.guardian_id} guardian={guardian} />
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
