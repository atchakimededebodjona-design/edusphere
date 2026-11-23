import { useId, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";

// Refonte, phase 0 (2026-11-23) — champs de formulaire communs : toujours un libellé visible (jamais un
// simple texte indicatif), aide et erreur reliées au champ pour les lecteurs d'écran, 44 px de haut sur
// téléphone.
export const controlClass =
  "block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 " +
  "placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 " +
  "disabled:bg-slate-100 disabled:text-slate-500 aria-[invalid=true]:border-red-600";

type FieldFrameProps = { label: string; hint?: ReactNode; error?: string | null; children: (ids: FieldIds) => ReactNode };
type FieldIds = { id: string; describedBy: string | undefined; invalid: boolean };

export function FieldFrame({ label, hint, error, children }: FieldFrameProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium text-slate-800">
        {label}
      </label>
      {children({ id, describedBy, invalid: Boolean(error) })}
      {hint && (
        <p id={hintId} className="text-xs text-slate-600">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-xs font-medium text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}

export function TextField({
  label,
  hint,
  error,
  className = "",
  ...input
}: { label: string; hint?: ReactNode; error?: string | null } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <FieldFrame label={label} hint={hint} error={error}>
      {({ id, describedBy, invalid }) => (
        <input id={id} aria-describedby={describedBy} aria-invalid={invalid} className={`${controlClass} ${className}`} {...input} />
      )}
    </FieldFrame>
  );
}

export function SelectField({
  label,
  hint,
  error,
  className = "",
  children,
  ...select
}: { label: string; hint?: ReactNode; error?: string | null; children: ReactNode } & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <FieldFrame label={label} hint={hint} error={error}>
      {({ id, describedBy, invalid }) => (
        <select id={id} aria-describedby={describedBy} aria-invalid={invalid} className={`${controlClass} ${className}`} {...select}>
          {children}
        </select>
      )}
    </FieldFrame>
  );
}
