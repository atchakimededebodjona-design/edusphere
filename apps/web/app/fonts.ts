import { Inter, Plus_Jakarta_Sans } from "next/font/google";

// Refonte, phase 0 (2026-11-23) — polices de l'identité EduLinkage. `next/font` les télécharge au build
// et les sert depuis le site : la CSP (`font-src 'self'`, next.config.js) n'autorise aucune police externe.
// Inter pour le texte, Plus Jakarta Sans pour les titres (voir tailwind.config.ts : font-sans, font-display).
export const bodyFont = Inter({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-body",
});

export const displayFont = Plus_Jakarta_Sans({
  subsets: ["latin", "latin-ext"],
  weight: ["600", "700", "800"],
  display: "swap",
  variable: "--font-display",
});
