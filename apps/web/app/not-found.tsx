import type { Metadata } from "next";
import Link from "next/link";
import { AuthFrame, authButtonClass } from "@/components/auth/AuthFrame";

// 2026-11-24 — page 404 aux couleurs de la marque (même cadre que la connexion), au lieu de la page
// anglaise par défaut de Next.js.
export const metadata: Metadata = { title: "Page introuvable", robots: { index: false, follow: true } };

export default function NotFound() {
  return (
    <AuthFrame title="Page introuvable" subtitle="Cette adresse ne correspond à aucune page d'EduLinkage.">
      <div className="flex flex-col gap-4">
        <p className="text-sm text-slate-700">
          Le lien est peut-être incomplet, ou la page a été déplacée. Vous pouvez revenir à l&apos;accueil ou vous connecter
          à votre espace.
        </p>
        <Link href="/" className={`${authButtonClass} inline-flex items-center justify-center`}>
          Retour à l&apos;accueil
        </Link>
        <Link
          href="/login"
          className="inline-flex min-h-11 items-center justify-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-semibold text-brand-text hover:bg-slate-50"
        >
          Se connecter
        </Link>
      </div>
    </AuthFrame>
  );
}
