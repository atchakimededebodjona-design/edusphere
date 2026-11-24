import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Connexion",
  description: "Connectez-vous à votre espace EduLinkage : administration, enseignants, parents, caisse.",
  alternates: { canonical: "https://edulinkage.com/login" },
};

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return children;
}
