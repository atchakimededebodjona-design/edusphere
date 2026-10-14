import { Nav } from "@/components/app-shell/Nav";
import { TopBar } from "@/components/app-shell/TopBar";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <TopBar />
      {/* Caisse scolaire, lot 2 — sous `md`, menu en barre horizontale au-dessus du contenu (le
          poste de caisse doit rester utilisable sur tablette/mobile) ; à partir de `md`, rendu
          strictement identique à l'existant (menu latéral, p-8). */}
      <div className="flex flex-1 flex-col md:flex-row">
        <Nav />
        <main className="min-w-0 flex-1 p-4 md:p-8">{children}</main>
      </div>
    </div>
  );
}
