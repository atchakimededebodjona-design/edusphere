"use client";

import { isPlatformAdmin } from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/useAuth";
import { PlatformDashboard } from "./PlatformDashboard";
import { SchoolDashboard } from "./SchoolDashboard";

export default function DashboardPage() {
  const { user } = useAuth();
  return isPlatformAdmin(user) ? <PlatformDashboard /> : <SchoolDashboard />;
}
