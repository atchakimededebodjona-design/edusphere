"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api/client";
import { hasTeacherRole } from "@/lib/auth/roles";
import { useAuth } from "@/lib/auth/useAuth";
import type { OutboxEntry } from "@/lib/offline/outbox";
import { announceDataSource, DATA_SOURCE_EVENT, type DataSourceDetail } from "@/lib/offline/status";
import { syncOutbox } from "@/lib/offline/sync";
import { useOutbox } from "@/lib/offline/useOutbox";
import { enablePush, pushState, syncPush, type PushState } from "@/lib/push/client";

// Phase 32, lot 1 — application installable et consultable hors connexion (voir
// docs/phases/PHASE_32_OFFLINE_PWA.md). Trois bandeaux discrets en bas d'écran :
// - « Hors connexion » : les informations affichées sont la copie gardée sur l'appareil, datée ;
// - « Installer EduLinkage » : proposé aux comptes connectés quand le navigateur le permet ;
// - « Nouvelle version » : après une mise à jour du site, recharger quand on le souhaite (jamais
//   imposé : une saisie en cours ne doit pas être perdue).

const INSTALL_DISMISSED_KEY = "edulinkage.install-dismissed-at";
const INSTALL_REMIND_AFTER_MS = 30 * 24 * 60 * 60 * 1000;
const REACHABILITY_PROBE_MS = 20_000;

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
};

function formatSavedAt(iso: string): string {
  const date = new Date(iso);
  const day = date.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
  const time = date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  return `${day} à ${time}`;
}

// Retour à une version du site SANS service worker (image de secours) : le navigateur garderait
// sinon l'ancien service worker et continuerait de servir la version gardée sur l'appareil.
// Seulement si le serveur répond explicitement 404 pour /sw.js — jamais sur une simple coupure.
async function removeServiceWorkerIfWithdrawn(): Promise<void> {
  try {
    const response = await fetch("/sw.js", { cache: "no-store" });
    if (response.status !== 404) return;
    const registrations = await navigator.serviceWorker.getRegistrations();
    await Promise.all(registrations.map((registration) => registration.unregister()));
    const names = await caches.keys();
    await Promise.all(names.filter((name) => name.startsWith("edulinkage-")).map((name) => caches.delete(name)));
    if (registrations.length > 0) window.location.reload();
  } catch {
    // hors connexion : on ne retire rien
  }
}

function useServiceWorker(enabled: boolean): boolean {
  const [updateReady, setUpdateReady] = useState(false);
  useEffect(() => {
    // Jamais en développement (ni donc dans les tests e2e, lancés avec `pnpm dev`) : public/sw.js
    // n'existe qu'après `next build`.
    if (process.env.NODE_ENV !== "production" || !("serviceWorker" in navigator)) return;
    // Enregistré après une connexion ; ensuite, vérifié à chaque ouverture (mises à jour, retrait).
    if (!enabled && !navigator.serviceWorker.controller) return;
    const hadController = Boolean(navigator.serviceWorker.controller);
    const onControllerChange = () => {
      if (hadController) setUpdateReady(true);
    };
    navigator.serviceWorker.addEventListener("controllerchange", onControllerChange);
    // `update()` explicite : un enregistrement déjà présent ne recontacte pas le serveur, et un
    // /sw.js retiré (404) passerait inaperçu. Sans service worker, le site fonctionne en ligne
    // exactement comme avant.
    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .then((registration) => registration.update())
      .catch(() => void removeServiceWorkerIfWithdrawn());
    // Demande au navigateur de ne pas effacer de lui-même les données gardées (accordé en général
    // aux applications installées).
    void navigator.storage?.persist?.().catch(() => false);
    return () => navigator.serviceWorker.removeEventListener("controllerchange", onControllerChange);
  }, [enabled]);
  return updateReady;
}

