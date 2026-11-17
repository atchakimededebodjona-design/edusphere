// Notifications téléphone (Web Push) — 2026-11-17. Ce navigateur s'abonne pour le compte connecté :
// chaque nouvelle annonce s'affiche alors dans la barre de notifications, même EduLinkage fermé
// (sw/service-worker.js). L'API reste seule juge (api: notifications/router.py, notifications/push.py).
//
// - Activation : seulement après un geste de l'utilisateur (« Activer »), jamais d'office.
// - Permission déjà accordée : l'abonnement est renvoyé au serveur à chaque ouverture (les services de
//   notification le renouvellent parfois).
// - Déconnexion : l'abonnement est retiré (poste partagé : plus aucune notification de ce compte).

import { apiFetch } from "@/lib/api/client";

type PushConfig = { enabled: boolean; public_key: string | null };

export type PushState = "unsupported" | "disabled" | "denied" | "default" | "granted";

export function pushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

async function fetchConfig(): Promise<PushConfig | null> {
  try {
    return (await (await apiFetch("/api/v1/push/config")).json()) as PushConfig;
  } catch {
    return null;
  }
}

function keyBytes(base64url: string): Uint8Array {
  const base64 = base64url.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(base64url.length / 4) * 4, "=");
  const raw = window.atob(base64);
  const bytes = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

function sameKey(current: ArrayBuffer | null, expected: Uint8Array): boolean {
  if (!current) return false;
  const bytes = new Uint8Array(current);
  return bytes.length === expected.length && bytes.every((value, index) => value === expected[index]);
}

// S'abonner exige un service worker ACTIF (il vient parfois juste d'être installé) : 5 s d'attente au plus.
async function readyRegistration(): Promise<ServiceWorkerRegistration | null> {
  const existing = await navigator.serviceWorker.getRegistration();
  if (!existing) return null;
  if (existing.active) return existing;
  return Promise.race([
    navigator.serviceWorker.ready,
    new Promise<null>((resolve) => window.setTimeout(() => resolve(null), 5000)),
  ]);
}

async function subscribe(publicKey: string): Promise<boolean> {
  const registration = await readyRegistration();
  if (!registration) return false;
  const serverKey = keyBytes(publicKey);
  let subscription = await registration.pushManager.getSubscription();
  // Clé du serveur changée : l'ancien abonnement ne recevrait plus rien.
  if (subscription && !sameKey(subscription.options.applicationServerKey, serverKey)) {
    await subscription.unsubscribe();
    subscription = null;
  }
  subscription ??= await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: serverKey });
  const json = subscription.toJSON();
  await apiFetch("/api/v1/push/devices", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ endpoint: json.endpoint, keys: { p256dh: json.keys?.p256dh, auth: json.keys?.auth } }),
  });
  return true;
}

export async function pushState(): Promise<PushState> {
  if (!pushSupported()) return "unsupported";
  const config = await fetchConfig();
  if (!config?.enabled) return "disabled";
  return Notification.permission as PushState;
}

/** À appeler sur un geste de l'utilisateur : demande la permission, puis abonne ce navigateur. */
export async function enablePush(): Promise<"granted" | "denied" | "failed"> {
  if (!pushSupported()) return "failed";
  const config = await fetchConfig();
  if (!config?.enabled || !config.public_key) return "failed";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return "denied";
  try {
    return (await subscribe(config.public_key)) ? "granted" : "failed";
  } catch {
    return "failed";
  }
}

/** Permission déjà accordée : l'abonnement est (ré)envoyé au serveur, sans rien demander. */
export async function syncPush(): Promise<void> {
  if (!pushSupported() || Notification.permission !== "granted") return;
  const config = await fetchConfig();
  if (!config?.enabled || !config.public_key) return;
  try {
    await subscribe(config.public_key);
  } catch {
    // hors connexion ou service indisponible : nouvel essai à la prochaine ouverture
  }
}

/** Déconnexion : ce navigateur ne reçoit plus les notifications de ce compte. Ne lève jamais d'erreur. */
export async function forgetPushDevice(): Promise<void> {
  if (!pushSupported()) return;
  try {
    const registration = await readyRegistration();
    const subscription = await registration?.pushManager.getSubscription();
    if (!subscription) return;
    try {
      await apiFetch("/api/v1/push/devices/remove", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ endpoint: subscription.endpoint }),
      });
    } catch {
      // hors connexion : l'abonnement local est retiré quand même, le serveur l'effacera au premier envoi
    }
    await subscription.unsubscribe();
  } catch {
    // ignore
  }
}
