"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { templates as templatesClient, type ReportCardTemplate } from "@/lib/report-cards/client";
import { useAuth } from "@/lib/auth/useAuth";
import { GenerationPanel } from "@/app/(app)/report-cards/GenerationPanel";
import { STARTER_TEMPLATE } from "@/app/(app)/report-cards/starterTemplate";

function TemplatesPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const [items, setItems] = useState<ReportCardTemplate[] | null>(null);
  const [name, setName] = useState("");
  const [htmlContent, setHtmlContent] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void templatesClient.list(schoolId).then(setItems);
  }, [schoolId]);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const created = await templatesClient.create({ school_id: schoolId, name, html_content: htmlContent, is_default: isDefault });
      setItems((prev) => [...(prev ?? []), created]);
      setName("");
      setHtmlContent("");
      setIsDefault(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setCreating(false);
    }
  }

  if (items === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-1">
        {items.map((t) => (
          <li key={t.id} className="rounded border border-slate-200 px-3 py-1.5 text-sm">
            {t.name} {t.is_default && <span className="text-xs text-slate-500">(par défaut)</span>}
          </li>
        ))}
        {items.length === 0 && <li className="text-sm text-slate-400">Aucun modèle.</li>}
      </ul>

      {canManage && (
        <form onSubmit={handleCreate} className="flex flex-col gap-3 rounded border border-dashed border-slate-300 p-4">
          <h2 className="text-sm font-semibold text-slate-900">Nouveau modèle</h2>
          <div className="flex flex-wrap items-center gap-3">
            <input
              placeholder="Nom du modèle"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="rounded border border-slate-300 px-3 py-2 text-sm"
            />
            <label className="flex items-center gap-1 text-xs text-slate-600">
              <input type="checkbox" checked={isDefault} onChange={(e) => setIsDefault(e.target.checked)} />
              Modèle par défaut
            </label>
            <button
              type="button"
              onClick={() => setHtmlContent(STARTER_TEMPLATE)}
              className="rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-100"
            >
              Charger un modèle de départ
            </button>
          </div>
          <textarea
            placeholder="Contenu HTML/Jinja2 du bulletin"
            value={htmlContent}
            onChange={(e) => setHtmlContent(e.target.value)}
            required
            rows={16}
            className="w-full rounded border border-slate-300 px-3 py-2 font-mono text-xs"
          />
          <button
            type="submit"
            disabled={creating}
            className="w-fit rounded bg-slate-900 px-4 py-2 text-sm text-white disabled:opacity-50"
          >
            {creating ? "Création..." : "Créer le modèle"}
          </button>
          {error && <p className="text-sm text-red-700">{error}</p>}
        </form>
      )}
    </div>
  );
}

const TABS = ["Modèles", "Génération & suivi"] as const;
type Tab = (typeof TABS)[number];

export default function ReportCardsPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("report_cards.manage");
  const [tab, setTab] = useState<Tab>("Génération & suivi");

  if (!currentSchoolId) return <p className="text-sm text-slate-500">Chargement...</p>;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-slate-900">Bulletins</h1>

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

      {tab === "Modèles" && <TemplatesPanel schoolId={currentSchoolId} canManage={canManage} />}
      {tab === "Génération & suivi" && <GenerationPanel schoolId={currentSchoolId} canManage={canManage} />}
    </div>
  );
}
