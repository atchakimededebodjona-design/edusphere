// Phase 32, lots 2 et 3 — envoi des saisies de la boîte d'envoi (lib/offline/outbox.ts).
//
// Chaque enregistrement d'appel, de notes ou d'encaissement (caisse ouverte) passe par `saveNow` :
// la saisie est d'abord gardée sur l'appareil, puis envoyée tout de suite si possible. Sans réponse du
// serveur, elle reste en attente et `syncOutbox` la renvoie plus tard (retour du réseau, ouverture de
// l'application, toutes les minutes). Renvoyer est sans risque : présences et notes sont mises à jour
// élève par élève, et la création d'une séance, d'une évaluation ou d'un paiement est protégée par sa
// clé d'idempotence.
//
// Lot 3 — un encaissement envoyé PLUS TARD (`syncOutbox`) porte la mention « hors connexion » (heure
// réelle, reçu provisoire remis au payeur, caisse ouverte à ce moment-là) ; envoyé tout de suite, il
// part comme un encaissement ordinaire.

import { ApiError } from "@/lib/api/client";
import { attendanceRecords, attendanceSessions } from "@/lib/attendance/client";
import { getStoredUserId } from "@/lib/auth/session";
import { payments, type Payment } from "@/lib/fees/client";
import { assessments, results } from "@/lib/grades/client";
import {
  failOnCreatedTarget,
  listOutbox,
  putOutboxEntry,
  reloadOutboxEntry,
  removeOutboxEntry,
  removeSentEntry,
  setOutboxEntryState,
  type OutboxDraft,
  type OutboxEntry,
} from "@/lib/offline/outbox";
import { browserSaysOnline } from "@/lib/offline/status";

type SendOutcome =
  /** `payment` : le paiement enregistré (lot 3), avec son numéro de reçu officiel. */
  | { status: "sent"; targetId: string; payment?: Payment }
  | { status: "unreachable" }
  | { status: "session-expired" }
  /** `createdId` : la séance/évaluation a été créée, seul l'appel ou les notes ont été refusés. */
  | { status: "rejected"; message: string; createdId?: string };

export type SaveOutcome =
  /** Envoyé et accepté par le serveur. */
  | { status: "sent"; targetId: string; payment?: Payment }
  /** Gardé sur l'appareil : partira automatiquement au retour d'internet. */
  | { status: "queued" }
  /** Refusé par le serveur (rien n'est gardé) : `message` explique pourquoi. */
  | { status: "rejected"; message: string }
  /** Ni envoyé, ni gardé (stockage de l'appareil indisponible, navigation privée…). */
  | { status: "unsaved" };

// Refus connus de l'API, traduits pour l'enseignant (les autres gardent le message du serveur).
const KNOWN_REFUSALS: [string, string][] = [
  ["This session is locked", "Cette séance d'appel a été verrouillée : seule l'administration peut la modifier."],
  ["Session date is outside the academic term period", "La date de la séance est en dehors de la période choisie."],
  ["Academic term does not belong", "La période choisie n'appartient pas à l'année scolaire de cette classe."],
  ["Idempotency key already used", "Cette saisie a déjà été envoyée avec d'autres informations : créez-en une nouvelle."],
  ["Student not found in this class", "Un élève de cette saisie n'est plus inscrit dans la classe."],
  ["exceeds the assessment maximum", "Une note dépasse la note maximale de l'évaluation."],
  // Lot 3 — encaissements.
  [
    "The cash session open when this payment was collected is no longer open",
    "La caisse ouverte au moment de l'encaissement a été clôturée entre-temps : le paiement n'a pas été enregistré.",
  ],
  ["An open cash session is required", "Aucune caisse ouverte : le paiement n'a pas été enregistré."],
  ["exceeds the remaining balance", "Le solde de l'élève a changé entre-temps : ce montant dépasse ce qui reste à payer."],
  ["is cancelled and cannot receive payments", "Un des frais de cet encaissement a été annulé entre-temps."],
  ["One or more fees were not found", "Un des frais de cet encaissement n'existe plus."],
  ["Cashiers can only record cash payments", "Un caissier ne peut enregistrer que des paiements en espèces."],
  ["exactly equal the payment amount", "La répartition ne correspond pas au montant reçu."],
  ["Could not record payment", "Le serveur n'a pas pu enregistrer ce paiement."],
];

export function describeRefusal(err: ApiError, kind?: OutboxEntry["kind"]): string {
  const known = KNOWN_REFUSALS.find(([needle]) => err.message.includes(needle));
  if (known) return known[1];
  if (kind === "payment") {
    if (err.status === 403) return "Vous n'êtes plus autorisé à enregistrer ce paiement.";
    if (err.status === 404) return "Élève ou frais introuvable : il a peut-être été retiré entre-temps.";
  }
  if (err.status === 403) return "Vous n'avez plus accès à cette classe ou à cette saisie.";
  if (err.status === 404) return "Classe, élève, séance ou évaluation introuvable : elle a peut-être été retirée entre-temps.";
  if (err.status >= 500) return "Erreur du serveur : la saisie n'a pas été enregistrée. Réessayez plus tard.";
  return /^Request failed with status \d+$/.test(err.message) ? `Saisie refusée par le serveur (erreur ${err.status}).` : err.message;
}

