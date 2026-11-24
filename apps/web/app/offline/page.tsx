import type { Metadata } from "next";
import Link from "next/link";
import { BrandSymbol } from "@/components/branding/BrandLogo";

export const metadata: Metadata = { title: "Hors connexion — EduLinkage" };

// Phase 32, lot 1 — servie par le service worker (sw/service-worker.js) quand une page n'a encore
// jamais été ouverte avec internet sur cet appareil (fiche d'un élève, d'un enfant…). Page statique,
// sans donnée : toujours gardée à l'installation.
export default function OfflinePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-brand-bg p-6 text-center">
      <BrandSymbol className="h-14 w-14" priority />
      <h1 className="text-xl font-bold text-brand-text">Page indisponible hors connexion</h1>
      <p className="max-w-md text-sm text-slate-600">
        Cette page n&apos;a pas encore été ouverte avec internet sur cet appareil. Elle sera consultable hors connexion
        après l&apos;avoir ouverte une fois avec internet.
      </p>
      <Link
        href="/dashboard"
        className="inline-flex min-h-11 items-center rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-5 text-sm font-semibold text-white shadow-sm hover:opacity-95 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-blue"
      >
        Retour à mon espace
      </Link>
    </main>
  );
}
