"use client";

import { useState } from "react";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { toErrorMessage, useAsyncData } from "@/lib/api/useAsyncData";
import { useAuth } from "@/lib/auth/useAuth";
import { formatApiAmount } from "@/lib/fees/allocation";
import { formatDateFR } from "@/lib/format/date";
import {
  PERIOD_MONTHS,
  periodLabel,
  platformSubscriptions,
  type GridPeriodPrices,
  type PeriodMonths,
  type PriceGrid,
} from "@/lib/subscriptions/client";

const STATUS_LABELS: Record<PriceGrid["status"], string> = {
  DRAFT: "Brouillon",
  ACTIVE: "Active",
  ARCHIVED: "Archivée",
};

type AmountKey = keyof Omit<GridPeriodPrices, "period_months">;

// Bornes fixées dans le code (grille validée le 9 novembre 2026, complète depuis le 15 novembre) ;
// seuls les montants se saisissent. Le palier est facultatif : vide pour les trois durées = devis
// au-delà de 1 000 élèves.
const AMOUNT_FIELDS: { key: AmountKey; label: string; optional?: boolean }[] = [
  { key: "base_amount", label: "Forfait de base (jusqu'à 100 élèves)" },
  { key: "supplement_tier_1", label: "Supplément 101 à 250 élèves" },
  { key: "supplement_tier_2", label: "Supplément 251 à 500 élèves" },
  { key: "supplement_tier_3", label: "Supplément 501 à 750 élèves" },
  { key: "supplement_tier_4", label: "Supplément 751 à 1 000 élèves" },
  {
    key: "supplement_step",
    label: "Au-delà de 1 000 élèves : supplément par tranche de 250 élèves (vide = devis)",
    optional: true,
  },
];

type EditorPeriod = { period_months: PeriodMonths } & Record<AmountKey, string>;
type Editor = { gridId: string | null; label: string; periods: EditorPeriod[] };

function integerString(value: string | null): string {
  // L'API renvoie "30000.00" ; la saisie se fait en FCFA entiers.
  if (value === null) return "";
  const match = /^(\d+)(?:\.0+)?$/.exec(value.trim());
  return match ? match[1] : value;
}

function toEditorPeriods(periods: GridPeriodPrices[] | null): EditorPeriod[] {
  return PERIOD_MONTHS.map((months) => {
    const p = periods?.find((period) => period.period_months === months);
    return {
      period_months: months,
      base_amount: integerString(p?.base_amount ?? null),
      supplement_tier_1: integerString(p?.supplement_tier_1 ?? null),
      supplement_tier_2: integerString(p?.supplement_tier_2 ?? null),
      supplement_tier_3: integerString(p?.supplement_tier_3 ?? null),
      supplement_tier_4: integerString(p?.supplement_tier_4 ?? null),
      supplement_step: integerString(p?.supplement_step ?? null),
    };
  });
}

/** Contrôle local, en français, avant l'envoi : l'API reste la seule vraie validation. */
function editorProblem(editor: Editor): string | null {
  if (!editor.label.trim()) return "Le libellé est obligatoire.";
  for (const field of AMOUNT_FIELDS.filter((f) => !f.optional)) {
    if (editor.periods.some((p) => p[field.key] === "")) {
      return `Montant manquant : « ${field.label} ». Saisissez 0 s'il n'y a pas de supplément.`;
    }
  }
  if (editor.periods.some((p) => p.base_amount !== "" && Number(p.base_amount) === 0)) {
    return "Le forfait de base doit être supérieur à 0.";
  }
  const steps = editor.periods.filter((p) => p.supplement_step !== "").length;
  if (steps !== 0 && steps !== editor.periods.length) {
    return "Le supplément au-delà de 1 000 élèves se renseigne pour les trois durées, ou pour aucune (devis).";
  }
  return null;
}

function amountCell(value: string | null, currency: string, optional: boolean | undefined): string {
  if (value === null) return optional ? "Devis" : "—";
  return formatApiAmount(value, currency);
}

