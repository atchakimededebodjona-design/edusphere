"use client";

import { useCallback, useEffect, useState } from "react";
import { formatDateTimeFR } from "@/components/notifications/NotificationItem";
import { Button } from "@/components/ui/Button";
import { TableSkeleton } from "@/components/ui/DataTable";
import { ErrorRetry } from "@/components/ui/ErrorRetry";
import { FieldFrame, SelectField, TextField, controlClass } from "@/components/ui/Field";
import { Alert, Badge, Card, EmptyState, PageHeader, SectionTitle } from "@/components/ui/Surface";
import { ApiError } from "@/lib/api/client";
import { schoolClasses, type SchoolClass } from "@/lib/academics/client";
import { useAuth } from "@/lib/auth/useAuth";
import {
  announcements,
  type AnnouncementAudience,
  type AnnouncementHistoryEntry,
  type AnnouncementTargetType,
} from "@/lib/notifications/client";

const TYPE_LABELS: Record<string, string> = {
  ANNOUNCEMENT: "Annonce",
  REPORT_CARD_PUBLISHED: "Bulletin",
  PAYMENT_RECORDED: "Paiement",
};

// 2026-11-17 — QUI reçoit l'annonce (en plus de la portée école entière / classes).
const AUDIENCE_LABELS: Record<AnnouncementAudience, string> = {
  ALL: "Tout le monde",
  PARENTS: "Les parents",
  TEACHERS: "Les enseignants",
  STAFF: "Le personnel de l'école",
};

function audienceHint(audience: AnnouncementAudience, targetType: AnnouncementTargetType): string {
  if (targetType === "CLASS") {
    if (audience === "PARENTS") return "Les parents (avec un compte EduLinkage) des élèves des classes choisies.";
    if (audience === "TEACHERS") return "Les enseignants affectés aux classes choisies.";
    return "Les parents des élèves et les enseignants des classes choisies.";
  }
  if (audience === "PARENTS") return "Les parents (avec un compte EduLinkage) de tous les élèves inscrits.";
  if (audience === "TEACHERS") return "Tous les enseignants de l'école.";
  if (audience === "STAFF") return "Direction, administration, comptabilité et caisse.";
  return "Tous les comptes de l'école : parents, enseignants et personnel.";
}

