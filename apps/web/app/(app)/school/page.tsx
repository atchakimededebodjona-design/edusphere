"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth/useAuth";
import { ApiError } from "@/lib/api/client";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import {
  getSchool,
  getSchoolLogoBlobUrl,
  updateSchool,
  uploadSchoolLogo,
  type School,
  type SchoolUpdate,
} from "@/lib/schools/client";
import { announceSchoolLogoChange } from "@/lib/schools/useSchoolLogo";

type SaveStatus = "idle" | "saving" | "saved" | "error";

// Mêmes règles que l'API (apps/api/app/modules/students/service.py::validate_logo_upload), vérifiées
// ici pour prévenir avant l'envoi : l'API reste l'autorité et refuse elle-même tout autre fichier.
const LOGO_MAX_BYTES = 2 * 1024 * 1024;
const LOGO_MIME_TYPES = ["image/jpeg", "image/png", "image/webp"];

export default function SchoolSettingsPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("schools.manage");

  const [school, setSchool] = useState<School | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [form, setForm] = useState<SchoolUpdate>({});
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [logoError, setLogoError] = useState<string | null>(null);
  const [logoUploading, setLogoUploading] = useState(false);

  const loadSchool = useCallback(() => {
    if (!currentSchoolId) return;
    setLoadError(null);
    getSchool(currentSchoolId)
      .then((result) => {
        setSchool(result);
        setForm({
          name: result.name,
          address: result.address ?? "",
          phone: result.phone ?? "",
          email: result.email ?? "",
          timezone: result.timezone,
          currency: result.currency,
        });
      })
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
    void getSchoolLogoBlobUrl(currentSchoolId).then(setLogoUrl);
  }, [currentSchoolId]);

  useEffect(() => {
    loadSchool();
  }, [loadSchool]);

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
    // Réinitialisé tout de suite : sans ça, choisir à nouveau le même fichier (après une erreur) ne
    // redéclenche pas onChange.
    event.target.value = "";
    if (!file || !currentSchoolId) return;

    setLogoError(null);
    if (file.size === 0) {
      setLogoError("Ce fichier est vide.");
      return;
    }
    if (file.size > LOGO_MAX_BYTES) {
      setLogoError("Logo trop volumineux (maximum 2 Mio). Réduisez l'image avant de l'envoyer.");
      return;
    }
    if (!LOGO_MIME_TYPES.includes(file.type)) {
      setLogoError("Type de fichier non autorisé (JPEG, PNG ou WebP uniquement).");
      return;
    }

    setLogoUploading(true);
    try {
      const updated = await uploadSchoolLogo(currentSchoolId, file);
      const newUrl = await getSchoolLogoBlobUrl(currentSchoolId);
      setLogoUrl(newUrl);
      // Le menu latéral affiche aussi ce logo : il le recharge sans attendre une nouvelle connexion.
      announceSchoolLogoChange(currentSchoolId, updated.logo_path);
    } catch (err) {
      setLogoError(err instanceof ApiError ? err.message : "Échec de l'envoi du logo.");
    } finally {
      setLogoUploading(false);
    }
  }

  if (loadError) return <ErrorRetry message={loadError} onRetry={loadSchool} />;
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
          <div className="flex flex-col gap-1">
            <label
              className={`w-fit rounded border border-slate-300 px-3 py-2 text-sm text-slate-700 ${
                logoUploading ? "cursor-wait opacity-60" : "cursor-pointer hover:bg-slate-100"
              }`}
            >
              {logoUploading ? "Envoi en cours..." : "Changer le logo"}
              <input
                type="file"
                accept={LOGO_MIME_TYPES.join(",")}
                onChange={handleLogoChange}
                disabled={logoUploading}
                className="hidden"
              />
            </label>
            <p className="text-xs text-slate-500">JPEG, PNG ou WebP, 2 Mio au maximum.</p>
          </div>
        )}
      </div>
      {logoError && (
        <p role="alert" className="-mt-3 text-sm text-red-700">
          {logoError}
        </p>
      )}

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