function classify(err: unknown, kind: OutboxEntry["kind"]): SendOutcome {
  if (err instanceof ApiError) {
    // 0 : appareil hors ligne ; 502/503/504 : passerelle sans API ; 429 : trop de requêtes.
    if (err.status === 0 || err.status === 429 || err.status === 502 || err.status === 503 || err.status === 504) {
      return { status: "unreachable" };
    }
    if (err.status === 401) return { status: "session-expired" };
    return { status: "rejected", message: describeRefusal(err, kind) };
  }
  // Aucune réponse (coupure pendant l'envoi) : on ne sait pas si le serveur l'a reçue ; renvoyer
  // est sans risque (voir l'en-tête de ce fichier).
  return { status: "unreachable" };
}

/** `deferred` : envoi après coup (`syncOutbox`), donc encaissement réellement fait sans internet. */
async function sendEntry(entry: OutboxEntry, deferred: boolean): Promise<SendOutcome> {
  let createdId: string | undefined;
  try {
    if (entry.kind === "payment") {
      const payment = await payments.create(deferred ? { ...entry.payment, ...entry.offline } : entry.payment);
      return { status: "sent", targetId: payment.id, payment };
    }
    if (entry.kind === "attendance") {
      const sessionId =
        "id" in entry.session ? entry.session.id : (createdId = (await attendanceSessions.create(entry.session.create)).id);
      if (entry.records.length > 0) await attendanceRecords.submit(sessionId, entry.records);
      return { status: "sent", targetId: sessionId };
    }
    const assessmentId =
      "id" in entry.assessment ? entry.assessment.id : (createdId = (await assessments.create(entry.assessment.create)).id);
    if (entry.results.length > 0) await results.submit(assessmentId, entry.results);
    return { status: "sent", targetId: assessmentId };
  } catch (err) {
    const outcome = classify(err, entry.kind);
    return outcome.status === "rejected" && createdId ? { ...outcome, createdId } : outcome;
  }
}

// Un seul envoi à la fois, y compris entre plusieurs onglets (Web Locks quand le navigateur les
// propose ; sinon, les renvois restent sans risque grâce à l'idempotence).
function withOutboxLock<T>(fn: () => Promise<T>): Promise<T> {
  if (typeof navigator !== "undefined" && "locks" in navigator && navigator.locks?.request) {
    return navigator.locks.request("edulinkage-outbox", fn) as Promise<T>;
  }
  return fn();
}

/** Garde la saisie sur l'appareil, puis tente de l'envoyer tout de suite. */
export async function saveNow(draft: OutboxDraft): Promise<SaveOutcome> {
  const entry = await putOutboxEntry(draft);
  if (!browserSaysOnline()) return entry ? { status: "queued" } : { status: "unsaved" };
  const toSend =
    entry ??
    ({ ...draft, id: draft.key, userId: "", createdAt: "", updatedAt: "", state: "pending", error: null } as OutboxEntry);
  const outcome = await withOutboxLock(() => sendEntry(toSend, false));
  if (outcome.status === "sent") {
    if (entry) await removeSentEntry(entry, outcome.targetId);
    return outcome;
  }
  if (outcome.status === "rejected") {
    // Refus immédiat, affiché à l'écran : rien à garder. Si la séance/évaluation a quand même été
    // créée, l'écran est prévenu pour afficher l'élément réel (une seule ligne, pas de doublon).
    if (entry && outcome.createdId) await removeSentEntry(entry, outcome.createdId);
    else if (entry) await removeOutboxEntry(entry);
    return outcome;
  }
  return entry ? { status: "queued" } : { status: "unsaved" };
}

export type SyncSummary = { sent: number; failed: number };

let running: Promise<SyncSummary> | null = null;

/** Envoie les saisies en attente du compte connecté, les plus anciennes d'abord. */
export function syncOutbox(): Promise<SyncSummary> {
  if (!running) {
    running = withOutboxLock(runSync).finally(() => {
      running = null;
    });
  }
  return running;
}

async function runSync(): Promise<SyncSummary> {
  const summary: SyncSummary = { sent: 0, failed: 0 };
  if (!getStoredUserId() || !browserSaysOnline()) return summary;
  const pending = (await listOutbox()).filter((entry) => entry.state === "pending");
  for (const listed of pending) {
    const entry = await reloadOutboxEntry(listed); // modifiée ou retirée depuis la liste ?
    if (!entry || entry.state !== "pending") continue;
    const outcome = await sendEntry(entry, true);
    if (outcome.status === "sent") {
      await removeSentEntry(entry, outcome.targetId);
      summary.sent += 1;
    } else if (outcome.status === "rejected") {
      // Gardée, avec la raison du refus : l'enseignant décide (réessayer ou supprimer).
      if (outcome.createdId) await failOnCreatedTarget(entry, outcome.createdId, outcome.message);
      else await setOutboxEntryState(entry, "failed", outcome.message);
      summary.failed += 1;
    } else {
      break; // serveur injoignable ou session expirée : on réessaiera plus tard
    }
  }
  return summary;
}

/** Remet en attente une saisie refusée, puis relance l'envoi. */
export async function retryOutboxEntry(entry: OutboxEntry): Promise<void> {
  await setOutboxEntryState(entry, "pending", null);
  await syncOutbox();
}
