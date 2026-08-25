"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getSchool, type School } from "@/lib/schools/client";
import { useAuth } from "@/lib/auth/useAuth";

export default function DashboardPage() {
  const { currentSchoolId, permissions } = useAuth();
  const [school, setSchool] = useState<School | null>(null);

  useEffect(() => {
    if (currentSchoolId) {
      void getSchool(currentSchoolId).then(setSchool);
    }
  }, [currentSchoolId]);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold text-slate-900">Tableau de bord</h1>
      {school ? (
        <p className="text-slate-600">
          Bienvenue sur l&apos;espace de <strong>{school.name}</strong>.
        </p>
      ) : (
        <p className="text-slate-500">Chargement de l&apos;école...</p>
      )}
      {permissions.includes("schools.read") && (
        <Link href="/school" className="w-fit rounded bg-slate-900 px-4 py-2 text-sm text-white">
          Paramètres de l&apos;école
        </Link>
      )}
    </div>
  );
}
