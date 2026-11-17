// Connexion sans internet (Phase 32, 2026-11-17) — voir docs/phases/PHASE_32_OFFLINE_PWA.md §6.
//
// Un compte qui s'est connecté AVEC internet sur cet appareil peut s'y reconnecter sans internet :
// - à chaque connexion en ligne, une clé de données aléatoire est créée (ou reprise), puis gardée
//   chiffrée par une clé tirée du mot de passe (PBKDF2-SHA-256, 600 000 tours, sel aléatoire). Le
//   mot de passe n'est jamais gardé : seul le bon mot de passe permet de déchiffrer la clé ;
// - « Déconnexion » VERROUILLE au lieu d'effacer : les copies des lectures, les saisies en attente
//   (sauf les encaissements, voir plus bas) et la session sont chiffrées (AES-GCM) avec la clé de
//   données, qui est ensuite retirée de l'appareil ;
// - se reconnecter sans internet déchiffre tout avec le mot de passe et rouvre la même session.
//
// Limites : 7 jours au plus depuis le dernier échange avec le serveur sur cet appareil, 5 essais
// ratés ; un compte désactivé ou un mot de passe changé n'est pris en compte qu'au retour d'internet.
// Les encaissements en attente (lot 3) ne sont jamais chiffrés : un mot de passe changé ailleurs
// rendrait illisible la seule trace d'un argent reçu.
//
// Tout échec est silencieux et sans danger : sans coffre, la déconnexion efface tout comme avant
// et la connexion demande internet.

import { clearStoredTokens, getStoredTokens, getStoredUserId, setStoredTokens, type StoredTokens } from "@/lib/auth/session";
import { openOfflineDb, OUTBOX_STORE, requestToPromise, RESPONSES_STORE, transactionDone, VAULT_STORE } from "@/lib/offline/db";

const PBKDF2_ITERATIONS = 600_000;
export const OFFLINE_LOGIN_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;
export const OFFLINE_LOGIN_MAX_ATTEMPTS = 5;
const SERVER_CONTACT_PREFIX = "edulinkage.server-contact.";
const SERVER_CONTACT_THROTTLE_MS = 60_000;

type Sealed = { iv: Uint8Array; data: ArrayBuffer };

type VaultRecord = {
  userId: string;
  /** En minuscules : la connexion sans internet retrouve le coffre par l'adresse saisie. */
  email: string;
  salt: Uint8Array;
  iterations: number;
  wrappedKey: ArrayBuffer;
  wrapIv: Uint8Array;
  /** Clé des données, présente seulement quand la session est ouverte (jamais exportable). */
  key: CryptoKey | null;
  locked: boolean;
  sealedTokens: Sealed | null;
  lockedAt: string | null;
  /** Dernier échange réussi avec le serveur sur cet appareil (limite des 7 jours). */
  lastServerContactAt: string;
  failedAttempts: number;
};

type PlainResponse = { key: string; userId: string; path: string; savedAt: string; contentType: string | null; body: ArrayBuffer };
type SealedResponse = { key: string; userId: string; savedAt: string; sealed: { meta: Sealed; body: Sealed } };
type PlainOutbox = { id: string; userId: string; kind?: string };
type SealedOutbox = { id: string; userId: string; sealed: Sealed };

export type OfflineAccount = { userId: string; email: string; lockedAt: string | null; usableUntil: string; blocked: boolean };

export type UnlockResult =
  | { status: "unlocked" }
  /** Aucun compte verrouillé pour cette adresse sur cet appareil. */
  | { status: "unknown" }
  | { status: "expired" }
  | { status: "blocked" }
  | { status: "wrong-password"; remaining: number }
  /** Stockage ou chiffrement indisponible sur cet appareil. */
  | { status: "unavailable" };

const encoder = new TextEncoder();
const decoder = new TextDecoder();

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

function randomBytes(length: number): Uint8Array {
  const bytes = new Uint8Array(length);
  crypto.getRandomValues(bytes);
  return bytes;
}

function cryptoAvailable(): boolean {
  return typeof crypto !== "undefined" && typeof crypto.subtle !== "undefined";
}