function useInstallPrompt(): { prompt: BeforeInstallPromptEvent | null; clear: () => void } {
  const [prompt, setPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  useEffect(() => {
    const onPrompt = (event: Event) => {
      event.preventDefault();
      setPrompt(event as BeforeInstallPromptEvent);
    };
    const onInstalled = () => setPrompt(null);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);
  return { prompt, clear: () => setPrompt(null) };
}

function installRecentlyDismissed(): boolean {
  try {
    const at = Number(window.localStorage.getItem(INSTALL_DISMISSED_KEY) ?? "0");
    return Date.now() - at < INSTALL_REMIND_AFTER_MS;
  } catch {
    return false;
  }
}

// 2026-11-17 — notifications téléphone des annonces (lib/push/client.ts). Proposées une fois par
// appareil (jamais demandées d'office) ; « Plus tard » les repropose 7 jours après.
const PUSH_DISMISSED_KEY = "edulinkage.push-dismissed-at";
const PUSH_REMIND_AFTER_MS = 7 * 24 * 60 * 60 * 1000;

function pushRecentlyDismissed(): boolean {
  try {
    const at = Number(window.localStorage.getItem(PUSH_DISMISSED_KEY) ?? "0");
    return Date.now() - at < PUSH_REMIND_AFTER_MS;
  } catch {
    return false;
  }
}

function usePushOffer(authenticated: boolean) {
  const [state, setState] = useState<PushState | null>(null);
  const [hidden, setHidden] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setHidden(pushRecentlyDismissed());
  }, []);

  useEffect(() => {
    if (!authenticated) {
      setState(null);
      return;
    }
    let cancelled = false;
    void pushState().then((current) => {
      if (cancelled) return;
      setState(current);
      // Déjà accepté sur cet appareil : l'abonnement est renvoyé au serveur, sans rien demander.
      if (current === "granted") void syncPush();
    });
    return () => {
      cancelled = true;
    };
  }, [authenticated]);

  useEffect(() => {
    if (!message) return;
    const id = window.setTimeout(() => setMessage(null), 8000);
    return () => window.clearTimeout(id);
  }, [message]);

  async function enable() {
    setBusy(true);
    try {
      const result = await enablePush();
      if (result === "granted") {
        setState("granted");
        setMessage("Notifications activées : les nouvelles annonces s'afficheront sur cet appareil.");
      } else if (result === "denied") {
        setState("denied");
        setMessage("Notifications refusées. Pour les recevoir, autorisez-les dans les réglages du navigateur pour EduLinkage.");
      } else {
        setMessage("Activation impossible pour le moment. Réessayez plus tard.");
      }
    } finally {
      setBusy(false);
    }
  }

  function later() {
    try {
      window.localStorage.setItem(PUSH_DISMISSED_KEY, String(Date.now()));
    } catch {
      // ignore
    }
    setHidden(true);
  }

  return { offer: authenticated && state === "default" && !hidden, message, busy, enable, later };
}

