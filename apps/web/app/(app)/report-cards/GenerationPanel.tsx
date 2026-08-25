"use client";

import { useEffect, useMemo, useState } from "react";
import { academicTerms, schoolClasses, type AcademicTerm, type SchoolClass } from "@/lib/academics/client";
import { ApiError } from "@/lib/api/client";
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

  useEffect(() => {
    void schoolClasses.list(schoolId).then(setClasses);
    void templatesClient.list(schoolId).then(setTemplates);
  }, [schoolId]);

  useEffect(() => {
    setSelectedTermId("");
    setTerms(null);
    setRoster(null);
    setCards(null);
    if (!selectedClassId) return;
    const schoolClass = classes?.find((c) => c.id === selectedClassId);
    if (schoolClass) void academicTerms.list(schoolClass.academic_year_id).then(setTerms);
    void studentsClient.list(schoolId, { classId: selectedClassId }).then(setRoster);
  }, [selectedClassId, classes, schoolId]);

  useEffect(() => {
    setCards(null);
    if (!selectedClassId || !selectedTermId) return;
    void reportCards.list(selectedClassId, selectedTermId).then(setCards);
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

  if (classes === null || templates === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-3">
        <label className="flex flex-col gap-1 text-xs text-slate-600">
          Classe
          <select value={selectedClassId} onChange={(e) => setSelectedClassId(e.target.value)} className="rounded border border-slate-300 px-2 py-1 text-sm">
            <option value="">—</option>
            {classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-slate-600">
          Période
          <select
            value={selectedTermId}
            onChange={(e) => setSelectedTermId(e.target.value)}
            disabled={!terms}
            className="rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-100"
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
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Modèle
            <select value={selectedTemplateId} onChange={(e) => setSelectedTemplateId(e.target.value)} className="rounded border border-slate-300 px-2 py-1 text-sm">
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
            className="self-end rounded bg-slate-900 px-4 py-1.5 text-sm text-white disabled:opacity-50"
          >
            {generating ? "Génération..." : "Générer les bulletins"}
          </button>
        )}
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}

      {selectedClassId && selectedTermId && (
        <div className="overflow-x-auto rounded border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-slate-600">Élève</th>
                <th className="px-3 py-2 text-left font-medium text-slate-600">Statut</th>
                <th className="px-3 py-2 text-left font-medium text-slate-600">Moyenne</th>
                <th className="px-3 py-2 text-left font-medium text-slate-600">Rang</th>
                <th className="w-48" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {cards === null ? (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-center text-slate-400">
                    Chargement...
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-center text-slate-400">
                    Aucun bulletin généré pour cette sélection.
                  </td>
                </tr>
              ) : (
                rows.map(({ card, student }) => (
                  <tr key={card.id}>
                    <td className="px-3 py-2">{student ? `${student.last_name} ${student.first_name}` : card.student_id}</td>
                    <td className="px-3 py-2">{STATUS_LABELS[card.status]}</td>
                    <td className="px-3 py-2">{card.general_average ?? "—"}</td>
                    <td className="px-3 py-2">{card.general_rank ?? "—"}</td>
                    <td className="px-3 py-2 text-right">
                      <div className="flex justify-end gap-3">
                        <button
                          type="button"
                          onClick={() => reportCards.download(card, student?.matricule ?? card.id)}
                          className="text-xs text-slate-700 underline"
                        >
                          Télécharger
                        </button>
                        {canManage && card.status === "DRAFT" && (
                          <button
                            type="button"
                            onClick={() => handlePublish(card)}
                            disabled={busyId === card.id}
                            className="text-xs text-slate-700 underline"
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
