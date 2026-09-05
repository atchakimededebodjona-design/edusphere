"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth/useAuth";
import type { AcademicYear } from "@/lib/academics/client";
import {
  StepAssignments,
  StepClasses,
  StepLevels,
  StepSubjects,
  StepSummary,
  StepTerms,
  StepYear,
} from "@/app/(app)/setup/WizardSteps";

const STEPS = [
  { title: "Année scolaire", description: "Choisissez ou créez l'année scolaire à configurer." },
  { title: "Termes / périodes", description: "Découpez l'année en trimestres ou semestres." },
  { title: "Niveaux", description: "Définissez les niveaux éducatifs de l'école." },
  { title: "Matières", description: "Listez les matières enseignées." },
  { title: "Classes", description: "Créez les classes de l'année." },
  { title: "Affectations enseignants", description: "Attachez matières et enseignants à chaque classe." },
  { title: "Résumé et confirmation", description: "Vérifiez la configuration de l'école." },
] as const;

export default function SetupWizardPage() {
  const { currentSchoolId, permissions } = useAuth();
  const [step, setStep] = useState(0);
  const [selectedYear, setSelectedYear] = useState<AcademicYear | null>(null);

  const canManage = permissions.includes("academics.manage");

  if (!currentSchoolId) {
    return <p className="text-sm text-slate-500">Chargement...</p>;
  }

  if (!canManage) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-bold text-slate-900">Mise en place de l&apos;école</h1>
        <p role="alert" className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          Vous n&apos;avez pas la permission d&apos;accéder à cette page.
        </p>
      </div>
    );
  }

  const canLeaveStep0 = selectedYear !== null;
  const maxReachableStep = canLeaveStep0 ? STEPS.length - 1 : 0;

  function goTo(index: number) {
    if (index < 0 || index > maxReachableStep) return;
    setStep(index);
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Mise en place de l&apos;école</h1>
        <p className="text-sm text-slate-500">
          Un parcours guidé pour configurer l&apos;essentiel : année scolaire, termes, niveaux, matières,
          classes et affectations enseignants. Vous pouvez revenir en arrière à tout moment ; rien
          n&apos;est perdu, chaque étape enregistre directement sur le serveur.
        </p>
      </div>

      <ol className="flex flex-wrap gap-2" aria-label="Progression">
        {STEPS.map((s, index) => {
          const reachable = index <= maxReachableStep;
          const current = index === step;
          return (
            <li key={s.title}>
              <button
                type="button"
                onClick={() => goTo(index)}
                disabled={!reachable}
                aria-current={current ? "step" : undefined}
                className={`rounded-full px-3 py-1 text-xs font-medium ${
                  current
                    ? "bg-slate-900 text-white"
                    : reachable
                      ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                      : "cursor-not-allowed bg-slate-50 text-slate-300"
                }`}
              >
                {index + 1}. {s.title}
              </button>
            </li>
          );
        })}
      </ol>

      <div className="rounded border border-slate-200 p-4">
        <h2 className="text-lg font-semibold text-slate-900">{STEPS[step].title}</h2>
        <p className="mb-4 text-sm text-slate-500">{STEPS[step].description}</p>

        {step === 0 && (
          <StepYear
            schoolId={currentSchoolId}
            selectedYearId={selectedYear?.id ?? ""}
            onSelectYear={setSelectedYear}
          />
        )}
        {step === 1 && selectedYear && <StepTerms yearId={selectedYear.id} />}
        {step === 2 && <StepLevels schoolId={currentSchoolId} />}
        {step === 3 && <StepSubjects schoolId={currentSchoolId} />}
        {step === 4 && selectedYear && <StepClasses schoolId={currentSchoolId} yearId={selectedYear.id} />}
        {step === 5 && selectedYear && <StepAssignments schoolId={currentSchoolId} yearId={selectedYear.id} />}
        {step === 6 && selectedYear && (
          <StepSummary schoolId={currentSchoolId} year={selectedYear} onGoToStep={goTo} />
        )}
      </div>

      <div className="flex justify-between">
        <button
          type="button"
          onClick={() => goTo(step - 1)}
          disabled={step === 0}
          className="rounded border border-slate-300 px-4 py-2 text-sm text-slate-700 disabled:opacity-50"
        >
          Précédent
        </button>
        {step < STEPS.length - 1 && (
          <button
            type="button"
            onClick={() => goTo(step + 1)}
            disabled={step === 0 && !canLeaveStep0}
            className="rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            Continuer
          </button>
        )}
      </div>
    </div>
  );
}