function useOfflineState() {
  const pathname = usePathname();
  const [browserOnline, setBrowserOnline] = useState(true);
  const [apiUnreachable, setApiUnreachable] = useState(false);
  const [oldestCopy, setOldestCopy] = useState<string | null>(null);
  const [reconnected, setReconnected] = useState(false);

  // Nouvelle page : ses données sont rechargées, l'état « copie affichée » repart de zéro.
  useEffect(() => {
    setOldestCopy(null);
    setReconnected(false);
  }, [pathname]);

  useEffect(() => {
    setBrowserOnline(navigator.onLine !== false);
    // Réseau revenu : supposé joignable jusqu'à la prochaine requête (qui le confirmera ou non).
    const onOnline = () => {
      setBrowserOnline(true);
      setApiUnreachable(false);
    };
    const onOffline = () => setBrowserOnline(false);
    const onDataSource = (event: Event) => {
      const detail = (event as CustomEvent<DataSourceDetail>).detail;
      if (!detail) return;
      if (detail.source === "network") {
        setApiUnreachable(false);
        return;
      }
      setApiUnreachable(true);
      setReconnected(false);
      if (detail.source === "copy") {
        const savedAt = detail.savedAt;
        setOldestCopy((previous) => (previous && previous < savedAt ? previous : savedAt));
      }
    };
    window.addEventListener("online", onOnline);
    window.addEventListener("offline", onOffline);
    window.addEventListener(DATA_SOURCE_EVENT, onDataSource);
    return () => {
      window.removeEventListener("online", onOnline);
      window.removeEventListener("offline", onOffline);
      window.removeEventListener(DATA_SOURCE_EVENT, onDataSource);
    };
  }, []);

  const offline = !browserOnline || apiUnreachable;
  // Retour du réseau alors que la page affiche encore une copie : proposer d'actualiser.
  useEffect(() => {
    if (!offline && oldestCopy) setReconnected(true);
  }, [offline, oldestCopy]);

  // Réseau présent mais serveur injoignable (wifi sans internet, forfait épuisé…) : aucun événement
  // du navigateur ne signalera le retour. Petite vérification régulière, seulement dans ce cas.
  useEffect(() => {
    if (!apiUnreachable || !browserOnline) return;
    const probe = async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/health`, { cache: "no-store" });
        if (response.ok) announceDataSource({ source: "network" });
      } catch {
        // toujours injoignable
      }
    };
    const id = setInterval(() => void probe(), REACHABILITY_PROBE_MS);
    return () => clearInterval(id);
  }, [apiUnreachable, browserOnline]);

  return { offline, browserOnline, oldestCopy, reconnected, dismissReconnected: () => setReconnected(false) };
}

// Phase 32, lot 2 — envoi automatique des saisies gardées sur l'appareil (appel, notes) : à
// l'ouverture, au retour du réseau, puis toutes les minutes tant qu'il en reste.
const OUTBOX_RETRY_MS = 60_000;

function useOutboxSync(authenticated: boolean, offline: boolean, pendingCount: number) {
  useEffect(() => {
    if (!authenticated) return;
    const send = () => void syncOutbox();
    send();
    window.addEventListener("online", send);
    return () => window.removeEventListener("online", send);
  }, [authenticated]);

  useEffect(() => {
    if (authenticated && !offline && pendingCount > 0) void syncOutbox();
  }, [authenticated, offline, pendingCount]);

  useEffect(() => {
    if (!authenticated || pendingCount === 0) return;
    const id = setInterval(() => void syncOutbox(), OUTBOX_RETRY_MS);
    return () => clearInterval(id);
  }, [authenticated, pendingCount]);
}

// 2026-11-17 — les bandeaux sont posés par-dessus la page : sans espace réservé, ce qu'ils couvrent
// en bas de page (ex. « Enregistrer l'appel ») restait inatteignable. La page reçoit en bas un
// espace égal à leur hauteur réelle, recalculé à chaque changement, retiré quand ils disparaissent.
function useReservedBottomSpace(element: HTMLElement | null) {
  useEffect(() => {
    if (!element) return;
    const apply = () => {
      document.body.style.paddingBottom = `${element.offsetHeight}px`;
      // Refonte, phase 2 (2026-11-23) : hauteur publiée aussi pour les barres d'action collées en bas
      // (components/ui/ActionBar.tsx), qui se posent au-dessus des bandeaux au lieu d'être couvertes.
      document.documentElement.style.setProperty("--bottom-banners-height", `${element.offsetHeight}px`);
      // L'espace ajouté prend le fond de l'espace affiché (gris clair des espaces connectés), pas le
      // blanc par défaut de la page.
      // (Les premiers enfants de <body> sont des scripts de Next.js, sans fond : on prend le premier
      // élément qui en a un.)
      const background = Array.from(document.body.children)
        .filter((child) => child !== element && !element.contains(child))
        .map((child) => getComputedStyle(child).backgroundColor)
        .find((color) => color && color !== "rgba(0, 0, 0, 0)" && color !== "transparent");
      document.body.style.backgroundColor = background ?? "";
    };
    apply();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(apply);
    observer?.observe(element);
    return () => {
      observer?.disconnect();
      document.body.style.paddingBottom = "";
      document.documentElement.style.removeProperty("--bottom-banners-height");
      document.body.style.backgroundColor = "";
    };
  }, [element]);
}

// Lot 3 — la boîte d'envoi mêle saisies (appel, notes) et encaissements : chacun nommé.
function countLabel(entries: OutboxEntry[]): string {
  const cash = entries.filter((entry) => entry.kind === "payment").length;
  const other = entries.length - cash;
  const parts: string[] = [];
  if (cash > 0) parts.push(cash === 1 ? "1 encaissement" : `${cash} encaissements`);
  if (other > 0) parts.push(other === 1 ? "1 saisie (appel ou notes)" : `${other} saisies (appel ou notes)`);
  return parts.join(" et ");
}

function failedLabel(entries: OutboxEntry[]): string {
  const cash = entries.filter((entry) => entry.kind === "payment").length;
  const other = entries.length - cash;
  const parts: string[] = [];
  if (cash > 0) parts.push(cash === 1 ? "1 encaissement a été refusé" : `${cash} encaissements ont été refusés`);
  if (other > 0) parts.push(other === 1 ? "1 saisie a été refusée" : `${other} saisies ont été refusées`);
  return `${parts.join(" et ")} par le serveur.`;
}

function failedLink(entries: OutboxEntry[]): string {
  if (entries.some((entry) => entry.kind === "payment")) return "/cashier";
  return entries.some((entry) => entry.kind === "attendance") ? "/teacher/attendance" : "/teacher/grades";
}

function formatShortSavedAt(iso: string): string {
  const date = new Date(iso);
  const day = date.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit" });
  const time = date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });
  return `${day} à ${time}`;
}

export function PwaSupport() {
  const { status, user, roles, permissions } = useAuth();
  const authenticated = status === "authenticated";
  const updateReady = useServiceWorker(authenticated);
  const install = useInstallPrompt();
  const [installHidden, setInstallHidden] = useState(true);
  const { offline, browserOnline, oldestCopy, reconnected, dismissReconnected } = useOfflineState();
  const outbox = useOutbox();
  const pending = outbox.filter((entry) => entry.state === "pending");
  const pendingCount = pending.length;
  const failed = outbox.filter((entry) => entry.state === "failed");
  const [sending, setSending] = useState(false);
  const teacher = hasTeacherRole(user, roles);
  const collector = permissions.includes("payments.manage");
  useOutboxSync(authenticated, offline, pendingCount);
  const pushOffer = usePushOffer(authenticated);
  const [bannerArea, setBannerArea] = useState<HTMLDivElement | null>(null);
  useReservedBottomSpace(bannerArea);
  // Bandeau « Hors connexion » masqué par l'utilisateur : il revient à la prochaine coupure.
  const [offlineHidden, setOfflineHidden] = useState(false);
  useEffect(() => {
    if (!offline) setOfflineHidden(false);
  }, [offline]);

  useEffect(() => {
    setInstallHidden(installRecentlyDismissed());
  }, []);

  async function handleSendNow() {
    setSending(true);
    try {
      await syncOutbox();
    } finally {
      setSending(false);
    }
  }

  async function handleInstall() {
    const prompt = install.prompt;
    if (!prompt) return;
    install.clear();
    await prompt.prompt();
    await prompt.userChoice.catch(() => null);
  }

  function handleInstallLater() {
    try {
      window.localStorage.setItem(INSTALL_DISMISSED_KEY, String(Date.now()));
    } catch {
      // ignore
    }
    setInstallHidden(true);
  }

  const showInstall = authenticated && install.prompt !== null && !installHidden && !offline;

  const showOutbox = authenticated && (pendingCount > 0 || failed.length > 0);

  const showOffline = offline && !offlineHidden;

  const showPushOffer = pushOffer.offer && !offline;

  if (!showOffline && !reconnected && !updateReady && !showInstall && !showOutbox && !showPushOffer && !pushOffer.message) {
    return null;
  }

  return (
    <div
      ref={setBannerArea}
      className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-1.5 px-2 pt-2"
      // Refonte, phase 1 (2026-11-23) : sur téléphone, les bandeaux se posent juste au-dessus de la barre
      // de navigation du bas (hauteur publiée par components/shell/MobileTabBar.tsx), qui couvre déjà la
      // zone du geste d'accueil des iPhone. Sans cette barre : collés en bas, comme avant.
      style={{
        bottom: "var(--bottom-nav-height, 0px)",
        paddingBottom: "var(--banner-pad-bottom, max(0.5rem, env(safe-area-inset-bottom)))",
      }}
    >
      {showOffline && (
        <div
          role="status"
          className="pointer-events-auto flex w-full max-w-xl items-start justify-between gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 shadow-lg"
        >
          <div className="min-w-0">
            <p className="font-semibold">
              {browserOnline ? "Connexion au serveur impossible" : "Hors connexion"}
              {oldestCopy && (
                <span className="font-normal" title={`Informations enregistrées sur cet appareil le ${formatSavedAt(oldestCopy)}`}>
                  {` · infos du ${formatShortSavedAt(oldestCopy)}`}
                </span>
              )}
            </p>
            <p className="text-xs">
              {teacher
                ? "Appel et notes : gardés sur l'appareil, envoyés au retour d'internet. Le reste attendra."
                : collector
                  ? "Encaissements : gardés sur l'appareil avec reçu provisoire (caisse ouverte), envoyés au retour d'internet."
                  : "Les modifications attendront le retour d'internet."}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setOfflineHidden(true)}
            aria-label="Masquer ce bandeau"
            className="-mr-1 shrink-0 rounded px-2 text-lg leading-none text-amber-800 hover:bg-amber-100"
          >
            ×
          </button>
        </div>
      )}
      {authenticated && pendingCount > 0 && (
        <div
          role="status"
          className="pointer-events-auto flex w-full max-w-xl flex-wrap items-center justify-between gap-2 rounded-lg border border-sky-300 bg-sky-50 px-3 py-2 text-sm text-sky-900 shadow-lg"
        >
          <p>{countLabel(pending)} en attente d&apos;envoi.</p>
          {!offline && (
            <button
              type="button"
              onClick={() => void handleSendNow()}
              disabled={sending}
              className="shrink-0 rounded bg-sky-800 px-3 py-1 font-medium text-white hover:bg-sky-900 disabled:opacity-50"
            >
              {sending ? "Envoi..." : "Envoyer maintenant"}
            </button>
          )}
        </div>
      )}
      {authenticated && failed.length > 0 && (
        <div
          role="alert"
          className="pointer-events-auto flex w-full max-w-xl flex-wrap items-center justify-between gap-3 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-900 shadow-lg"
        >
          <p>{failedLabel(failed)}</p>
          <Link href={failedLink(failed)} className="shrink-0 font-medium underline">
            Voir
          </Link>
        </div>
      )}
      {!offline && reconnected && (
        <div
          role="status"
          className="pointer-events-auto flex w-full max-w-xl items-center justify-between gap-3 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-900 shadow-lg"
        >
          <p>Connexion rétablie : les informations affichées peuvent être anciennes.</p>
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="rounded bg-emerald-700 px-3 py-1.5 font-medium text-white hover:bg-emerald-800"
            >
              Actualiser
            </button>
            <button type="button" onClick={dismissReconnected} className="px-2 py-1.5 text-emerald-800 underline">
              Fermer
            </button>
          </div>
        </div>
      )}
      {updateReady && (
        <div
          role="status"
          className="pointer-events-auto flex w-full max-w-xl items-center justify-between gap-3 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-lg"
        >
          <p>Une nouvelle version d&apos;EduLinkage est prête.</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="shrink-0 rounded bg-slate-900 px-3 py-1.5 font-medium text-white hover:bg-slate-700"
          >
            Recharger
          </button>
        </div>
      )}
      {showInstall && (
        <div className="pointer-events-auto flex w-full max-w-xl flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-lg">
          <p>Installez EduLinkage sur cet appareil pour l&apos;ouvrir comme une application, même sans connexion.</p>
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              onClick={() => void handleInstall()}
              className="rounded bg-slate-900 px-3 py-1.5 font-medium text-white hover:bg-slate-700"
            >
              Installer
            </button>
            <button type="button" onClick={handleInstallLater} className="px-2 py-1.5 text-slate-600 underline">
              Plus tard
            </button>
          </div>
        </div>
      )}
      {showPushOffer && (
        <div
          data-testid="push-offer"
          className="pointer-events-auto flex w-full max-w-xl flex-wrap items-center justify-between gap-3 rounded-lg border border-sky-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-lg"
        >
          <p>🔔 Recevez les annonces de l&apos;école sur cet appareil, même quand EduLinkage est fermé.</p>
          <div className="flex shrink-0 gap-2">
            <button
              type="button"
              onClick={() => void pushOffer.enable()}
              disabled={pushOffer.busy}
              className="rounded bg-sky-800 px-3 py-1.5 font-medium text-white hover:bg-sky-900 disabled:opacity-50"
            >
              {pushOffer.busy ? "Activation..." : "Activer"}
            </button>
            <button type="button" onClick={pushOffer.later} className="px-2 py-1.5 text-slate-600 underline">
              Plus tard
            </button>
          </div>
        </div>
      )}
      {pushOffer.message && (
        <div role="status" className="pointer-events-auto w-full max-w-xl rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-lg">
          {pushOffer.message}
        </div>
      )}
    </div>
  );
}
