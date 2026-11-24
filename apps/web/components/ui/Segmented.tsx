// Refonte, phase 2 (2026-11-23) — choix exclusif en boutons côte à côte (ex. Présent / Absent / Retard),
// pensé pour le pouce : 44 px de haut sur téléphone. Ce sont de vrais boutons radio (groupe nommé,
// flèches du clavier, lecteurs d'écran), simplement dessinés autrement.
export type SegmentTone = "neutral" | "success" | "warning" | "danger";

const CHECKED: Record<SegmentTone, string> = {
  neutral: "bg-primary-600 text-white",
  success: "bg-emerald-700 text-white",
  warning: "bg-amber-600 text-white",
  danger: "bg-red-700 text-white",
};

export function Segmented<T extends string>({
  label,
  name,
  value,
  options,
  onChange,
  disabled = false,
  className = "",
}: {
  /** Nom du groupe pour les lecteurs d'écran (ex. « Statut de KOFFI »). */
  label: string;
  /** Nom HTML du groupe de boutons radio : unique dans la page. */
  name: string;
  value: T;
  options: { value: T; label: string; tone?: SegmentTone }[];
  onChange: (value: T) => void;
  disabled?: boolean;
  className?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      aria-disabled={disabled || undefined}
      className={`inline-flex rounded-lg border border-slate-300 bg-white p-0.5 ${className}`}
    >
      {options.map((option) => {
        const checked = option.value === value;
        return (
          <label
            key={option.value}
            className={[
              "flex min-h-11 min-w-[4.75rem] flex-1 cursor-pointer select-none items-center justify-center rounded-md px-3 text-sm font-medium sm:min-h-9",
              "has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-1 has-[:focus-visible]:outline-primary-600",
              "has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60",
              checked ? CHECKED[option.tone ?? "neutral"] : "text-slate-700 hover:bg-slate-100",
            ].join(" ")}
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={checked}
              disabled={disabled}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            {option.label}
          </label>
        );
      })}
    </div>
  );
}
