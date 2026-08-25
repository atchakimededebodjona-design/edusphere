"use client";

import { Fragment, useState } from "react";
import { ApiError } from "@/lib/api/client";

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

function FieldInput({
  field,
  value,
  onChange,
  disabled,
}: {
  field: { key: string; label: string; type: FieldType; required?: boolean };
  value: string | number | boolean;
  onChange: (value: string | number | boolean) => void;
  disabled: boolean;
}) {
  if (field.type === "checkbox") {
    return (
      <input
        type="checkbox"
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
    );
  }
  return (
    <input
      type={field.type}
      value={value as string | number}
      onChange={(e) => onChange(coerce(field.type, e.target.value))}
      disabled={disabled}
      required={field.required}
      className="w-full rounded border border-slate-300 px-2 py-1 text-sm disabled:bg-slate-100"
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

  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-slate-900">{title}</h2>

      <div className="overflow-x-auto rounded border border-slate-200">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50">
            <tr>
              {renderRowExtra && <th className="w-8" />}
              {fields.map((field) => (
                <th key={field.key} className="px-3 py-2 text-left font-medium text-slate-600">
                  {field.label}
                </th>
              ))}
              {canManage && <th className="w-24" />}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((item) => {
              const isEditing = editingId === item.id;
              const isExpanded = expandedIds.has(item.id);
              return (
                <Fragment key={item.id}>
                  <tr>
                    {renderRowExtra && (
                      <td className="px-2">
                        <button
                          type="button"
                          onClick={() => toggleExpanded(item.id)}
                          className="text-slate-500 hover:text-slate-900"
                          aria-label="Afficher le détail"
                        >
                          {isExpanded ? "▾" : "▸"}
                        </button>
                      </td>
                    )}
                    {fields.map((field) => (
                      <td key={field.key} className="px-3 py-2">
                        {isEditing ? (
                          <FieldInput
                            field={field}
                            value={editValues[field.key]}
                            onChange={(value) => setEditValues((prev) => ({ ...prev, [field.key]: value }))}
                            disabled={saving}
                          />
                        ) : field.type === "checkbox" ? (
                          item[field.key] ? "Oui" : "Non"
                        ) : (
                          String(item[field.key] ?? "")
                        )}
                      </td>
                    ))}
                    {canManage && (
                      <td className="px-3 py-2 text-right">
                        {isEditing ? (
                          <div className="flex justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => handleSaveEdit(item.id)}
                              disabled={saving}
                              className="text-xs text-slate-900 underline"
                            >
                              Enregistrer
                            </button>
                            <button
                              type="button"
                              onClick={() => setEditingId(null)}
                              className="text-xs text-slate-500 underline"
                            >
                              Annuler
                            </button>
                          </div>
                        ) : (
                          <button type="button" onClick={() => startEdit(item)} className="text-xs text-slate-700 underline">
                            Modifier
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                  {renderRowExtra && isExpanded && (
                    <tr>
                      <td colSpan={fields.length + 1 + (canManage ? 1 : 0)} className="bg-slate-50 px-6 py-3">
                        {renderRowExtra(item)}
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
            {items.length === 0 && (
              <tr>
                <td colSpan={fields.length + (renderRowExtra ? 1 : 0) + (canManage ? 1 : 0)} className="px-3 py-4 text-center text-slate-400">
                  Aucun élément.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {canManage && (
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3 rounded border border-dashed border-slate-300 p-3">
          {fields.map((field) => (
            <label key={field.key} className="flex flex-col gap-1 text-xs text-slate-600">
              {field.label}
              <FieldInput
                field={field}
                value={createValues[field.key]}
                onChange={(value) => setCreateValues((prev) => ({ ...prev, [field.key]: value }))}
                disabled={creating}
              />
            </label>
          ))}
          <button
            type="submit"
            disabled={creating}
            className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          >
            {creating ? "Ajout..." : "Ajouter"}
          </button>
        </form>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  );
}
