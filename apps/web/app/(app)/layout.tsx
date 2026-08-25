import { AppShell } from "@/components/app-shell/AppShell";
import { AuthGate } from "@/app/(app)/AuthGate";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGate>
      <AppShell>{children}</AppShell>
    </AuthGate>
  );
}
