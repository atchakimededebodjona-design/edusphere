// Phase 32, lots 2 et 3 — boîte d'envoi : saisies de l'enseignant (appel, notes) et encaissements en
// espèces du caissier, gardés sur l'appareil jusqu'à leur envoi (voir lib/offline/sync.ts et
// docs/phases/PHASE_32_OFFLINE_PWA.md).
//
// - Une entrée par compte et par CIBLE (`key`) : réenregistrer le même appel ou les mêmes notes
//   remplace l'entrée (la dernière saisie gagne), jamais deux envois concurrents pour la même cible.
//   Chaque encaissement est sa propre cible (`payment:<clé d'idempotence>`).
// - Renvoyée uniquement avec la session de ce compte : l'API reste seule juge (permissions, RLS)
//   au moment de l'envoi.
// - Une séance, une évaluation ou un paiement créé hors connexion porte une clé d'idempotence : le
//   renvoyer plusieurs fois ne crée qu'un seul élément (API, migrations 0009 et 0032).

import type { AttendanceRecordEntry, AttendanceSessionCreate } from "@/lib/attendance/client";
import type { PaymentCreate } from "@/lib/fees/client";
import type { AssessmentCreate, AssessmentResultEntry } from "@/lib/grades/client";
import { getStoredUserId } from "@/lib/auth/session";
import { openOfflineDb, OUTBOX_STORE, requestToPromise, transactionDone } from "@/lib/offline/db";
import { canLockSession } from "@/lib/offline/vault";

export const OUTBOX_CHANGED_EVENT = "edulinkage:outbox-changed";

/** Détail de l'événement : après un envoi réussi, la cible créée côté serveur. */
export type OutboxChange = { sentKey?: string; targetId?: string };

type OutboxBase = {
  /** Clé de stockage : compte + cible. */
  id: string;
  /** Cible : `attendance:<séance>`, `attendance:new:<clé>`, `grades:<évaluation>`, `grades:new:<clé>`,
   * `payment:<clé>`. */
  key: string;
  userId: string;
  createdAt: string;
  updatedAt: string;
  /** pending : à envoyer ; failed : refusée par le serveur, en attente d'une décision. */
  state: "pending" | "failed";
  error: string | null;
  /** Libellé lisible, ex. « Appel du 16/11/2026 — CM1 ». */
  label: string;
};

export type NewSession = AttendanceSessionCreate & { idempotency_key: string };
export type NewAssessment = AssessmentCreate & { idempotency_key: string };

export type AttendanceOutboxEntry = OutboxBase & {
  kind: "attendance";
  classId: string;
  session: { id: string } | { create: NewSession };
  records: AttendanceRecordEntry[];
};

export type GradesOutboxEntry = OutboxBase & {
  kind: "grades";
  classId: string;
  assessment: { id: string } | { create: NewAssessment };
  results: AssessmentResultEntry[];
};

/** Lot 3 — reçu provisoire remis au payeur : tout ce qu'il faut pour le réimprimer sans internet. */
export type ProvisionalReceipt = {
  /** `PROV-` + 10 caractères hexadécimaux, tiré sur l'appareil. */
  number: string;
  collectedAt: string;
  schoolName: string;
  currency: string;
  student: { matricule: string; firstName: string; lastName: string; className: string | null };
  /** Montant API ("15000.00"). */
  amount: string;
  allocations: { name: string; amount: string }[];
  payerName: string | null;
  reference: string | null;
  cashierName: string | null;
};

export type PaymentOutboxEntry = OutboxBase & {
  kind: "payment";
  schoolId: string;
  studentId: string;
  /** Paiement tel qu'il part quand le serveur répond tout de suite (encaissement ordinaire). */
  payment: PaymentCreate & { idempotency_key: string };
  /** Ajouté aux envois DIFFÉRÉS seulement : l'encaissement a réellement été fait sans internet. */
  offline: { offline_collected_at: string; provisional_receipt_number: string; cash_session_id: string };
  receipt: ProvisionalReceipt;
};

export type OutboxEntry = AttendanceOutboxEntry | GradesOutboxEntry | PaymentOutboxEntry;

type Managed = "id" | "userId" | "createdAt" | "updatedAt" | "state" | "error";
export type OutboxDraft =
  | Omit<AttendanceOutboxEntry, Managed>
  | Omit<GradesOutboxEntry, Managed>
  | Omit<PaymentOutboxEntry, Managed>;

export function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return `offline-${crypto.randomUUID()}`;
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return `offline-${Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")}`;
}

export function attendanceKey(session: { id: string } | { create: NewSession }): string {
  return "id" in session ? `attendance:${session.id}` : `attendance:new:${session.create.idempotency_key}`;
}

