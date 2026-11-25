import type { Metadata } from "next";
import { ParentShell } from "@/components/parent-shell/ParentShell";
import { ParentGate } from "@/app/parent/ParentGate";

// 2026-11-24 — espace connecté : jamais indexé par les moteurs de recherche (voir aussi app/robots.ts).
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function ParentLayout({ children }: { children: React.ReactNode }) {
  return (
    <ParentGate>
      <ParentShell>{children}</ParentShell>
    </ParentGate>
  );
}
