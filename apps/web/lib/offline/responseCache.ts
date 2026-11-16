// Phase 32, lot 1 — copie locale des réponses de LECTURE de l'API, pour consulter hors connexion ce
// qui a déjà été vu avec internet (voir docs/phases/PHASE_32_OFFLINE_PWA.md).
//
// - Rangée par compte (`userId`, lu dans le jeton) : un compte ne lit jamais la copie d'un autre.
// - Effacée entièrement à la déconnexion, et celle des autres comptes à chaque connexion (poste
//   partagé d'une école) — voir lib/auth/AuthProvider.tsx.
// - Jamais une source d'autorité : servie seulement quand l'API est injoignable, et signalée à
//   l'écran (voir lib/offline/status.ts).
// - Tout échec d'IndexedDB (navigation privée, stockage plein ou bloqué) est silencieux :
//   l'application se comporte alors exactement comme avant, sans copie locale.

const DB_NAME = "edulinkage-offline";
const DB_VERSION = 1;
const STORE = "responses";
const MAX_BODY_BYTES = 5 * 1024 * 1024;
const MAX_ENTRIES = 600;

type StoredEntry = {
  key: string;
  userId: string;
  path: string;
  savedAt: string;
  contentType: string | null;
  body: ArrayBuffer;
};

export type CachedResponse = { response: Response; savedAt: string };

let dbPromise: Promise<IDBDatabase | null> | null = null;
let writesSincePrune = 0;

function entryKey(userId: string, path: string): string {
  return `${userId} ${path}`;
}

function openDb(): Promise<IDBDatabase | null> {
  if (typeof indexedDB === "undefined") return Promise.resolve(null);
  if (dbPromise) return dbPromise;
  dbPromise = new Promise<IDBDatabase | null>((resolve) => {
    try {
      const request = indexedDB.open(DB_NAME, DB_VERSION);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains(STORE)) {
          const store = db.createObjectStore(STORE, { keyPath: "key" });
          store.createIndex("userId", "userId");
          store.createIndex("savedAt", "savedAt");
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

function requestToPromise<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function transactionDone(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error);
  });
}

/** Garde une copie d'une réponse réussie. Ne lève jamais d'erreur. */
export async function storeResponse(userId: string, path: string, response: Response): Promise<void> {
  try {
    const declared = Number(response.headers.get("Content-Length") ?? "0");
    if (declared > MAX_BODY_BYTES) return;
    const body = await response.arrayBuffer();
    if (body.byteLength > MAX_BODY_BYTES) return;
    const db = await openDb();
    if (!db) return;
    const tx = db.transaction(STORE, "readwrite");
    const entry: StoredEntry = {
      key: entryKey(userId, path),
      userId,
      path,
      savedAt: new Date().toISOString(),
      contentType: response.headers.get("Content-Type"),
      body,
    };
    tx.objectStore(STORE).put(entry);
    await transactionDone(tx);
    writesSincePrune += 1;
    if (writesSincePrune >= 50) {
      writesSincePrune = 0;
      await pruneOldest(db);
    }
  } catch {
    // Copie locale impossible : sans conséquence pour l'utilisation en ligne.
  }
}

/** Copie locale de `path` pour ce compte, ou null. Ne lève jamais d'erreur. */
export async function readCachedResponse(userId: string, path: string): Promise<CachedResponse | null> {
  try {
    const db = await openDb();
    if (!db) return null;
    const tx = db.transaction(STORE, "readonly");
    const entry = (await requestToPromise(tx.objectStore(STORE).get(entryKey(userId, path)))) as StoredEntry | undefined;
    if (!entry || entry.userId !== userId) return null;
    const headers = new Headers();
    if (entry.contentType) headers.set("Content-Type", entry.contentType);
    return { response: new Response(entry.body, { status: 200, headers }), savedAt: entry.savedAt };
  } catch {
    return null;
  }
}

async function deleteMatching(predicate: (entry: StoredEntry) => boolean): Promise<void> {
  const db = await openDb();
  if (!db) return;
  const tx = db.transaction(STORE, "readwrite");
  const request = tx.objectStore(STORE).openCursor();
  request.onsuccess = () => {
    const cursor = request.result;
    if (!cursor) return;
    if (predicate(cursor.value as StoredEntry)) cursor.delete();
    cursor.continue();
  };
  await transactionDone(tx);
}

/** Efface toutes les copies locales (déconnexion). Ne lève jamais d'erreur. */
export async function clearAllCachedResponses(): Promise<void> {
  try {
    const db = await openDb();
    if (!db) return;
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).clear();
    await transactionDone(tx);
  } catch {
    // ignore
  }
}

/** Efface les copies de tous les AUTRES comptes (connexion sur un poste partagé). */
export async function clearCachedResponsesExcept(userId: string): Promise<void> {
  try {
    await deleteMatching((entry) => entry.userId !== userId);
  } catch {
    // ignore
  }
}

async function pruneOldest(db: IDBDatabase): Promise<void> {
  const tx = db.transaction(STORE, "readwrite");
  const store = tx.objectStore(STORE);
  const count = await requestToPromise(store.count());
  let excess = count - MAX_ENTRIES;
  if (excess > 0) {
    const request = store.index("savedAt").openCursor();
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor || excess <= 0) return;
      cursor.delete();
      excess -= 1;
      cursor.continue();
    };
  }
  await transactionDone(tx);
}
