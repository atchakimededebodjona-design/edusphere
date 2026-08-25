"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth/useAuth";

export function TopBar() {
  const { user, logout } = useAuth();
  const router = useRouter();

  async function handleLogout() {
    await logout();
    router.push("/login");
  }

  return (
    <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-6">
      <span className="text-lg font-bold text-slate-900">EduSphere</span>
      <div className="flex items-center gap-4">
        {user && <span className="text-sm text-slate-600">{user.full_name}</span>}
        <button
          type="button"
          onClick={handleLogout}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100"
        >
          Déconnexion
        </button>
      </div>
    </header>
  );
}
