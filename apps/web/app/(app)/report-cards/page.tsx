"use client";

import { useId, useState } from "react";
import { TableSkeleton } from "@/components/ui/DataTable";
import { TextField } from "@/components/ui/Field";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { Badge, EmptyState, PageHeader } from "@/components/ui/Surface";
import { TabPanel, Tabs } from "@/components/ui/Tabs";
import { ApiError } from "@/lib/api/client";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { templates as templatesClient } from "@/lib/report-cards/client";
import { useAuth } from "@/lib/auth/useAuth";
import { GenerationPanel } from "@/app/(app)/report-cards/GenerationPanel";
import { STARTER_TEMPLATE } from "@/app/(app)/report-cards/starterTemplate";

function TemplatesPanel({ schoolId, canManage }: { schoolId: string; canManage: boolean }) {
  const list = useAsyncData(() => templatesClient.list(schoolId), [schoolId]);
  const [name, setName] = useState("");
  const [htmlContent, setHtmlContent] = useState("");
  const [isDefault, setIsDefault] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      await templatesClient.create({ school_id: schoolId, name, html_content: htmlContent, is_default: isDefault });
      setName("");
      setHtmlContent("");
      setIsDefault(false);
      list.retry();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setCreating(false);
    }
  }

  if (list.isLoading) return <TableSkeleton rows={3} />;
  if (list.data === null) return <ErrorRetry message={list.error ?? "Une erreur est survenue."} onRetry={list.retry} />;
  const items = list.data;

  return (
    <div className="flex flex-col gap-4">
      {list.error && <ErrorRetry message={list.error} onRetry={list.retry} />}
      <ul className="flex flex-col gap-1">
        {items.map((t) => (
          <li key={t.id} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
            <span className="font-medium text-slate-900">{t.name}</span> {t.is_default && <Badge tone="info">Par défaut</Badge>}
          </li>
        ))}
      </ul>
      {items.length === 0 && (
        <EmptyState
          icon="fileText"
          title="Aucun modèle."
          description={canManage ? "Créez un modèle ci-dessous ; « Charger un modèle de départ » en propose un prêt à adapter." : undefined}
        />
      )}

      {canManage && (
        <form onSubmit={handleCreate} className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
          <h2 className="text-base font-bold text-slate-900">Nouveau modèle</h2>
          <div className="flex flex-wrap items-end gap-3">
            <div className="w-full sm:w-72">
              <TextField label="Nom du modèle" placeholder="Nom du modèle" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <label className="flex min-h-11 items-center gap-2 text-sm font-medium text-slate-800">
              <input
                type="checkbox"
                checked={isDefault}
                onChange={(e) => setIsDefault(e.target.checked)}
                className="h-5 w-5 rounded border-slate-400 accent-primary-600"
              />
              Modèle par défaut
            </label>
            <button
              type="button"
              onClick={() => setHtmlContent(STARTER_TEMPLATE)}
              className="inline-flex min-h-9 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
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
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-xs text-slate-900 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25"
            aria-label="Contenu HTML/Jinja2 du bulletin"
          />
          <button
            type="submit"
            disabled={creating}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10 w-fit"
          >
            {creating ? "Création..." : "Créer le modèle"}
          </button>
          {error && (
            <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
              {error}
            </p>
          )}
        </form>
      )}
    </div>
  );
}

const TABS = [
  { key: "generation", label: "Génération & suivi" },
  { key: "templates", label: "Modèles" },
] as const;
type Tab = (typeof TABS)[number]["key"];

export default function ReportCardsPage() {
  const { currentSchoolId, permissions } = useAuth();
  const canManage = permissions.includes("report_cards.manage");
  const [tab, setTab] = useState<Tab>("generation");
  const tabsId = useId();

  if (!currentSchoolId) return <TableSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title="Bulletins" description="Génération et publication des bulletins par classe et par période, et modèles de mise en page." />
      <div>
        <Tabs id={tabsId} label="Bulletins" tabs={[...TABS]} value={tab} onChange={setTab} />
        <TabPanel id={tabsId} active={tab}>
          {tab === "templates" && <TemplatesPanel schoolId={currentSchoolId} canManage={canManage} />}
          {tab === "generation" && <GenerationPanel schoolId={currentSchoolId} canManage={canManage} />}
        </TabPanel>
      </div>
    </div>
  );
}
