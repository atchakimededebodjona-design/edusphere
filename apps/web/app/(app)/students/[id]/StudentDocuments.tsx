"use client";

import { TableSkeleton } from "@/components/ui/DataTable";
import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { formatDateFR } from "@/lib/format/date";
import { documents, type StudentDocument } from "@/lib/students/client";

const DOCUMENT_MAX_BYTES = 10 * 1024 * 1024;
const ALLOWED_MIME_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/webp"];

const QUICK_TYPES = [
  "Acte de naissance",
  "Certificat de naissance",
  "Photo d'identité",
  "Certificat médical",
  "Bulletin",
  "Certificat de scolarité",
];
const OTHER_TYPE = "Autre";

function formatFileSize(bytes: number | null): string {
  if (bytes === null) return "—";
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

// "2026-10-07T12:34:00Z" -> "07/10/2026" (created_at est un datetime, pas juste une date, mais
// seule la partie date intéresse l'affichage ici — formatDateFR ne lit que le préfixe AAAA-MM-JJ).
function formatDocumentDate(isoDateTime: string): string {
  return formatDateFR(isoDateTime);
}

export function StudentDocuments({ studentId, canManage }: { studentId: string; canManage: boolean }) {
  const [items, setItems] = useState<StudentDocument[] | null>(null);
  const [quickType, setQuickType] = useState("");
  const [customType, setCustomType] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const loadDocuments = useCallback(() => {
    setLoadError(null);
    documents
      .list(studentId)
      .then(setItems)
      .catch((err) => setLoadError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [studentId]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    setUploadSuccess(false);
    if (!selected) {
      setFile(null);
      setFileError(null);
      return;
    }
    if (selected.size === 0) {
      setFile(null);
      setFileError("Ce fichier est vide.");
      return;
    }
    if (selected.size > DOCUMENT_MAX_BYTES) {
      setFile(null);
      setFileError("Fichier trop volumineux (maximum 10 Mio).");
      return;
    }
    if (!ALLOWED_MIME_TYPES.includes(selected.type)) {
      setFile(null);
      setFileError("Type de fichier non autorisé (PDF, JPEG, PNG ou WebP uniquement).");
      return;
    }
    setFile(selected);
    setFileError(null);
  }

  const documentType = quickType === OTHER_TYPE ? customType.trim() : quickType;

  async function handleUpload(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !documentType) return;
    setBusy(true);
    setError(null);
    setUploadSuccess(false);
    try {
      const created = await documents.upload(studentId, documentType, file);
      setItems((prev) => [...(prev ?? []), created]);
      setQuickType("");
      setCustomType("");
      setFile(null);
      setUploadSuccess(true);
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
      setPendingDeleteId(null);
    }
  }

  if (loadError) return <ErrorRetry message={loadError} onRetry={loadDocuments} />;
  if (items === null) return <TableSkeleton rows={3} />;

  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-bold text-slate-900">Documents</h2>
        <span className="text-sm text-slate-600" data-testid="documents-count">
          {items.length} document{items.length > 1 ? "s" : ""}
        </span>
      </div>

      {items.length === 0 ? (
        <p className="text-sm text-slate-600" data-testid="documents-empty">
          Aucun document.
        </p>
      ) : (
        <>
          <div className="hidden overflow-x-auto sm:block">
            <table className="w-full min-w-[640px] text-left text-sm" data-testid="documents-table">
              <thead>
                <tr className="border-b border-slate-200 text-xs uppercase text-slate-600">
                  <th className="px-3 py-2 font-medium">Type</th>
                  <th className="px-3 py-2 font-medium">Nom du fichier</th>
                  <th className="px-3 py-2 font-medium">Date</th>
                  <th className="px-3 py-2 font-medium">Taille</th>
                  <th className="px-3 py-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((doc) => (
                  <tr key={doc.id} className="border-b border-slate-100" data-testid="document-row">
                    <td className="px-3 py-2">{doc.document_type}</td>
                    <td className="px-3 py-2">{doc.original_filename}</td>
                    <td className="px-3 py-2">{formatDocumentDate(doc.created_at)}</td>
                    <td className="px-3 py-2">{formatFileSize(doc.file_size)}</td>
                    <td className="px-3 py-2">
                      <DocumentActions
                        doc={doc}
                        canManage={canManage}
                        busy={busy}
                        pending={pendingDeleteId === doc.id}
                        onDownload={() => documents.download(studentId, doc)}
                        onAskDelete={() => setPendingDeleteId(doc.id)}
                        onCancelDelete={() => setPendingDeleteId(null)}
                        onConfirmDelete={() => handleRemove(doc.id)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="flex flex-col gap-2 sm:hidden">
            {items.map((doc) => (
              <div key={doc.id} className="rounded-xl border border-slate-200 bg-white p-4 text-sm" data-testid="document-card">
                <p className="font-medium text-slate-900">{doc.document_type}</p>
                <p className="text-slate-600">{doc.original_filename}</p>
                <p className="text-xs text-slate-600">
                  {formatDocumentDate(doc.created_at)} — {formatFileSize(doc.file_size)}
                </p>
                <div className="mt-2">
                  <DocumentActions
                    doc={doc}
                    canManage={canManage}
                    busy={busy}
                    pending={pendingDeleteId === doc.id}
                    onDownload={() => documents.download(studentId, doc)}
                    onAskDelete={() => setPendingDeleteId(doc.id)}
                    onCancelDelete={() => setPendingDeleteId(null)}
                    onConfirmDelete={() => handleRemove(doc.id)}
                  />
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {canManage && (
        <form onSubmit={handleUpload} className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
          <div className="flex flex-col gap-1">
            <span className="text-xs text-slate-600">Type de document</span>
            <div className="flex flex-wrap gap-2">
              {QUICK_TYPES.map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => setQuickType(type)}
                  className={`rounded-full border px-3 py-1 text-xs ${
                    quickType === type ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 text-slate-700"
                  }`}
                >
                  {type}
                </button>
              ))}
              <button
                key={OTHER_TYPE}
                type="button"
                onClick={() => setQuickType(OTHER_TYPE)}
                className={`rounded-full border px-3 py-1 text-xs ${
                  quickType === OTHER_TYPE ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 text-slate-700"
                }`}
              >
                {OTHER_TYPE}
              </button>
            </div>
            {quickType === OTHER_TYPE && (
              <input
                placeholder="Préciser le type de document"
                value={customType}
                onChange={(e) => setCustomType(e.target.value)}
                required
                className="mt-1 block w-full min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-900 sm:min-h-10 placeholder:text-slate-500 focus:border-primary-600 focus:outline-none focus:ring-2 focus:ring-primary-600/25 disabled:bg-slate-100 disabled:text-slate-500"
                data-testid="document-type-custom"
              />
            )}
          </div>

          <label className="flex flex-col gap-1 text-sm font-medium text-slate-800">
            Fichier
            <input
              type="file"
              accept={ALLOWED_MIME_TYPES.join(",")}
              onChange={handleFileChange}
              required
              className="min-w-0 text-sm text-slate-700 file:mr-3 file:min-h-10 file:cursor-pointer file:rounded-lg file:border-0 file:bg-primary-50 file:px-3 file:font-medium file:text-primary-800 hover:file:bg-primary-100"
              data-testid="document-file-input"
            />
          </label>
          {file && (
            <p className="text-xs text-slate-600" data-testid="document-file-preview">
              {file.name} — {formatFileSize(file.size)} — {file.type || "type inconnu"}
            </p>
          )}
          {fileError && (
            <p className="text-xs text-red-700" data-testid="document-file-error">
              {fileError}
            </p>
          )}

          <button
            type="submit"
            disabled={busy || !file || !documentType}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10 w-fit"
          >
            {busy ? "Envoi..." : "Ajouter le document"}
          </button>
        </form>
      )}
      {uploadSuccess && (
        <p className="text-sm text-green-700" data-testid="document-upload-success">
          Document ajouté.
        </p>
      )}
      {error && (
        <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" data-testid="document-error">
          {error}
        </p>
      )}
    </section>
  );
}

function DocumentActions({
  doc,
  canManage,
  busy,
  pending,
  onDownload,
  onAskDelete,
  onCancelDelete,
  onConfirmDelete,
}: {
  doc: StudentDocument;
  canManage: boolean;
  busy: boolean;
  pending: boolean;
  onDownload: () => void;
  onAskDelete: () => void;
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
}) {
  if (pending) {
    return (
      <div className="flex items-center gap-2 text-xs" data-testid="document-delete-confirm">
        <span className="text-slate-700">Supprimer {doc.original_filename} ?</span>
        <button type="button" onClick={onConfirmDelete} disabled={busy} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-red-700 hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50" data-testid="document-delete-confirm-yes">
          Oui, supprimer
        </button>
        <button type="button" onClick={onCancelDelete} disabled={busy} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-primary-700 hover:bg-primary-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50">
          Annuler
        </button>
      </div>
    );
  }
  return (
    <div className="flex gap-3">
      <button type="button" onClick={onDownload} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-primary-700 hover:bg-primary-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50" data-testid="document-download">
        Télécharger
      </button>
      {canManage && (
        <button type="button" onClick={onAskDelete} disabled={busy} className="inline-flex min-h-9 items-center rounded-lg px-2 text-sm font-medium text-red-700 hover:bg-red-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50" data-testid="document-delete">
          Supprimer
        </button>
      )}
    </div>
  );
}