// Phase 29 — grille tarifaire (PLATFORM_OWNER). Une seule grille active ; une grille activée n'est
// plus jamais modifiée (les factures émises référencent leur version et gardent leur prix).
// Contrôles réels côté API (`platform.subscriptions.*`).
export default function SubscriptionGridsPage() {
  const { permissions } = useAuth();
  const canManage = permissions.includes("platform.subscriptions.manage");
  const [reloadKey, setReloadKey] = useState(0);
  const [editor, setEditor] = useState<Editor | null>(null);
  const [confirmActivate, setConfirmActivate] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const { data, error, isLoading, retry } = useAsyncData(() => platformSubscriptions.grids(), [reloadKey]);
  const active = data?.find((grid) => grid.status === "ACTIVE") ?? null;

  function startNew() {
    setActionError(null);
    // Préremplie avec la grille active, pour ne modifier que ce qui change.
    setEditor({ gridId: null, label: "", periods: toEditorPeriods(active ? active.periods : null) });
  }

  function startEdit(grid: PriceGrid) {
    setActionError(null);
    setEditor({ gridId: grid.id, label: grid.label, periods: toEditorPeriods(grid.periods) });
  }

  async function run(action: () => Promise<unknown>, after?: () => void) {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      after?.();
      setReloadKey((k) => k + 1);
    } catch (err) {
      setActionError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function saveEditor() {
    if (!editor) return;
    const problem = editorProblem(editor);
    if (problem) {
      setActionError(problem);
      return;
    }
    const input = {
      label: editor.label.trim(),
      periods: editor.periods.map((p) => ({ ...p, supplement_step: p.supplement_step === "" ? null : p.supplement_step })),
    };
    return run(
      () => (editor.gridId ? platformSubscriptions.updateGrid(editor.gridId, input) : platformSubscriptions.createGrid(input)),
      () => setEditor(null),
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Grille tarifaire</h1>
        <p className="text-sm text-slate-600">
          Prix des abonnements : forfait de base + supplément selon l&apos;effectif d&apos;élèves actifs, pour 3, 6 et 12 mois
          (FCFA entiers). Au-delà de 1 000 élèves : supplément de la tranche 751 à 1 000, plus un supplément par tranche de
          250 élèves commencée ; sans ce supplément, la facture passe en devis.
        </p>
      </div>

      {canManage && !editor && (
        <button
          type="button"
          onClick={startNew}
          className="self-start rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          Nouvelle grille (brouillon)
        </button>
      )}

      {actionError && <p className="text-sm text-red-700">{actionError}</p>}

      {editor && (
        <section className="flex flex-col gap-3 rounded border border-slate-300 bg-white p-4">
          <label className="flex flex-col gap-1 text-sm">
            Libellé
            <input
              value={editor.label}
              onChange={(e) => setEditor({ ...editor, label: e.target.value })}
              className="rounded border border-slate-300 px-2 py-1"
              maxLength={120}
            />
          </label>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr>
                  <th className="px-2 py-1 text-left font-medium text-slate-600">Montant (FCFA)</th>
                  {editor.periods.map((p) => (
                    <th key={p.period_months} className="px-2 py-1 text-left font-medium text-slate-600">
                      {periodLabel(p.period_months)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {AMOUNT_FIELDS.map((field) => (
                  <tr key={field.key}>
                    <td className="px-2 py-1 text-slate-700">{field.label}</td>
                    {editor.periods.map((p, index) => (
                      <td key={p.period_months} className="px-2 py-1">
                        <input
                          inputMode="numeric"
                          value={p[field.key]}
                          onChange={(e) => {
                            const periods = editor.periods.map((current, i) =>
                              i === index ? { ...current, [field.key]: e.target.value.replace(/[^\d]/g, "") } : current,
                            );
                            setEditor({ ...editor, periods });
                          }}
                          className="w-32 rounded border border-slate-300 px-2 py-1"
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={saveEditor}
              className="rounded bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Enregistrer le brouillon
            </button>
            <button type="button" disabled={busy} onClick={() => setEditor(null)} className="rounded border border-slate-300 px-3 py-2 text-sm">
              Annuler
            </button>
          </div>
        </section>
      )}

      {error && <ErrorRetry message={error} onRetry={retry} />}
      {isLoading && !error && <p className="text-sm text-slate-400">Chargement...</p>}
      {data && data.length === 0 && <p className="text-sm text-slate-500">Aucune grille : les écoles ne peuvent pas encore s&apos;abonner.</p>}

      {data?.map((grid) => (
        <section key={grid.id} className="flex flex-col gap-2 rounded border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-semibold text-slate-900">{grid.label}</p>
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700">{STATUS_LABELS[grid.status]}</span>
            <span className="text-xs text-slate-500">
              Créée le {formatDateFR(grid.created_at)}
              {grid.activated_at && ` — activée le ${formatDateFR(grid.activated_at)}`}
              {grid.archived_at && ` — archivée le ${formatDateFR(grid.archived_at)}`}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr>
                  <th className="px-2 py-1 text-left font-medium text-slate-600">Montant</th>
                  {grid.periods.map((p) => (
                    <th key={p.period_months} className="px-2 py-1 text-left font-medium text-slate-600">
                      {periodLabel(p.period_months)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {AMOUNT_FIELDS.map((field) => (
                  <tr key={field.key}>
                    <td className="px-2 py-1 text-slate-700">{field.label}</td>
                    {grid.periods.map((p) => (
                      <td key={p.period_months} className="px-2 py-1 text-slate-900">
                        {amountCell(p[field.key], grid.currency, field.optional)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {grid.periods.some((p) => p.supplement_tier_4 === null) && (
            <p className="text-xs text-slate-500">
              Grille antérieure au 15/11/2026 : sa tranche « 501 à 750 » couvrait alors 501 à 1 000 élèves, et elle ne chiffre pas
              751 à 1 000 élèves.
            </p>
          )}
          {canManage && grid.status === "DRAFT" && (
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={busy} onClick={() => startEdit(grid)} className="rounded border border-slate-300 px-3 py-1 text-sm">
                Modifier
              </button>
              {confirmActivate === grid.id ? (
                <>
                  <span className="text-sm text-amber-800">
                    Activer cette grille ? {active ? "La grille active actuelle sera archivée. " : ""}Les nouvelles factures
                    utiliseront ces prix ; une grille activée n&apos;est plus modifiable.
                  </span>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => run(() => platformSubscriptions.activateGrid(grid.id), () => setConfirmActivate(null))}
                    className="rounded bg-slate-900 px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
                  >
                    Confirmer l&apos;activation
                  </button>
                  <button type="button" onClick={() => setConfirmActivate(null)} className="rounded border border-slate-300 px-3 py-1 text-sm">
                    Annuler
                  </button>
                </>
              ) : (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setConfirmActivate(grid.id)}
                  className="rounded bg-slate-900 px-3 py-1 text-sm font-medium text-white disabled:opacity-50"
                >
                  Activer
                </button>
              )}
            </div>
          )}
        </section>
      ))}
    </div>
  );
}
