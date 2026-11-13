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
  type PriceGrid,
} from "@/lib/subscriptions/client";

const STATUS_LABELS: Record<PriceGrid["status"], string> = {
  DRAFT: "Brouillon",
  ACTIVE: "Active",
  ARCHIVED: "Archivée",
};

const AMOUNT_FIELDS: { key: keyof Omit<GridPeriodPrices, "period_months">; label: string }[] = [
  { key: "base_amount", label: "Forfait de base (jusqu'à 100 élèves)" },
  { key: "supplement_tier_1", label: "Supplément tranche 1 (101 à 250)" },
  { key: "supplement_tier_2", label: "Supplément tranche 2 (251 à 500)" },
  { key: "supplement_tier_3", label: "Supplément tranche 3 (501 à 1 000)" },
];

function emptyPeriods(): GridPeriodPrices[] {
  return PERIOD_MONTHS.map((months) => ({
    period_months: months,
    base_amount: "",
    supplement_tier_1: "",
    supplement_tier_2: "",
    supplement_tier_3: "",
  }));
}

function integerString(value: string): string {
  // L'API renvoie "30000.00" ; la saisie se fait en FCFA entiers.
  const match = /^(\d+)(?:\.0+)?$/.exec(value.trim());
  return match ? match[1] : value;
}

type Editor = { gridId: string | null; label: string; periods: GridPeriodPrices[] };

// Phase 29, lot A — grille tarifaire (PLATFORM_OWNER). Les bornes des tranches sont fixées (décision
// du 9 novembre) ; seuls les montants se saisissent. Une seule grille active ; une grille activée
// n'est plus jamais modifiée (les factures émises référencent leur version). Au-delà de 1 000
// élèves : devis, hors grille. Contrôles réels côté API (`platform.subscriptions.*`).
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
    setEditor({
      gridId: null,
      label: "",
      // Préremplie avec la grille active, pour ne modifier que ce qui change.
      periods: active
        ? active.periods.map((p) => ({
            period_months: p.period_months,
            base_amount: integerString(p.base_amount),
            supplement_tier_1: integerString(p.supplement_tier_1),
            supplement_tier_2: integerString(p.supplement_tier_2),
            supplement_tier_3: integerString(p.supplement_tier_3),
          }))
        : emptyPeriods(),
    });
  }

  function startEdit(grid: PriceGrid) {
    setActionError(null);
    setEditor({
      gridId: grid.id,
      label: grid.label,
      periods: grid.periods.map((p) => ({
        period_months: p.period_months,
        base_amount: integerString(p.base_amount),
        supplement_tier_1: integerString(p.supplement_tier_1),
        supplement_tier_2: integerString(p.supplement_tier_2),
        supplement_tier_3: integerString(p.supplement_tier_3),
      })),
    });
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
    const input = { label: editor.label, periods: editor.periods };
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
          Prix des abonnements : forfait de base + supplément selon la tranche d&apos;effectif, pour 3, 6 et 12 mois (FCFA
          entiers). Au-delà de 1 000 élèves : devis.
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
                        {formatApiAmount(p[field.key], grid.currency)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
