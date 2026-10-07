import { TeacherGate } from "./TeacherGate";

export default function TeacherLayout({ children }: { children: React.ReactNode }) {
  return <TeacherGate>{children}</TeacherGate>;
}
