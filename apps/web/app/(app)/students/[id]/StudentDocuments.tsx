"use client";

import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { documents, type StudentDocument } from "@/lib/students/client";

export function StudentDocuments({ studentId, canManage }: { studentId: string; canManage: boolean }) {
  const [items, setItems] = useState<StudentDocument[] | null>(null);
  const [documentType, setDocumentType] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void documents.list(studentId).then(setItems);
  }, [studentId]);

  async function handleUpload(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !documentType) return;
    setBusy(true);
    setError(null);
    try {
      const created = await documents.upload(studentId, documentType, file);
      setItems((prev) => [...(prev ?? []), created]);
      setDocumentType("");
      setFile(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemove(documentId: string) {
    setBusy(true);
    setError(null);
    try {
      await documents.remove(studentId, documentId);
      setItems((prev) => (prev ?? []).filter((d) => d.id !== documentId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  }

  if (items === null) return <p className="text-sm text-slate-400">Chargement...</p>;

  return (
    <div className="flex flex-col gap-3">
      <h2 className="text-lg font-semibold text-slate-900">Documents</h2>
      <ul className="flex flex-col gap-1">
        {items.map((doc) => (
          <li key={doc.id} className="flex items-center justify-between rounded border border-slate-200 px-3 py-1.5 text-sm">
            <span>
              {doc.document_type} — {doc.original_filename}
            </span>
            <div className="flex gap-3">
              <button type="button" onClick={() => documents.download(studentId, doc)} className="text-xs text-slate-700 underline">
                Télécharger
              </button>
              {canManage && (
                <button type="button" onClick={() => handleRemove(doc.id)} disabled={busy} className="text-xs text-red-700 underline">
                  Supprimer
                </button>
              )}
            </div>
          </li>
        ))}
        {items.length === 0 && <li className="text-sm text-slate-400">Aucun document.</li>}
      </ul>

      {canManage && (
        <form onSubmit={handleUpload} className="flex flex-wrap items-end gap-3 rounded border border-dashed border-slate-300 p-3">
          <label className="flex flex-col gap-1 text-xs text-slate-600">
            Type de document
            <input
              placeholder="ex. Acte de naissance"
              value={documentType}
              onChange={(e) => setDocumentType(e.target.value)}
              required
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            />
          </label>
          <input
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            required
            className="text-sm"
          />
          <button type="submit" disabled={busy} className="rounded bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-50">
            {busy ? "Envoi..." : "Uploader"}
          </button>
        </form>
      )}
      {error && <p className="text-sm text-red-700">{error}</p>}
    </div>
  );
}