async function deriveWrappingKey(password: string, salt: Uint8Array, iterations: number): Promise<CryptoKey> {
  const material = await crypto.subtle.importKey("raw", encoder.encode(password), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey(
    { name: "PBKDF2", hash: "SHA-256", salt: salt as BufferSource, iterations },
    material,
    { name: "AES-GCM", length: 256 },
    false,
    ["wrapKey", "unwrapKey"],
  );
}

/** Clé des données déchiffrée avec le mot de passe ; lève une erreur si le mot de passe est faux. */
async function unwrapDataKey(vault: VaultRecord, password: string): Promise<CryptoKey> {
  const wrapping = await deriveWrappingKey(password, vault.salt, vault.iterations);
  return crypto.subtle.unwrapKey(
    "raw",
    vault.wrappedKey,
    wrapping,
    { name: "AES-GCM", iv: vault.wrapIv as BufferSource },
    { name: "AES-GCM" },
    false,
    ["encrypt", "decrypt"],
  );
}

async function seal(key: CryptoKey, data: BufferSource): Promise<Sealed> {
  const iv = randomBytes(12);
  return { iv, data: await crypto.subtle.encrypt({ name: "AES-GCM", iv: iv as BufferSource }, key, data) };
}

async function open(key: CryptoKey, sealed: Sealed): Promise<ArrayBuffer> {
  return crypto.subtle.decrypt({ name: "AES-GCM", iv: sealed.iv as BufferSource }, key, sealed.data);
}

async function getVault(db: IDBDatabase, userId: string): Promise<VaultRecord | null> {
  const tx = db.transaction(VAULT_STORE, "readonly");
  return ((await requestToPromise(tx.objectStore(VAULT_STORE).get(userId))) as VaultRecord | undefined) ?? null;
}

async function putVault(db: IDBDatabase, vault: VaultRecord): Promise<void> {
  const tx = db.transaction(VAULT_STORE, "readwrite");
  tx.objectStore(VAULT_STORE).put(vault);
  await transactionDone(tx);
}

async function allForUser<T>(db: IDBDatabase, store: string, userId: string): Promise<T[]> {
  const tx = db.transaction(store, "readonly");
  return (await requestToPromise(tx.objectStore(store).index("userId").getAll(userId))) as T[];
}

function isSealed(value: object): boolean {
  return "sealed" in value;
}

// --- Dernier échange avec le serveur (limite des 7 jours) -----------------------------------------

let lastContactMark = 0;

/** Appelée à chaque réponse du serveur (lib/api/client.ts). Ne lève jamais d'erreur. */
export function markServerContact(): void {
  const now = Date.now();
  if (now - lastContactMark < SERVER_CONTACT_THROTTLE_MS) return;
  const userId = getStoredUserId();
  if (!userId) return;
  lastContactMark = now;
  try {
    window.localStorage.setItem(`${SERVER_CONTACT_PREFIX}${userId}`, new Date(now).toISOString());
  } catch {
    // ignore
  }
}

function readServerContact(userId: string): string | null {
  try {
    return window.localStorage.getItem(`${SERVER_CONTACT_PREFIX}${userId}`);
  } catch {
    return null;
  }
}

function latest(a: string, b: string | null): string {
  return b && Date.parse(b) > Date.parse(a) ? b : a;
}

// --- Chiffrement et déchiffrement des données d'un compte ---------------------------------------

async function unsealUserData(db: IDBDatabase, userId: string, key: CryptoKey): Promise<void> {
  const allResponses = await allForUser<PlainResponse | SealedResponse>(db, RESPONSES_STORE, userId);
  const responses = allResponses.filter(isSealed) as SealedResponse[];
  const outbox = (await allForUser<PlainOutbox | SealedOutbox>(db, OUTBOX_STORE, userId)).filter(isSealed) as SealedOutbox[];
  const existingResponses = new Set(allResponses.filter((r) => !isSealed(r)).map((r) => r.key));
  const plainResponses: PlainResponse[] = [];
  for (const entry of responses) {
    try {
      const meta = JSON.parse(decoder.decode(await open(key, entry.sealed.meta))) as { path: string; contentType: string | null };
      const restoredKey = `${userId} ${meta.path}`;
      if (existingResponses.has(restoredKey)) continue; // copie plus récente déjà présente
      plainResponses.push({ key: restoredKey, userId, path: meta.path, savedAt: entry.savedAt, contentType: meta.contentType, body: await open(key, entry.sealed.body) });
    } catch {
      // copie illisible : abandonnée
    }
  }
  // Seules les saisies effectivement déchiffrées remplacent leur version chiffrée ; une saisie
  // illisible reste chiffrée (jamais supprimée en silence).
  const restoredOutbox: { sealedId: string; plain: PlainOutbox }[] = [];
  for (const entry of outbox) {
    try {
      restoredOutbox.push({ sealedId: entry.id, plain: JSON.parse(decoder.decode(await open(key, entry.sealed))) as PlainOutbox });
    } catch {
      // illisible
    }
  }
  const tx = db.transaction([RESPONSES_STORE, OUTBOX_STORE], "readwrite");
  const responsesStore = tx.objectStore(RESPONSES_STORE);
  for (const entry of responses) responsesStore.delete(entry.key);
  for (const entry of plainResponses) responsesStore.put(entry);
  const outboxStore = tx.objectStore(OUTBOX_STORE);
  for (const { sealedId, plain } of restoredOutbox) {
    outboxStore.delete(sealedId);
    outboxStore.put(plain);
  }
  await transactionDone(tx);
}

async function deleteUserData(db: IDBDatabase, userId: string, onlySealed: boolean): Promise<void> {
  const responses = await allForUser<PlainResponse | SealedResponse>(db, RESPONSES_STORE, userId);
  const outbox = await allForUser<PlainOutbox | SealedOutbox>(db, OUTBOX_STORE, userId);
  const tx = db.transaction([RESPONSES_STORE, OUTBOX_STORE], "readwrite");
  for (const entry of responses) if (!onlySealed || isSealed(entry)) tx.objectStore(RESPONSES_STORE).delete(entry.key);
  for (const entry of outbox) {
    // Jamais un encaissement (lot 3) : l'argent a été reçu.
    if ((entry as PlainOutbox).kind === "payment") continue;
    if (!onlySealed || isSealed(entry)) tx.objectStore(OUTBOX_STORE).delete(entry.id);
  }
  await transactionDone(tx);
}

// --- API du module -------------------------------------------------------------------------------

/**
 * Après une connexion EN LIGNE réussie : prépare (ou reprend) la connexion sans internet de ce
 * compte sur cet appareil. Si le compte était verrouillé, ses données sont déchiffrées et reprises ;
 * si son mot de passe a changé depuis, elles sont illisibles et effacées. Ne lève jamais d'erreur.
 */
export async function enableOfflineLogin(userId: string, email: string, password: string): Promise<void> {
  if (!cryptoAvailable()) return;
  try {
    const db = await openOfflineDb();
    if (!db) return;
    const now = new Date().toISOString();
    const existing = await getVault(db, userId);
    if (existing) {
      const key = await unwrapDataKey(existing, password).catch(() => null);
      if (key) {
        if (existing.locked) await unsealUserData(db, userId, key);
        await putVault(db, {
          ...existing,
          email: normalizeEmail(email),
          key,
          locked: false,
          sealedTokens: null,
          lockedAt: null,
          lastServerContactAt: now,
          failedAttempts: 0,
        });
        return;
      }
      // Mot de passe changé depuis le verrouillage : l'ancien contenu chiffré est illisible.
      await deleteUserData(db, userId, true);
    }
    const salt = randomBytes(16);
    const wrapping = await deriveWrappingKey(password, salt, PBKDF2_ITERATIONS);
    const exportable = await crypto.subtle.generateKey({ name: "AES-GCM", length: 256 }, true, ["encrypt", "decrypt"]);
    const wrapIv = randomBytes(12);
    const wrappedKey = await crypto.subtle.wrapKey("raw", exportable, wrapping, { name: "AES-GCM", iv: wrapIv as BufferSource });
    const key = await crypto.subtle.importKey("raw", await crypto.subtle.exportKey("raw", exportable), "AES-GCM", false, [
      "encrypt",
      "decrypt",
    ]);
    await putVault(db, {
      userId,
      email: normalizeEmail(email),
      salt,
      iterations: PBKDF2_ITERATIONS,
      wrappedKey,
      wrapIv,
      key,
      locked: false,
      sealedTokens: null,
      lockedAt: null,
      lastServerContactAt: now,
      failedAttempts: 0,
    });
  } catch {
    // Connexion sans internet indisponible sur cet appareil : la connexion en ligne reste.
  }
}

/** Vrai si la session ouverte peut être verrouillée (coffre prêt pour ce compte). */
export async function canLockSession(): Promise<boolean> {
  const userId = getStoredUserId();
  if (!userId || !cryptoAvailable()) return false;
  try {
    const db = await openOfflineDb();
    const vault = db ? await getVault(db, userId) : null;
    return Boolean(vault?.key);
  } catch {
    return false;
  }
}

/**
 * « Déconnexion » d'un compte qui peut se reconnecter sans internet : tout ce que ce compte a sur
 * l'appareil est chiffré, la clé des données retirée, la session fermée sur l'appareil (mais pas
 * révoquée sur le serveur : elle sera rouverte par le mot de passe). Renvoie false si ce n'est pas
 * possible : l'appelant fait alors la déconnexion complète habituelle.
 */
export async function lockSession(): Promise<boolean> {
  const userId = getStoredUserId();
  const tokens = getStoredTokens();
  if (!userId || !tokens || !cryptoAvailable()) return false;
  try {
    const db = await openOfflineDb();
    if (!db) return false;
    const vault = await getVault(db, userId);
    const key = vault?.key;
    if (!vault || !key) return false;

    const responses = (await allForUser<PlainResponse | SealedResponse>(db, RESPONSES_STORE, userId)).filter(
      (entry) => !isSealed(entry),
    ) as PlainResponse[];
    const outbox = (await allForUser<PlainOutbox | SealedOutbox>(db, OUTBOX_STORE, userId)).filter(
      (entry) => !isSealed(entry) && (entry as PlainOutbox).kind !== "payment",
    ) as PlainOutbox[];

    const sealedResponses: SealedResponse[] = [];
    for (const entry of responses) {
      sealedResponses.push({
        key: `${userId} #${crypto.randomUUID()}`,
        userId,
        savedAt: entry.savedAt,
        sealed: {
          meta: await seal(key, encoder.encode(JSON.stringify({ path: entry.path, contentType: entry.contentType }))),
          body: await seal(key, entry.body),
        },
      });
    }
    const sealedOutbox: SealedOutbox[] = [];
    for (const entry of outbox) {
      sealedOutbox.push({ id: `${userId}|sealed:${crypto.randomUUID()}`, userId, sealed: await seal(key, encoder.encode(JSON.stringify(entry))) });
    }
    const sealedTokens = await seal(key, encoder.encode(JSON.stringify(tokens)));

    // Une seule transaction : tout est chiffré, ou rien ne change.
    const tx = db.transaction([RESPONSES_STORE, OUTBOX_STORE, VAULT_STORE], "readwrite");
    const responsesStore = tx.objectStore(RESPONSES_STORE);
    for (const entry of responses) responsesStore.delete(entry.key);
    for (const entry of sealedResponses) responsesStore.put(entry);
    const outboxStore = tx.objectStore(OUTBOX_STORE);
    for (const entry of outbox) outboxStore.delete(entry.id);
    for (const entry of sealedOutbox) outboxStore.put(entry);
    tx.objectStore(VAULT_STORE).put({
      ...vault,
      key: null,
      locked: true,
      sealedTokens,
      lockedAt: new Date().toISOString(),
      lastServerContactAt: latest(vault.lastServerContactAt, readServerContact(userId)),
    } satisfies VaultRecord);
    await transactionDone(tx);
    clearStoredTokens();
    return true;
  } catch {
    return false;
  }
}

/** Vrai si le compte de la session stockée est verrouillé (verrouillage interrompu : il l'emporte). */
export async function isStoredSessionLocked(): Promise<boolean> {
  const userId = getStoredUserId();
  if (!userId) return false;
  try {
    const db = await openOfflineDb();
    const vault = db ? await getVault(db, userId) : null;
    return Boolean(vault?.locked);
  } catch {
    return false;
  }
}

/** Connexion SANS internet : déchiffre la session et les données du compte avec le mot de passe. */
export async function unlockOffline(email: string, password: string): Promise<UnlockResult> {
  if (!cryptoAvailable()) return { status: "unavailable" };
  try {
    const db = await openOfflineDb();
    if (!db) return { status: "unavailable" };
    const tx = db.transaction(VAULT_STORE, "readonly");
    const candidates = (await requestToPromise(tx.objectStore(VAULT_STORE).index("email").getAll(normalizeEmail(email)))) as VaultRecord[];
    const vault = candidates
      .filter((v) => v.locked && v.sealedTokens)
      .sort((a, b) => Date.parse(b.lastServerContactAt) - Date.parse(a.lastServerContactAt))[0];
    if (!vault || !vault.sealedTokens) return { status: "unknown" };
    if (vault.failedAttempts >= OFFLINE_LOGIN_MAX_ATTEMPTS) return { status: "blocked" };
    if (Date.now() - Date.parse(vault.lastServerContactAt) > OFFLINE_LOGIN_MAX_AGE_MS) return { status: "expired" };

    const key = await unwrapDataKey(vault, password).catch(() => null);
    if (!key) {
      const failedAttempts = vault.failedAttempts + 1;
      await putVault(db, { ...vault, failedAttempts });
      return failedAttempts >= OFFLINE_LOGIN_MAX_ATTEMPTS
        ? { status: "blocked" }
        : { status: "wrong-password", remaining: OFFLINE_LOGIN_MAX_ATTEMPTS - failedAttempts };
    }
    const tokens = JSON.parse(decoder.decode(await open(key, vault.sealedTokens))) as StoredTokens;
    await unsealUserData(db, vault.userId, key);
    await putVault(db, { ...vault, key, locked: false, sealedTokens: null, lockedAt: null, failedAttempts: 0 });
    setStoredTokens(tokens);
    return { status: "unlocked" };
  } catch {
    return { status: "unavailable" };
  }
}

/** Comptes verrouillés sur cet appareil (affichés sur la page de connexion). */
export async function listOfflineAccounts(): Promise<OfflineAccount[]> {
  try {
    const db = await openOfflineDb();
    if (!db) return [];
    const tx = db.transaction(VAULT_STORE, "readonly");
    const vaults = (await requestToPromise(tx.objectStore(VAULT_STORE).getAll())) as VaultRecord[];
    return vaults
      .filter((v) => v.locked)
      .map((v) => ({
        userId: v.userId,
        email: v.email,
        lockedAt: v.lockedAt,
        usableUntil: new Date(Date.parse(v.lastServerContactAt) + OFFLINE_LOGIN_MAX_AGE_MS).toISOString(),
        blocked: v.failedAttempts >= OFFLINE_LOGIN_MAX_ATTEMPTS,
      }));
  } catch {
    return [];
  }
}

/**
 * Efface de cet appareil un compte et tout ce qu'il y a gardé (coffre, copies, saisies en attente),
 * sauf ses encaissements en attente, qui repartiront à sa prochaine connexion avec internet.
 */
export async function forgetAccount(userId: string): Promise<void> {
  try {
    const db = await openOfflineDb();
    if (!db) return;
    await deleteUserData(db, userId, false);
    const tx = db.transaction(VAULT_STORE, "readwrite");
    tx.objectStore(VAULT_STORE).delete(userId);
    await transactionDone(tx);
    window.localStorage.removeItem(`${SERVER_CONTACT_PREFIX}${userId}`);
  } catch {
    // ignore
  }
}
