import { ParentNav } from "@/components/parent-shell/ParentNav";
import { ParentTopBar } from "@/components/parent-shell/ParentTopBar";

// Pas de colonne latérale (contrairement à components/app-shell/AppShell.tsx) : nav horizontale
// empilée sous la barre du haut, meilleure adaptation mobile pour un espace consulté surtout
// depuis un téléphone (voir consigne Phase 28A, "mobile-first").
export function ParentShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <ParentTopBar />
      <ParentNav />
      <main className="flex-1 p-4 sm:p-8">{children}</main>
    </div>
  );
}
