import type { Metadata, Viewport } from "next";
import "./globals.css";
import { bodyFont, displayFont } from "./fonts";
import { AnalyticsConsent } from "@/components/consent/AnalyticsConsent";
import { PwaSupport } from "@/components/pwa/PwaSupport";
import { AuthProvider } from "@/lib/auth/AuthProvider";

export const metadata: Metadata = {
  // Nécessaire pour résoudre en URL absolue les images Open Graph/Twitter déclarées par les pages
  // (ex. app/page.tsx) à partir de chemins relatifs — sans cela, Next.js les résout par défaut
  // vers "http://localhost:3000", même en production. N'affecte que la résolution d'assets ;
  // titre/description par défaut ci-dessous inchangés pour toutes les autres routes.
  metadataBase: new URL("https://edulinkage.com"),
  // 2026-11-24 — « Page — EduLinkage » pour toute page qui déclare son propre titre.
  title: { default: "EduLinkage", template: "%s — EduLinkage" },
  description:
    "EduLinkage, la gestion scolaire pour l'Afrique : élèves, présences, notes, bulletins, frais et caisse, pour l'administration, les enseignants et les parents.",
  applicationName: "EduLinkage",
  // Phase 32 — application installable : le manifeste vient de app/manifest.ts, l'icône iPhone de
  // app/apple-icon.png.
  appleWebApp: { capable: true, title: "EduLinkage", statusBarStyle: "default" },
};

export const viewport: Viewport = {
  themeColor: "#0B1224",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr" className={`${bodyFont.variable} ${displayFont.variable}`}>
      <body className="font-sans text-slate-900 antialiased">
        <AuthProvider>
          {children}
          <PwaSupport />
          <AnalyticsConsent />
        </AuthProvider>
      </body>
    </html>
  );
}
