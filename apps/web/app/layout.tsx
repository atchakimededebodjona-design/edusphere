import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "EduSphere",
  description: "Plateforme SaaS scolaire multi-tenant pour l'Afrique",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
