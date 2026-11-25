"use client";

import type { ReactNode } from "react";

// Rouvre le bandeau de mesure d'audience (components/consent/AnalyticsConsent.tsx). Sans configuration
// Umami, il n'y a rien à choisir : le bouton ne s'affiche pas.
const CONFIGURED = Boolean(process.env.NEXT_PUBLIC_UMAMI_SRC && process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID);

export function ConsentSettingsButton({ className, children }: { className?: string; children: ReactNode }) {
  if (!CONFIGURED) return null;
  return (
    <button type="button" className={className} onClick={() => window.dispatchEvent(new Event("edulinkage:open-consent"))}>
      {children}
    </button>
  );
}
