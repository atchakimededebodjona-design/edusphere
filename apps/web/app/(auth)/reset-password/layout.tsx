import type { Metadata } from "next";

// Page ouverte par un lien personnel reçu par email : jamais indexée.
export const metadata: Metadata = {
  title: "Définir votre mot de passe",
  robots: { index: false, follow: false },
};

export default function ResetPasswordLayout({ children }: { children: React.ReactNode }) {
  return children;
}
