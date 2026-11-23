import type { ReactNode } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";

// Refonte, phase 0 (2026-11-23) — briques d'affichage communes : en-tête de page, carte, indicateur,
// badge de statut, alerte, état vide et squelette de chargement. Contraste AA : le texte secondaire est
// en slate-600, jamais en gris clair.

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-bold text-slate-900">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm text-slate-600">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`rounded-xl border border-slate-200 bg-white p-4 sm:p-5 ${className}`}>{children}</div>;
}

export function StatCard({
  label,
  value,
  hint,
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  icon?: IconName;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-4">
      {icon && (
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-700">
          <Icon name={icon} />
        </span>
      )}
      <div className="min-w-0">
        <p className="text-sm text-slate-600">{label}</p>
        <p className="font-display text-2xl font-bold tabular-nums text-slate-900">{value}</p>
        {hint && <p className="text-xs text-slate-600">{hint}</p>}
      </div>
    </div>
  );
}

export type Tone = "neutral" | "info" | "success" | "warning" | "danger";

const BADGE_TONES: Record<Tone, string> = {
  neutral: "bg-slate-100 text-slate-700",
  info: "bg-primary-50 text-primary-800",
  success: "bg-emerald-50 text-emerald-800",
  warning: "bg-amber-50 text-amber-900",
  danger: "bg-red-50 text-red-800",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${BADGE_TONES[tone]}`}>
      {children}
    </span>
  );
}

const ALERT_TONES: Record<Exclude<Tone, "neutral">, { box: string; icon: IconName }> = {
  info: { box: "border-primary-200 bg-primary-50 text-primary-900", icon: "bell" },
  success: { box: "border-emerald-200 bg-emerald-50 text-emerald-900", icon: "checkSquare" },
  warning: { box: "border-amber-300 bg-amber-50 text-amber-900", icon: "clock" },
  danger: { box: "border-red-200 bg-red-50 text-red-900", icon: "shield" },
};

export function Alert({
  tone = "info",
  title,
  children,
}: {
  tone?: Exclude<Tone, "neutral">;
  title?: string;
  children?: ReactNode;
}) {
  const style = ALERT_TONES[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={`flex gap-3 rounded-lg border px-4 py-3 text-sm ${style.box}`}>
      <Icon name={style.icon} className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="min-w-0">
        {title && <p className="font-semibold">{title}</p>}
        {children}
      </div>
    </div>
  );
}

export function EmptyState({
  icon = "layers",
  title,
  description,
  action,
}: {
  icon?: IconName;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
      <span className="flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 text-slate-600">
        <Icon name={icon} />
      </span>
      <p className="font-semibold text-slate-900">{title}</p>
      {description && <p className="max-w-md text-sm text-slate-600">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

/** Bloc gris animé pendant un chargement (animation coupée si l'appareil demande moins de mouvement). */
export function Skeleton({ className = "h-4 w-full" }: { className?: string }) {
  return <div aria-hidden="true" className={`animate-pulse rounded bg-slate-200 motion-reduce:animate-none ${className}`} />;
}
