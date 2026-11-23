import type { ReactNode } from "react";

// Refonte, phase 2 (2026-11-23) — barre d'action collée en bas de l'écran pendant le défilement
// (« Enregistrer l'appel », « Encaisser »...). Elle se pose au-dessus de la barre de navigation du bas
// (--bottom-nav-height, components/shell/MobileTabBar.tsx) et des bandeaux hors connexion ou de mise à
// jour (--bottom-banners-height, components/pwa/PwaSupport.tsx) : rien ne la recouvre sur téléphone.
export function ActionBar({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`sticky z-30 border-t border-slate-200 bg-white py-3 shadow-[0_-4px_12px_-8px_rgba(15,23,42,0.25)] ${className}`}
      style={{ bottom: "calc(var(--bottom-nav-height, 0px) + var(--bottom-banners-height, 0px))" }}
    >
      {children}
    </div>
  );
}
