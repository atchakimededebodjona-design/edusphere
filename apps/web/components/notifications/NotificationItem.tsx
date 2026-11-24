import { Button } from "@/components/ui/Button";
import { Badge, type Tone } from "@/components/ui/Surface";
import type { Notification } from "@/lib/notifications/client";

// Refonte, phase 3 (2026-11-24) — une notification, présentée de la même façon pour l'administration,
// le parent (même page) et l'enseignant : type en pastille, date en français, point bleu tant qu'elle
// n'est pas lue.
const TYPES: Record<string, { label: string; tone: Tone }> = {
  ANNOUNCEMENT: { label: "Annonce", tone: "info" },
  REPORT_CARD_PUBLISHED: { label: "Bulletin", tone: "info" },
  PAYMENT_RECORDED: { label: "Paiement", tone: "success" },
  STUDENT_ABSENT: { label: "Absence", tone: "warning" },
  FEE_OVERDUE: { label: "Paiement en retard", tone: "danger" },
  SUBSCRIPTION_RENEWAL_DUE: { label: "Abonnement à renouveler", tone: "warning" },
  SUBSCRIPTION_EXPIRED: { label: "Abonnement expiré", tone: "danger" },
  SUBSCRIPTION_INVOICE_DUE: { label: "Facture d'abonnement à régler", tone: "warning" },
  SUBSCRIPTION_PAYMENT_CONFIRMED: { label: "Abonnement payé", tone: "success" },
};

/** "2026-11-24T07:33:00Z" -> "24/11/2026 à 07:33" (heure de l'appareil). */
export function formatDateTimeFR(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const day = date.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
  const time = date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  return `${day} à ${time}`;
}

export function NotificationItem({ notification: n, onMarkRead }: { notification: Notification; onMarkRead: (id: string) => void }) {
  const unread = n.read_at === null;
  const type = TYPES[n.type] ?? { label: n.type, tone: "neutral" as Tone };
  return (
    // Téléphone : le bouton passe sous le texte (à droite, il réduisait le texte à une colonne étroite).
    <li
      className={`grid grid-cols-[auto_minmax(0,1fr)] items-start gap-x-3 gap-y-1 px-4 py-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] ${
        unread ? "bg-primary-50/40" : ""
      }`}
      data-testid="notification-item"
    >
      <span
        aria-hidden="true"
        className={`mt-2 h-2.5 w-2.5 shrink-0 rounded-full ${unread ? "bg-primary-600" : "bg-transparent"}`}
      />
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <Badge tone={type.tone}>{type.label}</Badge>
          <time dateTime={n.created_at} className="text-xs text-slate-600">
            {formatDateTimeFR(n.created_at)}
          </time>
          {unread && <span className="sr-only">Non lue</span>}
        </div>
        <p className={`mt-1.5 break-words ${unread ? "font-semibold text-slate-900" : "font-medium text-slate-800"}`}>{n.title}</p>
        <p className="whitespace-pre-line break-words text-sm text-slate-700">{n.body}</p>
      </div>
      {unread && (
        <div className="col-start-2 max-sm:-ml-3 sm:col-start-3 sm:row-start-1">
          <Button variant="quiet" size="sm" onClick={() => onMarkRead(n.id)}>
            Marquer comme lue
          </Button>
        </div>
      )}
    </li>
  );
}
