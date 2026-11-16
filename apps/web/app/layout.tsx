import type { Metadata, Viewport } from "next";
import "./globals.css";
import { PwaSupport } from "@/components/pwa/PwaSupport";
import { AuthProvider } from "@/lib/auth/AuthProvider";

export const metadata: Metadata = {
  // Nécessaire pour résoudre en URL absolue les images Open Graph/Twitter déclarées par les pages
  // (ex. app/page.tsx) à partir de chemins relatifs — sans cela, Next.js les résout par défaut
  // vers "http://localhost:3000", même en production. N'affecte que la résolution d'assets ;
  // titre/description par défaut ci-dessous inchangés pour toutes les autres routes.
  metadataBase: new URL("https://edulinkage.com"),
  title: "EduLinkage",
  description: "Plateforme SaaS scolaire multi-tenant pour l'Afrique",
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
    <html lang="fr">
      <body>
        <AuthProvider>
          {children}
          <PwaSupport />
        </AuthProvider>
      </body>
    </html>
  );
}
