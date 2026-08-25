"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { verify, type ReportCardVerify } from "@/lib/report-cards/client";

const STATUS_LABELS: Record<ReportCardVerify["status"], string> = {
  DRAFT: "Brouillon (non publié)",
  PUBLISHED: "Publié",
};

export default function VerifyPage() {
  const params = useParams<{ code: string }>();
  const [result, setResult] = useState<ReportCardVerify | "not_found" | null>(null);

  useEffect(() => {
    verify(params.code)
      .then(setResult)
      .catch(() => setResult("not_found"));
  }, [params.code]);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-slate-50 p-8">
      <h1 className="text-2xl font-bold text-slate-900">Vérification de bulletin</h1>

      {result === null && <p className="text-sm text-slate-500">Vérification en cours...</p>}

      {result === "not_found" && (
        <p className="max-w-sm text-center text-sm text-red-700">
          Code de vérification inconnu. Ce bulletin n&apos;a pas pu être authentifié.
        </p>
      )}

      {result && result !== "not_found" && (
        <div className="flex w-full max-w-sm flex-col gap-2 rounded border border-slate-200 bg-white p-6 text-sm">
          <p className="text-lg font-semibold text-slate-900">{result.school_name}</p>
          <dl className="flex flex-col gap-1">
            <div className="flex justify-between">
              <dt className="text-slate-500">Élève</dt>
              <dd>{result.student_full_name}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Classe</dt>
              <dd>{result.class_name}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Période</dt>
              <dd>{result.academic_term_name}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Moyenne générale</dt>
              <dd>{result.general_average ?? "—"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Rang</dt>
              <dd>{result.general_rank ?? "—"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-slate-500">Statut</dt>
              <dd>{STATUS_LABELS[result.status]}</dd>
            </div>
          </dl>
          <p className="mt-2 text-xs text-slate-400">Généré le {new Date(result.generated_at).toLocaleDateString("fr-FR")}</p>
        </div>
      )}
    </main>
  );
}
