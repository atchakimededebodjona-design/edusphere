import type { ReactNode } from "react";
import { BrandFull, BrandSymbol } from "@/components/branding/BrandLogo";

// Refonte, phase 4 C (2026-11-24) — cadre commun des pages hors de l'application : connexion, mot de
// passe oublié, définition du mot de passe, vérification d'un bulletin. Panneau de marque (navy,
// dégradé bleu → cyan purement CSS) pleine largeur sur téléphone, colonne dédiée sur grand écran ;
// formulaire à droite. Repris tel quel de la page de connexion.

/** Champ des pages d'accès (même rendu que la connexion), 44 px de haut. */
export const authInputClass =
  "min-h-11 rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-brand-text shadow-sm outline-none transition " +
  "placeholder:text-slate-500 focus:border-brand-blue focus:ring-2 focus:ring-brand-blue/20";

/** Bouton principal des pages d'accès (dégradé de la marque). */
export const authButtonClass =
  "min-h-11 rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition " +
  "hover:opacity-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-blue disabled:opacity-50";

/** Libellé de champ des pages d'accès. */
export const authLabelClass = "flex flex-col gap-1.5 text-sm font-medium text-brand-text";

export function AuthFrame({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="flex min-h-screen flex-col bg-brand-bg lg:flex-row">
      <div className="relative flex items-center justify-center overflow-hidden bg-brand-navy px-8 py-12 lg:w-[45%] lg:py-0">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -left-24 -top-24 h-72 w-72 rounded-full bg-gradient-to-br from-brand-blue to-brand-cyan opacity-20 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -bottom-24 -right-16 h-80 w-80 rounded-full bg-gradient-to-tr from-brand-cyan to-brand-blue opacity-20 blur-3xl"
        />
        <div className="relative z-10 flex max-w-sm flex-col items-center gap-6 py-8 text-center">
          <BrandFull className="h-auto w-full max-w-[260px]" priority />
          <p className="text-sm font-medium text-slate-300">Une école, des liens, un avenir.</p>
          <p className="hidden text-sm leading-relaxed text-slate-400 lg:block">
            La plateforme qui connecte administrateurs, enseignants et familles autour de la réussite scolaire.
          </p>
        </div>
      </div>

      <div className="flex flex-1 items-center justify-center px-6 py-12 sm:px-10">
        <div className="w-full max-w-sm">
          <BrandSymbol className="mb-6 h-10 w-10 lg:hidden" priority />
          <h1 className="text-2xl font-bold text-brand-text">{title}</h1>
          {subtitle && <p className="mt-1 text-sm text-slate-600">{subtitle}</p>}
          <div className="mt-8">{children}</div>
          {footer && <div className="mt-6">{footer}</div>}
        </div>
      </div>
    </main>
  );
}
