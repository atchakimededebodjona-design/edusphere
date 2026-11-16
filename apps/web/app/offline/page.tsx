import type { Metadata } from "next";
import Link from "next/link";
import { BrandSymbol } from "@/components/branding/BrandLogo";

export const metadata: Metadata = { title: "Hors connexion — EduLinkage" };

// Phase 32, lot 1 — servie par le service worker (sw/service-worker.js) quand une page n'a encore
// jamais été ouverte avec internet sur cet appareil (fiche d'un élève, d'un enfant…). Page statique,
// sans donnée : toujours gardée à l'installation.
export default function OfflinePage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-slate-50 p-6 text-center">
      <BrandSymbol className="h-14 w-14" priority />
      <h1 className="text-xl font-bold text-slate-900">Page indisponible hors connexion</h1>
      <p className="max-w-md text-sm text-slate-600">
        Cette page n&apos;a pas encore été ouverte avec internet sur cet appareil. Elle sera consultable hors connexion
        après l&apos;avoir ouverte une fois avec internet.
      </p>
      <Link href="/dashboard" className="rounded bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700">
        Retour à mon espace
      </Link>
    </main>
  );
}
