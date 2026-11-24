"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { controlClass } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { Card, EmptyState, SectionTitle } from "@/components/ui/Surface";
import { ApiError } from "@/lib/api/client";
import { formatDateFR } from "@/lib/format/date";

// Refonte, phase 3 lot B (2026-11-24) — liste + ajout + modification en ligne, sur le tableau commun
// (cartes sur téléphone). Mêmes props et même comportement qu'avant : seuls l'affichage, les libellés
// des champs et les dates en français changent.

export type FieldType = "text" | "number" | "date" | "checkbox";

export type FieldSpec<T> = {
  key: Extract<keyof T, string>;
  label: string;
  type: FieldType;
  required?: boolean;
};

export type FieldValues = Record<string, string | number | boolean>;

type ResourceCrudPanelProps<T extends { id: string }> = {
  title: string;
  items: T[];
  fields: FieldSpec<T>[];
  canManage: boolean;
  onCreate: (values: FieldValues) => Promise<T>;
  onUpdate: (id: string, values: FieldValues) => Promise<T>;
  onItemCreated: (item: T) => void;
  onItemUpdated: (item: T) => void;
  /** Contenu additionnel affiché sous une ligne dépliée (ex. les périodes d'une année). */
  renderRowExtra?: (item: T) => React.ReactNode;
};

function emptyValues<T>(fields: FieldSpec<T>[]): FieldValues {
  const values: FieldValues = {};
  for (const field of fields) values[field.key] = field.type === "checkbox" ? false : "";
  return values;
}

function valuesFromItem<T>(item: T, fields: FieldSpec<T>[]): FieldValues {
  const values: FieldValues = {};
  for (const field of fields) values[field.key] = item[field.key] as string | number | boolean;
  return values;
}

function coerce(type: FieldType, raw: string | number | boolean): string | number | boolean {
  if (type === "number") return raw === "" ? "" : Number(raw);
  return raw;
}

function display(type: FieldType, value: unknown): string {
  if (type === "checkbox") return value ? "Oui" : "Non";
  if (value === null || value === undefined || value === "") return "—";
  if (type === "date") return formatDateFR(String(value));
  return String(value);
}

const checkboxClass = "h-5 w-5 rounded border-slate-400 accent-primary-600";

function FieldInput({
  field,
  value,
  onChange,
  disabled,
  ariaLabel,
}: {
  field: { key: string; label: string; type: FieldType; required?: boolean };
  value: string | number | boolean;
  onChange: (value: string | number | boolean) => void;
  disabled: boolean;
  /** Nom du champ quand il n'a pas de libellé visible (modification dans la ligne). */
  ariaLabel?: string;
}) {
  if (field.type === "checkbox") {
    return (
      <input
        type="checkbox"
        aria-label={ariaLabel}
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
        className={checkboxClass}
      />
    );
  }
  return (
    <input
      type={field.type}
      aria-label={ariaLabel}
      value={value as string | number}
      onChange={(e) => onChange(coerce(field.type, e.target.value))}
      disabled={disabled}
      required={field.required}
      className={controlClass}
    />
  );
}

