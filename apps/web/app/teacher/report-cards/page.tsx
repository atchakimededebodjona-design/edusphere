"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { describeTeacherError, teacherApi, type TeacherClass, type TeacherReportCard } from "@/lib/teacher/client";

// Bulletins PUBLIÉS des élèves de mes classes uniquement (filtre serveur). La génération et la
// publication restent administratives : rien n'est modifiable ici.
function TeacherReportCardsPageContent() {
  const searchParams = useSearchParams();
  const [classes, setClasses] = useState<TeacherClass[] | null>(null);
  const [classId, setClassId] = useState(searchParams.get("class_id") ?? "");
  const [cards, setCards] = useState<TeacherReportCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    teacherApi.classes().then((list) => {
      setClasses(list);
      if (!classId && list[0]) setClassId(list[0].id);
    }).catch((err) => setError(describeTeacherError(err)));
    // initialisation unique
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!classId) return;
    setCards(null);
    teacherApi.reportCards(classId).then(setCards).catch((err) => setError(describeTeacherError(err)));
  }, [classId]);

  async function download(card: TeacherReportCard) {
    try {
      const blob = await teacherApi.reportCardPdf(card.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `bulletin_${card.student_name.replace(/\s+/g, "_")}.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(describeTeacherError(err));
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Bulletins publiés</h1>
      {error && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</p>}
      {classes && classes.length > 0 && (
        <select aria-label="Classe" value={classId} onChange={(e) => setClassId(e.target.value)} className="block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500 sm:!w-72">
          {classes.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      )}
      {classes && classes.length === 0 && <p className="text-sm text-slate-600">Aucune classe ne vous est affectée.</p>}
      {cards === null && !error && classId && <p className="text-sm text-slate-600">Chargement des bulletins...</p>}
      {cards && cards.length === 0 && <p className="text-sm text-slate-600">Aucun bulletin publié pour cette classe.</p>}
      {cards && cards.length > 0 && (
        <ul className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 text-sm">
          {cards.map((c) => (
            <li key={c.id} className="flex items-center justify-between gap-3">
              <span>{c.student_name}</span>
              <button type="button" onClick={() => download(c)} className="font-medium text-primary-700 underline underline-offset-2 hover:text-primary-800">Télécharger le PDF</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function TeacherReportCardsPage() {
  return (
    <Suspense fallback={<p className="text-sm text-slate-600">Chargement...</p>}>
      <TeacherReportCardsPageContent />
    </Suspense>
  );
}
