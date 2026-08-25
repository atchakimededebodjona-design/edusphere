import { Nav } from "@/components/app-shell/Nav";
import { TopBar } from "@/components/app-shell/TopBar";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-slate-50">
      <TopBar />
      <div className="flex flex-1">
        <Nav />
        <main className="flex-1 p-8">{children}</main>
      </div>
    </div>
  );
}
