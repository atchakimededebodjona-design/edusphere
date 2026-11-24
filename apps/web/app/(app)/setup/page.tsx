"use client";

import { TableSkeleton } from "@/components/ui/DataTable";
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
    return <TableSkeleton rows={3} />;
  }

  if (!canManage) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-bold text-slate-900">Mise en place de l&apos;école</h1>
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
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
        <p className="text-sm text-slate-600">
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
                className={`inline-flex min-h-9 items-center rounded-full px-3 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 ${
                  current
                    ? "bg-primary-600 text-white"
                    : reachable
                      ? "bg-primary-50 text-primary-800 hover:bg-primary-100"
                      : "cursor-not-allowed bg-slate-100 text-slate-500"
                }`}
              >
                {index + 1}. {s.title}
              </button>
            </li>
          );
        })}
      </ol>

      <div className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
        <h2 className="text-lg font-semibold text-slate-900">{STEPS[step].title}</h2>
        <p className="mb-4 text-sm text-slate-600">{STEPS[step].description}</p>

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
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10"
        >
          Précédent
        </button>
        {step < STEPS.length - 1 && (
          <button
            type="button"
            onClick={() => goTo(step + 1)}
            disabled={step === 0 && !canLeaveStep0}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10"
          >
            Continuer
          </button>
        )}
      </div>
    </div>
  );
}
