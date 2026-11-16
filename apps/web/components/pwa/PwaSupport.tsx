"use client";

import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { API_URL } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/useAuth";
import { announceDataSource, DATA_SOURCE_EVENT, type DataSourceDetail } from "@/lib/offline/status";

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

export function PwaSupport() {
  const { status } = useAuth();
  const authenticated = status === "authenticated";
  const updateReady = useServiceWorker(authenticated);
  const install = useInstallPrompt();
  const [installHidden, setInstallHidden] = useState(true);
  const { offline, browserOnline, oldestCopy, reconnected, dismissReconnected } = useOfflineState();

  useEffect(() => {
    setInstallHidden(installRecentlyDismissed());
  }, []);

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

  if (!offline && !reconnected && !updateReady && !showInstall) return null;

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-50 flex flex-col items-center gap-2 p-3">
      {offline && (
        <div
          role="status"
          className="pointer-events-auto w-full max-w-xl rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 shadow-lg"
        >
          <p className="font-semibold">{browserOnline ? "Connexion au serveur impossible" : "Hors connexion"}</p>
          <p>
            {oldestCopy
              ? `Informations enregistrées sur cet appareil le ${formatSavedAt(oldestCopy)}. `
              : "Les pages déjà ouvertes avec internet restent consultables. "}
            Aucune modification ne peut être envoyée pour l&apos;instant.
          </p>
        </div>
      )}
      {!offline && reconnected && (
        <div
          role="status"
          className="pointer-events-auto flex w-full max-w-xl items-center justify-between gap-3 rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm text-emerald-900 shadow-lg"
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
          className="pointer-events-auto flex w-full max-w-xl items-center justify-between gap-3 rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm text-slate-800 shadow-lg"
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
        <div className="pointer-events-auto flex w-full max-w-xl flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-300 bg-white px-4 py-3 text-sm text-slate-800 shadow-lg">
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
    </div>
  );
}
