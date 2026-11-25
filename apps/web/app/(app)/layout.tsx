import type { Metadata } from "next";
import { AppShell } from "@/components/app-shell/AppShell";
import { AuthGate } from "@/app/(app)/AuthGate";

// 2026-11-24 — espace connecté : jamais indexé par les moteurs de recherche (voir aussi app/robots.ts).
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <AppShell>{children}</AppShell>
    </AuthGate>
  );
}
