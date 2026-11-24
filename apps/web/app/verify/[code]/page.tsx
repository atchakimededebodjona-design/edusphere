"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { AuthFrame } from "@/components/auth/AuthFrame";
import { verify, type ReportCardVerify } from "@/lib/report-cards/client";

const STATUS_LABELS: Record<ReportCardVerify["status"], string> = {
  DRAFT: "Brouillon (non publié)",
  PUBLISHED: "Publié",
};

// Page publique ouverte par le QR code d'un bulletin. Phase 4 C (2026-11-24) : même cadre que la
// connexion ; résultat dans une carte, statut en pastille. Même appel à l'API qu'avant.
export default function VerifyPage() {
  const params = useParams<{ code: string }>();
  const [result, setResult] = useState<ReportCardVerify | "not_found" | null>(null);

  useEffect(() => {
    verify(params.code)
      .then(setResult)
      .catch(() => setResult("not_found"));
  }, [params.code]);

  const rows: [string, string][] =
    result && result !== "not_found"
      ? [
          ["Élève", result.student_full_name],
          ["Classe", result.class_name],
          ["Période", result.academic_term_name],
          ["Moyenne générale", result.general_average === null ? "—" : String(result.general_average)],
          ["Rang", result.general_rank === null ? "—" : String(result.general_rank)],
        ]
      : [];

  return (
    <AuthFrame title="Vérification de bulletin" subtitle="Authenticité d'un bulletin émis par une école EduLinkage.">
      {result === null && (
        <p role="status" className="text-sm text-slate-600">
          Vérification en cours...
        </p>
      )}

      {result === "not_found" && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          Code de vérification inconnu. Ce bulletin n&apos;a pas pu être authentifié.
        </p>
      )}

      {result && result !== "not_found" && (
        <div className="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-5 text-sm shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="text-lg font-bold text-brand-text">{result.school_name}</p>
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                result.status === "PUBLISHED" ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-900"
              }`}
            >
              {STATUS_LABELS[result.status]}
            </span>
          </div>
          <dl className="divide-y divide-slate-100">
            {rows.map(([label, value]) => (
              <div key={label} className="flex justify-between gap-4 py-2">
                <dt className="text-slate-600">{label}</dt>
                <dd className="text-right font-medium text-slate-900">{value}</dd>
              </div>
            ))}
          </dl>
          <p className="text-xs text-slate-600">Généré le {new Date(result.generated_at).toLocaleDateString("fr-FR")}</p>
        </div>
      )}
    </AuthFrame>
  );
}
