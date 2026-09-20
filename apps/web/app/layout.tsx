import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth/AuthProvider";

export const metadata: Metadata = {
  // Nécessaire pour résoudre en URL absolue les images Open Graph/Twitter déclarées par les pages
  // (ex. app/page.tsx) à partir de chemins relatifs — sans cela, Next.js les résout par défaut
  // vers "http://localhost:3000", même en production. N'affecte que la résolution d'assets ;
  // titre/description par défaut ci-dessous inchangés pour toutes les autres routes.
  metadataBase: new URL("https://edulinkage.com"),
  title: "EduLinkage",
  description: "Plateforme SaaS scolaire multi-tenant pour l'Afrique",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
