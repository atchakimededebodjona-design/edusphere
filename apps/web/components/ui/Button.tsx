import Link from "next/link";
import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Icon, type IconName } from "@/components/ui/Icon";

// Refonte, phase 0 (2026-11-23) — boutons communs. Action principale en bleu de marque (fini le noir) ;
// 44 px de haut sur téléphone (cible au doigt), 40 px à partir de sm. Focus toujours visible.
export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-primary-600 text-white hover:bg-primary-700 active:bg-primary-800",
  secondary: "border border-slate-300 bg-white text-slate-800 hover:bg-slate-50",
  ghost: "text-slate-700 hover:bg-slate-100",
  danger: "bg-red-700 text-white hover:bg-red-800",
};

const SIZES: Record<ButtonSize, string> = {
  sm: "min-h-9 px-3 text-sm",
  md: "min-h-11 px-4 text-sm sm:min-h-10",
};

export function buttonClass(variant: ButtonVariant = "primary", size: ButtonSize = "md", extra = ""): string {
  return [
    "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors",
    "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600",
    "disabled:cursor-not-allowed disabled:opacity-50",
    VARIANTS[variant],
    SIZES[size],
    extra,
  ]
    .filter(Boolean)
    .join(" ");
}

type CommonProps = { variant?: ButtonVariant; size?: ButtonSize; icon?: IconName; children: ReactNode };

export function Button({
  variant,
  size,
  icon,
  children,
  className = "",
  type = "button",
  ...rest
}: CommonProps & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button type={type} className={buttonClass(variant, size, className)} {...rest}>
      {icon && <Icon name={icon} className="h-4 w-4" />}
      {children}
    </button>
  );
}

export function ButtonLink({
  href,
  variant,
  size,
  icon,
  children,
  className = "",
}: CommonProps & { href: string; className?: string }) {
  return (
    <Link href={href} className={buttonClass(variant, size, className)}>
      {icon && <Icon name={icon} className="h-4 w-4" />}
      {children}
    </Link>
  );
}
