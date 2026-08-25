"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth/useAuth";
import { ApiError } from "@/lib/api/client";
import {
  getSchool,
  getSchoolLogoBlobUrl,
  updateSchool,
  uploadSchoolLogo,
  type School,
  type SchoolUpdate,
} from "@/lib/schools/client";

type SaveStatus = "idle" | "saving" | "saved" | "error";

export default function SchoolSettingsPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("schools.manage");

  const [school, setSchool] = useState<School | null>(null);
  const [form, setForm] = useState<SchoolUpdate>({});
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!currentSchoolId) return;
    void getSchool(currentSchoolId).then((result) => {
      setSchool(result);
      setForm({
        name: result.name,
        address: result.address ?? "",
        phone: result.phone ?? "",
        email: result.email ?? "",
        timezone: result.timezone,
        currency: result.currency,
      });
    });
    void getSchoolLogoBlobUrl(currentSchoolId).then(setLogoUrl);
  }, [currentSchoolId]);

  function update(field: keyof SchoolUpdate) {
    return (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((prev) => ({ ...prev, [field]: event.target.value }));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!currentSchoolId) return;
    setSaveStatus("saving");
    setError(null);
    try {
      const updated = await updateSchool(currentSchoolId, form);
      setSchool(updated);
      setSaveStatus("saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
      setSaveStatus("error");
    }
  }

  async function handleLogoChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !currentSchoolId) return;
    try {
      await uploadSchoolLogo(currentSchoolId, file);
      const newUrl = await getSchoolLogoBlobUrl(currentSchoolId);
      setLogoUrl(newUrl);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Échec de l'envoi du logo.");
    }
  }

  if (!school) return <p className="text-slate-500">Chargement...</p>;

  return (
    <div className="flex max-w-xl flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Paramètres de l&apos;école</h1>

      <div className="flex items-center gap-4">
        {logoUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={logoUrl} alt="Logo de l'école" className="h-16 w-16 rounded object-contain" />
        ) : (
          <div className="flex h-16 w-16 items-center justify-center rounded bg-slate-200 text-xs text-slate-500">
            Aucun logo
          </div>
        )}
        {canManage && (
          <label className="cursor-pointer rounded border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-100">
            Changer le logo
            <input type="file" accept="image/*" onChange={handleLogoChange} className="hidden" />
          </label>
        )}
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <input
          placeholder="Nom de l'école"
          value={form.name ?? ""}
          onChange={update("name")}
          disabled={!canManage}
          required
          className="rounded border border-slate-300 px-3 py-2 disabled:bg-slate-100"
        />
        <input
          placeholder="Adresse"
          value={form.address ?? ""}
          onChange={update("address")}
          disabled={!canManage}
          className="rounded border border-slate-300 px-3 py-2 disabled:bg-slate-100"
        />
        <input
          placeholder="Téléphone"
          value={form.phone ?? ""}
          onChange={update("phone")}
          disabled={!canManage}
          className="rounded border border-slate-300 px-3 py-2 disabled:bg-slate-100"
        />
        <input
          type="email"
          placeholder="Email"
          value={form.email ?? ""}
          onChange={update("email")}
          disabled={!canManage}
          className="rounded border border-slate-300 px-3 py-2 disabled:bg-slate-100"
        />
        <input
          placeholder="Fuseau horaire"
          value={form.timezone ?? ""}
          onChange={update("timezone")}
          disabled={!canManage}
          className="rounded border border-slate-300 px-3 py-2 disabled:bg-slate-100"
        />
        <input
          placeholder="Devise"
          value={form.currency ?? ""}
          onChange={update("currency")}
          disabled={!canManage}
          className="rounded border border-slate-300 px-3 py-2 disabled:bg-slate-100"
        />
        {canManage && (
          <button
            type="submit"
            disabled={saveStatus === "saving"}
            className="w-fit rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {saveStatus === "saving" ? "Enregistrement..." : "Enregistrer"}
          </button>
        )}
        {saveStatus === "saved" && <p className="text-sm text-green-700">Modifications enregistrées.</p>}
        {error && <p className="text-sm text-red-700">{error}</p>}
      </form>
    </div>
  );
}
