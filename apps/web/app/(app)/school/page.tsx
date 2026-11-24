"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/lib/auth/useAuth";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/Button";
import { TableSkeleton } from "@/components/ui/DataTable";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { TextField } from "@/components/ui/Field";
import { Alert, Card, PageHeader, SectionTitle } from "@/components/ui/Surface";
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
  if (!school) return <TableSkeleton rows={4} />;

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <PageHeader title="Paramètres de l'école" description="Le nom et le logo apparaissent dans le menu, sur les reçus et sur les bulletins." />

      <Card className="flex flex-col gap-3">
        <SectionTitle title="Logo" />
        <div className="flex flex-wrap items-center gap-4">
          {logoUrl ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={logoUrl} alt="Logo de l'école" className="h-20 w-20 rounded-lg border border-slate-200 bg-white object-contain p-1" />
          ) : (
            <div className="flex h-20 w-20 items-center justify-center rounded-lg border border-dashed border-slate-300 bg-slate-50 text-center text-xs text-slate-600">
              Aucun logo
            </div>
          )}
          {canManage && (
            <div className="flex flex-col gap-1">
              <label
                className={`inline-flex min-h-11 w-fit items-center rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-primary-600 sm:min-h-10 ${
                  logoUploading ? "cursor-wait opacity-60" : "cursor-pointer hover:bg-slate-50"
                }`}
              >
                {logoUploading ? "Envoi en cours..." : "Changer le logo"}
                <input
                  type="file"
                  accept={LOGO_MIME_TYPES.join(",")}
                  onChange={handleLogoChange}
                  disabled={logoUploading}
                  className="sr-only"
                />
              </label>
              <p className="text-xs text-slate-600">JPEG, PNG ou WebP, 2 Mio au maximum.</p>
            </div>
          )}
        </div>
        {logoError && <Alert tone="danger">{logoError}</Alert>}
      </Card>

      <form onSubmit={handleSubmit}>
        <Card className="flex flex-col gap-4">
          <SectionTitle title="Coordonnées" />
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField label="Nom de l'école" value={form.name ?? ""} onChange={update("name")} disabled={!canManage} required />
            <TextField label="Adresse" value={form.address ?? ""} onChange={update("address")} disabled={!canManage} />
            <TextField label="Téléphone" type="tel" value={form.phone ?? ""} onChange={update("phone")} disabled={!canManage} />
            <TextField label="Email" type="email" value={form.email ?? ""} onChange={update("email")} disabled={!canManage} />
            <TextField
              label="Fuseau horaire"
              value={form.timezone ?? ""}
              onChange={update("timezone")}
              disabled={!canManage}
              hint="Exemple : Africa/Lome"
            />
            <TextField label="Devise" value={form.currency ?? ""} onChange={update("currency")} disabled={!canManage} hint="Exemple : XOF (franc CFA)" />
          </div>
          {canManage && (
            <Button type="submit" disabled={saveStatus === "saving"} className="self-start">
              {saveStatus === "saving" ? "Enregistrement..." : "Enregistrer"}
            </Button>
          )}
          {saveStatus === "saved" && <Alert tone="success">Modifications enregistrées.</Alert>}
          {error && <Alert tone="danger">{error}</Alert>}
        </Card>
      </form>
    </div>
  );
}
