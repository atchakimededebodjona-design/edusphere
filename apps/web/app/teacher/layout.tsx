import type { Metadata } from "next";
import { TeacherGate } from "./TeacherGate";

// 2026-11-24 — espace connecté : jamais indexé par les moteurs de recherche (voir aussi app/robots.ts).
export const metadata: Metadata = { robots: { index: false, follow: false } };

export default function TeacherLayout({ children }: { children: React.ReactNode }) {
  return <TeacherGate>{children}</TeacherGate>;
}
