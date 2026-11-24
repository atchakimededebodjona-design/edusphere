import type { ReactNode } from "react";

// Refonte, phase 0 (2026-11-23) — jeu d'icônes EduLinkage : traits simples sur une grille de 24, dessinés
// ici (aucune dépendance, aucune requête externe, compatible avec la CSP). Remplace les emoji, dont le
// rendu change d'un téléphone à l'autre. Couleur héritée du texte (currentColor).
const PATHS = {
  grid: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.5" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.5" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.5" />
    </>
  ),
  home: (
    <>
      <path d="M3.5 10.5 12 3.5l8.5 7" />
      <path d="M5.5 9v11.5h5v-6h3v6h5V9" />
    </>
  ),
  school: (
    <>
      <path d="M3 20.5h18" />
      <path d="M5 20.5V9.5l7-4.5 7 4.5v11" />
      <path d="M10 20.5v-4.5h4v4.5" />
      <path d="M12 5V2.5h3" />
      <path d="M8.5 11.5h1.5M14 11.5h1.5" />
    </>
  ),
  building: (
    <>
      <path d="M4 20.5V5a1.5 1.5 0 0 1 1.5-1.5h8A1.5 1.5 0 0 1 15 5v15.5" />
      <path d="M15 9h3.5A1.5 1.5 0 0 1 20 10.5v10" />
      <path d="M2.5 20.5h19" />
      <path d="M7.5 7.5h4M7.5 11.5h4M7.5 15.5h4" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4.5 20.5c.9-3.7 3.9-6 7.5-6s6.6 2.3 7.5 6" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8.5" r="3.5" />
      <path d="M2.5 19.5c.7-3.3 3.2-5.5 6.5-5.5s5.8 2.2 6.5 5.5" />
      <path d="M15.5 5.3a3.3 3.3 0 0 1 0 6.4" />
      <path d="M17.5 14.3c2.1.6 3.5 2.4 4 5.2" />
    </>
  ),
  student: (
    <>
      <path d="M2.5 9 12 4.5 21.5 9 12 13.5Z" />
      <path d="M6.5 11v4.5c0 1.5 2.5 3 5.5 3s5.5-1.5 5.5-3V11" />
      <path d="M21.5 9v5" />
    </>
  ),
  board: (
    <>
      <path d="M2.5 4h19" />
      <path d="M4 4v10.5h16V4" />
      <path d="M12 14.5v3" />
      <path d="M8 21l4-3.5 4 3.5" />
    </>
  ),
  layers: (
    <>
      <path d="M12 3.5 2.5 8.5 12 13.5l9.5-5Z" />
      <path d="M2.5 12.5 12 17.5l9.5-5" />
      <path d="M2.5 16.5 12 21.5l9.5-5" />
    </>
  ),
  listChecks: (
    <>
      <path d="M3.5 6.5 5 8l2.5-2.5" />
      <path d="M3.5 12.5 5 14l2.5-2.5" />
      <path d="M3.5 18.5 5 20l2.5-2.5" />
      <path d="M11 7h9.5M11 13h9.5M11 19h9.5" />
    </>
  ),
  repeat: (
    <>
      <path d="M4 11.5a7.5 7.5 0 0 1 13-5l2.5 2.5" />
      <path d="M19.5 4v5h-5" />
      <path d="M20 12.5a7.5 7.5 0 0 1-13 5L4.5 15" />
      <path d="M4.5 20v-5h5" />
    </>
  ),
  checkSquare: (
    <>
      <rect x="3.5" y="3.5" width="17" height="17" rx="3" />
      <path d="M8 12.5l2.7 2.7L16.5 9.5" />
    </>
  ),
  chart: (
    <>
      <path d="M3.5 20.5h17" />
      <path d="M6.5 17v-5M11 17V7M15.5 17v-8M20 17V4.5" />
    </>
  ),
  fileText: (
    <>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6M9 17h6" />
    </>
  ),
  wallet: (
    <>
      <path d="M19.5 8V6.5A1.5 1.5 0 0 0 18 5H5.5A2.5 2.5 0 0 0 3 7.5" />
      <path d="M3 7.5v10A2.5 2.5 0 0 0 5.5 20h14a1.5 1.5 0 0 0 1.5-1.5v-9A1.5 1.5 0 0 0 19.5 8H5.5A2.5 2.5 0 0 1 3 7.5" />
      <circle cx="16.5" cy="14" r="1.25" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  cash: (
    <>
      <rect x="2.5" y="6" width="19" height="12" rx="2" />
      <circle cx="12" cy="12" r="2.5" />
      <path d="M6 9.5v5M18 9.5v5" />
    </>
  ),
  register: (
    <>
      <path d="M3.5 10.5h17v9a1.5 1.5 0 0 1-1.5 1.5H5a1.5 1.5 0 0 1-1.5-1.5Z" />
      <path d="M6.5 10.5V4.5h11v6" />
      <path d="M9 7.5h6M9 15.5h6" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3 4.5 6v5.5c0 4.6 3.2 8.2 7.5 9.5 4.3-1.3 7.5-4.9 7.5-9.5V6Z" />
      <path d="M9 12l2.2 2.2L15.5 10" />
    </>
  ),
  receipt: (
    <>
      <path d="M6 3h12v18l-2.5-1.7L13 21l-2.5-1.7L8 21l-2-1.4Z" />
      <path d="M9 8h6M9 12h6M9 16h3" />
    </>
  ),
  card: (
    <>
      <rect x="2.5" y="5" width="19" height="14" rx="2.5" />
      <path d="M2.5 10h19M6.5 15h3.5" />
    </>
  ),
  table: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 9.5h18M3 14.5h18M9 4v16" />
    </>
  ),
  percent: (
    <>
      <path d="M19 5 5 19" />
      <circle cx="7" cy="7" r="2.5" />
      <circle cx="17" cy="17" r="2.5" />
    </>
  ),
  link: (
    <>
      <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1.4 1.4" />
      <path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1.4-1.4" />
    </>
  ),
  bell: (
    <>
      <path d="M6 16.5V11a6 6 0 1 1 12 0v5.5l1.5 2h-15Z" />
      <path d="M10 21a2.3 2.3 0 0 0 4 0" />
    </>
  ),
  megaphone: (
    <>
      <path d="M3.5 10v4a1 1 0 0 0 1 1H7l6.5 4V5L7 9H4.5a1 1 0 0 0-1 1Z" />
      <path d="M17 9.5a3.5 3.5 0 0 1 0 5" />
      <path d="M19.5 7a7 7 0 0 1 0 10" />
    </>
  ),
  clipboard: (
    <>
      <rect x="9" y="3" width="6" height="3.5" rx="1" />
      <path d="M9 5H6.5A1.5 1.5 0 0 0 5 6.5v13A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5v-13A1.5 1.5 0 0 0 17.5 5H15" />
      <path d="M9 12h6M9 16h4" />
    </>
  ),
  settings: (
    <>
      <path d="M4 6.5h9M17 6.5h3M4 12h3M11 12h9M4 17.5h11M19 17.5h1" />
      <circle cx="15" cy="6.5" r="2" />
      <circle cx="9" cy="12" r="2" />
      <circle cx="17" cy="17.5" r="2" />
    </>
  ),
  more: (
    <>
      <circle cx="5.5" cy="12" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="18.5" cy="12" r="1.4" fill="currentColor" stroke="none" />
    </>
  ),
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  close: <path d="M6 6l12 12M18 6 6 18" />,
  chevronDown: <path d="M6 9l6 6 6-6" />,
  chevronRight: <path d="M9 6l6 6-6 6" />,
  logout: (
    <>
      <path d="M14.5 4H18a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3.5" />
      <path d="M10 8l-4 4 4 4" />
      <path d="M6 12h10" />
    </>
  ),
  // 2026-11-24 — bouton « Afficher le mot de passe » (components/ui/PasswordInput.tsx).
  eye: (
    <>
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="3" />
    </>
  ),
  eyeOff: (
    <>
      <path d="M9.9 5.8A9.7 9.7 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a17 17 0 0 1-2.7 3.5" />
      <path d="M6.3 7.4C3.9 9 2.5 12 2.5 12S6 18.5 12 18.5c1.8 0 3.3-.5 4.6-1.3" />
      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
      <path d="M3.5 3.5l17 17" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof PATHS;

/** Icône décorative par défaut (masquée aux lecteurs d'écran) ; `label` la rend lisible. */
export function Icon({ name, className = "h-5 w-5", label }: { name: IconName; className?: string; label?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden={label ? undefined : true}
      role={label ? "img" : undefined}
      aria-label={label}
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  );
}
