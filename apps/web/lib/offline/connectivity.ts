"use client";

// Phase 32, lot 3 — « le serveur répond-il ? » pour un écran qui change de comportement sans internet
// (la caisse). Mêmes signaux que les bandeaux de components/pwa/PwaSupport.tsx : événements du
// navigateur et origine des dernières données lues (lib/offline/status.ts). Indicatif : chaque
// opération garde son propre repli si le serveur ne répond pas.

import { useEffect, useState } from "react";
import { DATA_SOURCE_EVENT, type DataSourceDetail } from "@/lib/offline/status";

export function useServerReachable(): boolean {
  const [browserOnline, setBrowserOnline] = useState(true);
  const [apiUnreachable, setApiUnreachable] = useState(false);

  useEffect(() => {
    setBrowserOnline(navigator.onLine !== false);
    const onOnline = () => {
      setBrowserOnline(true);
      setApiUnreachable(false);
    };
    const onOffline = () => setBrowserOnline(false);
    const onDataSource = (event: Event) => {
      const detail = (event as CustomEvent<DataSourceDetail>).detail;
      if (detail) setApiUnreachable(detail.source !== "network");
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

  return browserOnline && !apiUnreachable;
}
