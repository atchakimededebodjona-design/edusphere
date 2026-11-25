import type { Metadata } from "next";

// Page ouverte par le QR code d'un bulletin : propre à un élève, jamais indexée.
export const metadata: Metadata = {
  title: "Vérification de bulletin",
  robots: { index: false, follow: false },
};

export default function VerifyLayout({ children }: { children: React.ReactNode }) {
  return children;
}