export function gradesKey(assessment: { id: string } | { create: NewAssessment }): string {
  return "id" in assessment ? `grades:${assessment.id}` : `grades:new:${assessment.create.idempotency_key}`;
}

export function paymentKey(idempotencyKey: string): string {
  return `payment:${idempotencyKey}`;
}

export function isPaymentEntry(entry: OutboxEntry): entry is PaymentOutboxEntry {
  return entry.kind === "payment";
}

function storageId(userId: string, key: string): string {
  return `${userId}|${key}`;
}

function announce(change: OutboxChange = {}): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<OutboxChange>(OUTBOX_CHANGED_EVENT, { detail: change }));
}

async function readById(db: IDBDatabase, id: string): Promise<OutboxEntry | null> {
  const tx = db.transaction(OUTBOX_STORE, "readonly");
  return ((await requestToPromise(tx.objectStore(OUTBOX_STORE).get(id))) as OutboxEntry | undefined) ?? null;
}

/**
 * Enregistre (ou remplace) une saisie du compte connecté. Renvoie l'entrée enregistrée, ou null si
 * le stockage local est indisponible (navigation privée…) : la saisie ne survivrait alors pas à
 * une fermeture, l'appelant doit le dire.
 */
export async function putOutboxEntry(draft: OutboxDraft): Promise<OutboxEntry | null> {
  const userId = getStoredUserId();
  if (!userId) return null;
  try {
    const db = await openOfflineDb();
    if (!db) return null;
    const id = storageId(userId, draft.key);
    const previous = await readById(db, id);
    const now = new Date().toISOString();
    const stored = {
      ...draft,
      id,
      userId,
      createdAt: previous?.createdAt ?? now,
      updatedAt: now,
      state: "pending",
      error: null,
    } as OutboxEntry;
    const tx = db.transaction(OUTBOX_STORE, "readwrite");
    tx.objectStore(OUTBOX_STORE).put(stored);
    await transactionDone(tx);
    announce();
    return stored;
  } catch {
    return null;
  }
}

/** Saisie du compte connecté pour cette cible, ou null. */
export async function findOutboxEntry(key: string): Promise<OutboxEntry | null> {
  const userId = getStoredUserId();
  if (!userId) return null;
  try {
    const db = await openOfflineDb();
    return db ? await readById(db, storageId(userId, key)) : null;
  } catch {
    return null;
  }
}

/** Saisies du compte connecté, les plus anciennes d'abord. */
export async function listOutbox(): Promise<OutboxEntry[]> {
  const userId = getStoredUserId();
  if (!userId) return [];
  try {
    const db = await openOfflineDb();
    if (!db) return [];
    const tx = db.transaction(OUTBOX_STORE, "readonly");
    const entries = (await requestToPromise(tx.objectStore(OUTBOX_STORE).index("userId").getAll(userId))) as OutboxEntry[];
    // Saisies chiffrées d'un compte verrouillé (lib/offline/vault.ts) : jamais listées ni envoyées.
    return entries.filter((entry) => !("sealed" in entry)).sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  } catch {
    return [];
  }
}

/** Relit une entrée telle qu'elle est maintenant (elle a pu être modifiée ou retirée). */
export async function reloadOutboxEntry(entry: OutboxEntry): Promise<OutboxEntry | null> {
  try {
    const db = await openOfflineDb();
    return db ? await readById(db, entry.id) : null;
  } catch {
    return null;
  }
}

/**
 * Retire une entrée envoyée — sauf si elle a été modifiée pendant l'envoi (`updatedAt` différent) :
 * la nouvelle version doit partir à son tour.
 */
export async function removeSentEntry(entry: OutboxEntry, targetId: string): Promise<void> {
  try {
    const db = await openOfflineDb();
    if (!db) return;
    const current = await readById(db, entry.id);
    if (current && current.updatedAt === entry.updatedAt) {
      const tx = db.transaction(OUTBOX_STORE, "readwrite");
      tx.objectStore(OUTBOX_STORE).delete(entry.id);
      await transactionDone(tx);
    }
    announce({ sentKey: entry.key, targetId });
  } catch {
    // ignore
  }
}

export async function removeOutboxEntry(entry: OutboxEntry): Promise<void> {
  try {
    const db = await openOfflineDb();
    if (!db) return;
    const tx = db.transaction(OUTBOX_STORE, "readwrite");
    tx.objectStore(OUTBOX_STORE).delete(entry.id);
    await transactionDone(tx);
    announce();
  } catch {
    // ignore
  }
}

