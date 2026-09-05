"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth/useAuth";
import { AttendanceSessionPanel } from "@/app/(app)/attendance/AttendanceSessionPanel";
import { AttendanceStatsPanel } from "@/app/(app)/attendance/AttendanceStatsPanel";

const TABS = ["Appel", "Statistiques"] as const;
type Tab = (typeof TABS)[number];

export default function AttendancePage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("attendance.manage");
  const [tab, setTab] = useState<Tab>("Appel");

  if (!currentSchoolId) return <p className="text-sm text-slate-500">Chargement...</p>;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Présences</h1>

      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium ${
              tab === t ? "border-b-2 border-slate-900 text-slate-900" : "text-slate-500 hover:text-slate-800"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Appel" && <AttendanceSessionPanel schoolId={currentSchoolId} canManage={canManage} />}
      {tab === "Statistiques" && <AttendanceStatsPanel schoolId={currentSchoolId} />}
    </div>
  );
}
