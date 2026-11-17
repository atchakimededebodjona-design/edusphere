// Phase 32 — base IndexedDB unique de l'application, ouverte une seule fois :
// - `responses` (lot 1) : copies des lectures de l'API, voir lib/offline/responseCache.ts ;
// - `outbox` (lot 2) : saisies faites hors connexion, en attente d'envoi, voir lib/offline/outbox.ts ;
// - `vault` (connexion sans internet, version 3) : un coffre par compte, voir lib/offline/vault.ts.
// Tout échec (navigation privée, stockage bloqué) donne `null` : l'appelant se passe alors du
// stockage local, sans jamais lever d'erreur.

const DB_NAME = "edulinkage-offline";
const DB_VERSION = 3;
export const RESPONSES_STORE = "responses";
export const OUTBOX_STORE = "outbox";
export const VAULT_STORE = "vault";

let dbPromise: Promise<IDBDatabase | null> | null = null;

export function openOfflineDb(): Promise<IDBDatabase | null> {
  if (typeof indexedDB === "undefined") return Promise.resolve(null);
  if (dbPromise) return dbPromise;
  dbPromise = new Promise<IDBDatabase | null>((resolve) => {
    try {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(RESPONSES_STORE)) {
          const store = db.createObjectStore(RESPONSES_STORE, { keyPath: "key" });
          store.createIndex("userId", "userId");
          store.createIndex("savedAt", "savedAt");
        }
        if (!db.objectStoreNames.contains(OUTBOX_STORE)) {
          const store = db.createObjectStore(OUTBOX_STORE, { keyPath: "id" });
          store.createIndex("userId", "userId");
        }
        if (!db.objectStoreNames.contains(VAULT_STORE)) {
          const store = db.createObjectStore(VAULT_STORE, { keyPath: "userId" });
          store.createIndex("email", "email");
        }
      };
      request.onsuccess = () => {
        const db = request.result;
        db.onversionchange = () => {
          db.close();
          dbPromise = null;
        };
        resolve(db);
      };
      request.onerror = () => resolve(null);
      request.onblocked = () => resolve(null);
    } catch {
      resolve(null);
    }
  }).then((db) => {
    if (!db) dbPromise = null;
    return db;
  });
  return dbPromise;
}

export function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export function transactionDone(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}