export function ResourceCrudPanel<T extends { id: string }>({
  title,
  items,
  fields,
  canManage,
  onCreate,
  onUpdate,
  onItemCreated,
  onItemUpdated,
  renderRowExtra,
}: ResourceCrudPanelProps<T>) {
  const [createValues, setCreateValues] = useState<FieldValues>(() => emptyValues(fields));
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<FieldValues>({});
  const [saving, setSaving] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  function toggleExpanded(id: string) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const item = await onCreate(createValues);
      onItemCreated(item);
      setCreateValues(emptyValues(fields));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setCreating(false);
    }
  }

  function startEdit(item: T) {
    setEditingId(item.id);
    setEditValues(valuesFromItem(item, fields));
    setError(null);
  }

  async function handleSaveEdit(id: string) {
    setSaving(true);
    setError(null);
    try {
      const item = await onUpdate(id, editValues);
      onItemUpdated(item);
      setEditingId(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setSaving(false);
    }
  }

  const columns: Column<T>[] = [
    ...(renderRowExtra
      ? [
          {
            key: "__expand",
            header: <span className="sr-only">Détail</span>,
            mobile: "lead" as const,
            cell: (item: T) => {
              const expanded = expandedIds.has(item.id);
              return (
                <button
                  type="button"
                  onClick={() => toggleExpanded(item.id)}
                  aria-label="Afficher le détail"
                  aria-expanded={expanded}
                  className="flex h-9 w-9 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600"
                >
                  <Icon name={expanded ? "chevronDown" : "chevronRight"} className="h-5 w-5" />
                </button>
              );
            },
          },
        ]
      : []),
    ...fields.map(
      (field, index): Column<T> => ({
        key: field.key,
        header: field.label,
        mobile: index === 0 ? "title" : undefined,
        cell: (item: T) =>
          editingId === item.id ? (
            <FieldInput
              field={field}
              value={editValues[field.key]}
              onChange={(value) => setEditValues((prev) => ({ ...prev, [field.key]: value }))}
              disabled={saving}
              ariaLabel={field.label}
            />
          ) : (
            display(field.type, item[field.key])
          ),
      }),
    ),
    ...(canManage
      ? [
          {
            key: "__actions",
            header: <span className="sr-only">Actions</span>,
            align: "right" as const,
            mobile: "full" as const,
            cell: (item: T) =>
              editingId === item.id ? (
                <div className="flex flex-wrap gap-2 sm:justify-end">
                  <Button size="sm" onClick={() => handleSaveEdit(item.id)} disabled={saving}>
                    {saving ? "Enregistrement..." : "Enregistrer"}
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => setEditingId(null)} disabled={saving}>
                    Annuler
                  </Button>
                </div>
              ) : (
                <Button variant="quiet" size="sm" onClick={() => startEdit(item)} className="max-sm:-ml-3">
                  Modifier
                </Button>
              ),
          },
        ]
      : []),
  ];

  return (
    <div className="flex flex-col gap-3">
      <SectionTitle title={title} />

      <DataTable
        caption={title}
        columns={columns}
        rows={items}
        rowKey={(item) => item.id}
        rowTone={(item) => (editingId === item.id ? "highlight" : undefined)}
        after={renderRowExtra ? (item) => (expandedIds.has(item.id) ? renderRowExtra(item) : null) : undefined}
        empty={<EmptyState title="Aucun élément." description={canManage ? "Ajoutez le premier avec le formulaire ci-dessous." : undefined} />}
      />

      {error && (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      )}

      {canManage && (
        <form onSubmit={handleCreate}>
          <Card className="flex flex-col gap-3">
            <p className="text-sm font-semibold text-slate-900">Ajouter</p>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {fields.map((field) =>
                field.type === "checkbox" ? (
                  <label key={field.key} className="flex min-h-11 items-center gap-2 self-end text-sm font-medium text-slate-800">
                    <FieldInput
                      field={field}
                      value={createValues[field.key]}
                      onChange={(value) => setCreateValues((prev) => ({ ...prev, [field.key]: value }))}
                      disabled={creating}
                    />
                    {field.label}
                  </label>
                ) : (
                  <label key={field.key} className="flex flex-col gap-1 text-sm font-medium text-slate-800">
                    {field.label}
                    <FieldInput
                      field={field}
                      value={createValues[field.key]}
                      onChange={(value) => setCreateValues((prev) => ({ ...prev, [field.key]: value }))}
                      disabled={creating}
                    />
                  </label>
                ),
              )}
            </div>
            <Button type="submit" icon="plus" disabled={creating} className="self-start">
              {creating ? "Ajout..." : "Ajouter"}
            </Button>
          </Card>
        </form>
      )}
    </div>
  );
}
