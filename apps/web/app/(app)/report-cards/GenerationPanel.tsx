"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { academicTerms, schoolClasses, type AcademicTerm, type SchoolClass } from "@/lib/academics/client";
import { ApiError } from "@/lib/api/client";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { Badge } from "@/components/ui/Surface";
import { reportCards, templates as templatesClient, type ReportCard, type ReportCardTemplate } from "@/lib/report-cards/client";
import { students as studentsClient, type Student } from "@/lib/students/client";

const STATUS_LABELS: Record<ReportCard["status"], string> = {
  DRAFT: "Brouillon",
  PUBLISHED: "Publié",
};

export function GenerationPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [templates, setTemplates] = useState<ReportCardTemplate[] | null>(null);
  const [selectedClassId, setSelectedClassId] = useState("");
  const [terms, setTerms] = useState<AcademicTerm[] | null>(null);
  const [selectedTermId, setSelectedTermId] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [roster, setRoster] = useState<Student[] | null>(null);
  const [cards, setCards] = useState<ReportCard[] | null>(null);
  const [generating, setGenerating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const loadClassesAndTemplates = useCallback(() => {
    setLoadError(null);
    Promise.all([schoolClasses.list(schoolId), templatesClient.list(schoolId)])
      .then(([c, t]) => {
        setClasses(c);
        setTemplates(t);
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [schoolId]);

  useEffect(() => {
    loadClassesAndTemplates();
  }, [loadClassesAndTemplates]);

  useEffect(() => {
    setSelectedTermId("");
    setTerms(null);
    setRoster(null);
    setCards(null);
    setError(null);
    if (!selectedClassId) return;
    const schoolClass = classes?.find((c) => c.id === selectedClassId);
    if (schoolClass) {
      void academicTerms
        .list(schoolClass.academic_year_id)
        .then(setTerms)
        .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
    }
    void studentsClient
      .list(schoolId, { classId: selectedClassId })
      .then(setRoster)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [selectedClassId, classes, schoolId]);

  useEffect(() => {
    setCards(null);
    setError(null);
    if (!selectedClassId || !selectedTermId) return;
    void reportCards
      .list(selectedClassId, selectedTermId)
      .then(setCards)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [selectedClassId, selectedTermId]);

  const rows = useMemo(() => {
    if (!cards || !roster) return [];
    return cards.map((card) => ({ card, student: roster.find((s) => s.id === card.student_id) }));
  }, [cards, roster]);

  async function handleGenerate() {
    if (!selectedClassId || !selectedTermId || !selectedTemplateId) return;
    setGenerating(true);
    setError(null);
    try {
      const generated = await reportCards.generate({
        class_id: selectedClassId,
        academic_term_id: selectedTermId,
        template_id: selectedTemplateId,
      });
      setCards(generated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setGenerating(false);
    }
  }

  async function handlePublish(card: ReportCard) {
    setBusyId(card.id);
    setError(null);
    try {
      const updated = await reportCards.publish(card.id);
      setCards((prev) => (prev ?? []).map((c) => (c.id === updated.id ? updated : c)));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusyId(null);
    }
  }

  if (loadError) return <ErrorRetry message={loadError} onRetry={loadClassesAndTemplates} />;
  if (classes === null || templates === null) return <p className="text-sm text-slate-600">Chargement...</p>;

  return (
    <div className="flex flex-col gap-4">
      <div className="grid items-end gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:grid-cols-2 sm:p-5 lg:grid-cols-4">
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
          Classe
          <select value={selectedClassId} onChange={(e) => setSelectedClassId(e.target.value)} className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500">
            <option value="">—</option>
            {classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
          Période
          <select
            value={selectedTermId}
            onChange={(e) => setSelectedTermId(e.target.value)}
            disabled={!terms}
            className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
          >
            <option value="">—</option>
            {terms?.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        {canManage && (
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
            Modèle
            <select value={selectedTemplateId} onChange={(e) => setSelectedTemplateId(e.target.value)} className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500">
              <option value="">—</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {canManage && selectedClassId && selectedTermId && selectedTemplateId && (
          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10 sm:justify-self-start"
          >
            {generating ? "Génération..." : "Générer les bulletins"}
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      )}

      {selectedClassId && selectedTermId && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Élève</th>
                <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Statut</th>
                <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Moyenne</th>
                <th className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">Rang</th>
                <th className="w-48" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {cards === null ? (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-center text-slate-600">
                    Chargement...
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-center text-slate-600">
                    Aucun bulletin généré pour cette sélection.
                  </td>
                </tr>
              ) : (
                rows.map(({ card, student }) => (
                  <tr key={card.id}>
                    <td className="px-3 py-2">{student ? `${student.last_name} ${student.first_name}` : card.student_id}</td>
                    <td className="px-3 py-2">
                      <Badge tone={card.status === "PUBLISHED" ? "success" : "neutral"}>{STATUS_LABELS[card.status]}</Badge>
                    </td>
                    <td className="px-3 py-2">{card.general_average ?? "—"}</td>
                    <td className="px-3 py-2">{card.general_rank ?? "—"}</td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-3">
                        <button
                          type="button"
                          onClick={() => reportCards.download(card, student?.matricule ?? card.id)}
                          className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-primary-700 hover:bg-primary-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          Télécharger
                        </button>
                        {canManage && card.status === "DRAFT" && (
                          <button
                            type="button"
                            onClick={() => handlePublish(card)}
                            disabled={busyId === card.id}
                            className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-primary-700 hover:bg-primary-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            Publier
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