/** Change l'état d'une entrée, sauf si elle a été modifiée entre-temps (la nouvelle version prime). */
export async function setOutboxEntryState(entry: OutboxEntry, state: "pending" | "failed", error: string | null): Promise<void> {
  try {
    const db = await openOfflineDb();
    if (!db) return;
    const current = await readById(db, entry.id);
    if (!current || current.updatedAt !== entry.updatedAt) return;
    const tx = db.transaction(OUTBOX_STORE, "readwrite");
    tx.objectStore(OUTBOX_STORE).put({ ...current, state, error });
    await transactionDone(tx);
    announce();
  } catch {
    // ignore
  }
}

/**
 * La séance (ou l'évaluation) a bien été créée côté serveur, mais l'appel (ou les notes) a été
 * refusé : la saisie refusée vise désormais l'élément réellement créé, pour qu'il n'apparaisse
 * qu'une fois à l'écran et qu'un nouvel essai ne renvoie que l'appel ou les notes.
 */
export async function failOnCreatedTarget(entry: OutboxEntry, targetId: string, error: string): Promise<void> {
  try {
    const db = await openOfflineDb();
    if (!db) return;
    const current = await readById(db, entry.id);
    if (!current || current.updatedAt !== entry.updatedAt) return; // modifiée entre-temps : la nouvelle version prime
    if (current.kind === "payment") return; // un paiement est créé en une fois : jamais à moitié accepté
    const moved: OutboxEntry =
      current.kind === "attendance"
        ? { ...current, key: attendanceKey({ id: targetId }), session: { id: targetId } }
        : { ...current, key: gradesKey({ id: targetId }), assessment: { id: targetId } };
    moved.id = storageId(current.userId, moved.key);
    moved.state = "failed";
    moved.error = error;
    const tx = db.transaction(OUTBOX_STORE, "readwrite");
    tx.objectStore(OUTBOX_STORE).delete(current.id);
    tx.objectStore(OUTBOX_STORE).put(moved);
    await transactionDone(tx);
    announce({ sentKey: entry.key, targetId });
  } catch {
    // ignore
  }
}

/**
 * Déconnexion confirmée : les saisies non envoyées de CE compte sont retirées de l'appareil — sauf
 * les encaissements (lot 3), jamais effacés ainsi : l'argent a été reçu. La déconnexion est déjà
 * bloquée tant qu'il en reste (`confirmLogoutWithUnsentEntries`) ; ceci est une seconde garde. Ils
 * repartiront à la prochaine connexion de ce même compte.
 */
export async function clearOutboxForUser(userId: string): Promise<void> {
  try {
    const db = await openOfflineDb();
    if (!db) return;
    const tx = db.transaction(OUTBOX_STORE, "readwrite");
    const request = tx.objectStore(OUTBOX_STORE).index("userId").openCursor(IDBKeyRange.only(userId));
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) return;
      if ((cursor.value as OutboxEntry).kind !== "payment") cursor.delete();
      cursor.continue();
    };
    await transactionDone(tx);
    announce();
  } catch {
    // ignore
  }
}

/**
 * À appeler avant toute déconnexion : prévient si des saisies ne sont pas encore envoyées.
 * Renvoie false si l'utilisateur préfère rester connecté.
 *
 * Lot 3 — un encaissement en espèces non accepté par le serveur (en attente ou refusé) BLOQUE la
 * déconnexion : l'argent a été reçu, sa seule trace est sur cet appareil.
 *
 * Connexion sans internet — un compte qui peut se reconnecter sans internet est verrouillé, pas
 * effacé (lib/offline/vault.ts) : rien n'est perdu, aucune question à poser.
 */
export async function confirmLogoutWithUnsentEntries(): Promise<boolean> {
  if (await canLockSession()) return true;
  const entries = await listOutbox();
  const cash = entries.filter(isPaymentEntry).length;
  if (cash > 0) {
    window.alert(
      `${
        cash === 1
          ? "1 encaissement fait sans internet n'est pas encore enregistré par le serveur"
          : `${cash} encaissements faits sans internet ne sont pas encore enregistrés par le serveur`
      } (en attente d'envoi ou refusé).\n\nDéconnexion impossible : l'argent a été reçu et sa seule trace est sur cet appareil. Envoyez ou régularisez d'abord ces encaissements depuis la page Caisse.`,
    );
    return false;
  }
  const count = entries.length;
  if (count === 0) return true;
  const message =
    count === 1
      ? "1 saisie (appel ou notes) n'a pas encore été envoyée. Si vous vous déconnectez maintenant, elle sera supprimée de cet appareil."
      : `${count} saisies (appel ou notes) n'ont pas encore été envoyées. Si vous vous déconnectez maintenant, elles seront supprimées de cet appareil.`;
  return window.confirm(`${message}\n\nSe déconnecter quand même ?`);
}
