import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Mot de passe oublié",
  description: "Recevez par email un lien pour définir un nouveau mot de passe EduLinkage.",
  robots: { index: false, follow: true },
};

export default function ForgotPasswordLayout({ children }: { children: React.ReactNode }) {
  return children;
}
