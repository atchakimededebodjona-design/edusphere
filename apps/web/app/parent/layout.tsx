import { ParentShell } from "@/components/parent-shell/ParentShell";
import { ParentGate } from "@/app/parent/ParentGate";

export default function ParentLayout({ children }: { children: React.ReactNode }) {
  return (
    <ParentGate>
      <ParentShell>{children}</ParentShell>
    </ParentGate>
  );
}