export default function AnnouncementsPage() {
  const { currentSchoolId } = useAuth();
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [targetType, setTargetType] = useState<AnnouncementTargetType>("SCHOOL");
  const [audience, setAudience] = useState<AnnouncementAudience>("ALL");
  const [selectedClassIds, setSelectedClassIds] = useState<string[]>([]);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [status, setStatus] = useState<"idle" | "saving" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<number | null>(null);

  const [classesError, setClassesError] = useState<string | null>(null);

  const [history, setHistory] = useState<AnnouncementHistoryEntry[] | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyNextBefore, setHistoryNextBefore] = useState<string | null>(null);
  const [loadingMoreHistory, setLoadingMoreHistory] = useState(false);

  const loadClasses = useCallback(() => {
    if (!currentSchoolId) return;
    setClassesError(null);
    schoolClasses
      .list(currentSchoolId)
      .then(setClasses)
      .catch((err) => setClassesError(err instanceof ApiError ? err.message : "Une erreur est survenue."));
  }, [currentSchoolId]);

  useEffect(() => {
    loadClasses();
  }, [loadClasses]);

  const loadHistory = useCallback(async () => {
    if (!currentSchoolId) return;
    setHistoryError(null);
    try {
      const page = await announcements.history(currentSchoolId, { limit: 20 });
      setHistory(page.items);
      setHistoryNextBefore(page.next_before);
    } catch (err) {
      setHistoryError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    }
  }, [currentSchoolId]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  async function handleLoadMoreHistory() {
    if (!currentSchoolId || !historyNextBefore) return;
    setLoadingMoreHistory(true);
    try {
      const page = await announcements.history(currentSchoolId, { limit: 20, before: historyNextBefore });
      setHistory((prev) => [...(prev ?? []), ...page.items]);
      setHistoryNextBefore(page.next_before);
    } catch (err) {
      setHistoryError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setLoadingMoreHistory(false);
    }
  }

  function toggleClass(classId: string) {
    setSelectedClassIds((prev) => (prev.includes(classId) ? prev.filter((id) => id !== classId) : [...prev, classId]));
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!currentSchoolId) return;
    setStatus("saving");
    setError(null);
    setResult(null);
    try {
      const response = await announcements.create({
        school_id: currentSchoolId,
        title,
        body,
        target_type: targetType,
        class_ids: targetType === "CLASS" ? selectedClassIds : undefined,
        audience,
      });
      setResult(response.recipient_count);
      setSentTo(AUDIENCE_LABELS[audience].toLowerCase());
      setTitle("");
      setBody("");
      setSelectedClassIds([]);
      setStatus("idle");
      void loadHistory();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
      setStatus("error");
    }
  }

  if (!currentSchoolId) return <TableSkeleton />;
  if (classesError) return <ErrorRetry message={classesError} onRetry={loadClasses} />;
  if (classes === null) return <TableSkeleton />;

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <PageHeader title="Annonces" description="Une annonce arrive dans les notifications des destinataires, et sur leur téléphone s'ils les ont activées." />

      <form onSubmit={handleSubmit}>
        <Card className="flex flex-col gap-4">
          <SectionTitle title="Nouvelle annonce" />
          <TextField label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} required />
          <FieldFrame label="Contenu" hint={`${body.length} / 2000 caractères`}>
            {({ id, describedBy }) => (
              <textarea
                id={id}
                aria-describedby={describedBy}
                value={body}
                onChange={(e) => setBody(e.target.value)}
                maxLength={2000}
                required
                rows={5}
                className={`${controlClass} py-2`}
              />
            )}
          </FieldFrame>
          <div className="grid gap-3 sm:grid-cols-2">
            <SelectField
              label="Destinataires"
              value={audience}
              onChange={(e) => {
                const next = e.target.value as AnnouncementAudience;
                setAudience(next);
                // Le personnel n'est pas rattaché à une classe : annonce à toute l'école.
                if (next === "STAFF") setTargetType("SCHOOL");
              }}
            >
              {(Object.keys(AUDIENCE_LABELS) as AnnouncementAudience[]).map((value) => (
                <option key={value} value={value}>
                  {AUDIENCE_LABELS[value]}
                </option>
              ))}
            </SelectField>
            <SelectField label="Portée" value={targetType} onChange={(e) => setTargetType(e.target.value as AnnouncementTargetType)}>
              <option value="SCHOOL">Toute l&apos;école</option>
              <option value="CLASS" disabled={audience === "STAFF"}>
                Une ou plusieurs classes
              </option>
            </SelectField>
          </div>
          <p data-testid="announcement-audience-hint" className="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-700">
            Recevront cette annonce : {audienceHint(audience, targetType)}
          </p>
          {targetType === "CLASS" && (
            <fieldset className="flex flex-col gap-2">
              <legend className="mb-1 text-sm font-medium text-slate-800">Classes</legend>
              <div className="flex flex-wrap gap-2">
                {classes.map((c) => {
                  const checked = selectedClassIds.includes(c.id);
                  return (
                    <label
                      key={c.id}
                      className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border px-3 text-sm font-medium sm:min-h-10 ${
                        checked ? "border-primary-600 bg-primary-50 text-primary-800" : "border-slate-300 bg-white text-slate-800 hover:bg-slate-50"
                      }`}
                    >
                      <input type="checkbox" checked={checked} onChange={() => toggleClass(c.id)} className="h-4 w-4 accent-primary-600" />
                      {c.name}
                    </label>
                  );
                })}
                {classes.length === 0 && <span className="text-sm text-slate-600">Aucune classe.</span>}
              </div>
            </fieldset>
          )}
          <Button
            type="submit"
            icon="megaphone"
            disabled={status === "saving" || (targetType === "CLASS" && selectedClassIds.length === 0)}
            className="self-start"
          >
            {status === "saving" ? "Publication..." : "Publier"}
          </Button>
          {result !== null && result > 0 && (
            <Alert tone="success">
              Annonce publiée ({sentTo}) — {result} destinataire(s) notifié(s).
            </Alert>
          )}
          {result === 0 && (
            <Alert tone="warning">
              Annonce publiée, mais personne ne l&apos;a reçue : aucun compte EduLinkage ne correspond à ce choix (par exemple, des
              parents qui n&apos;ont pas encore de compte).
            </Alert>
          )}
          {error && <Alert tone="danger">{error}</Alert>}
        </Card>
      </form>

      <section className="flex flex-col gap-3" aria-labelledby="announcements-history">
        <SectionTitle id="announcements-history" title="Historique" />
        {historyError && history === null ? (
          <ErrorRetry message={historyError} onRetry={() => void loadHistory()} />
        ) : history === null ? (
          <TableSkeleton rows={3} />
        ) : history.length === 0 ? (
          <EmptyState icon="megaphone" title="Aucune annonce envoyée." />
        ) : (
          <Card padded={false}>
            <ul className="divide-y divide-slate-200">
              {history.map((entry, index) => (
                <li key={`${entry.created_at}-${index}`} className="flex flex-col gap-1 px-4 py-4">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <Badge tone="info">{TYPE_LABELS[entry.type] ?? entry.type}</Badge>
                    <time dateTime={entry.created_at} className="text-xs text-slate-600">
                      {formatDateTimeFR(entry.created_at)}
                    </time>
                    <span className="text-xs text-slate-600">· {entry.recipient_count} destinataire(s)</span>
                  </div>
                  <p className="break-words font-semibold text-slate-900">{entry.title}</p>
                  <p className="whitespace-pre-line break-words text-sm text-slate-700">{entry.body}</p>
                </li>
              ))}
            </ul>
          </Card>
        )}
        {historyError && history !== null && <Alert tone="danger">{historyError}</Alert>}
        {historyNextBefore && (
          <Button variant="secondary" className="self-center" onClick={() => void handleLoadMoreHistory()} disabled={loadingMoreHistory}>
            {loadingMoreHistory ? "Chargement..." : "Charger plus"}
          </Button>
        )}
      </section>
    </div>
  );
}
