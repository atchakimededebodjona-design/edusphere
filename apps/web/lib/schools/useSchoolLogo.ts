"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth/useAuth";
import { getSchoolLogoBlobUrl } from "@/lib/schools/client";

// Logo de l'école courante, affiché dans le menu latéral (2026-11-16). Le fichier est servi par
// l'API avec authentification (`GET /schools/{id}/logo`, permission `schools.read`) : il est lu
// en blob, jamais par une URL publique. Sans logo, sans droit ou en cas d'échec : `url` est nulle
// et l'appelant affiche le symbole EduLinkage.

const LOGO_CHANGED_EVENT = "edulinkage:school-logo-changed";

type LogoChangedDetail = { schoolId: string; logoPath: string | null };

/** À appeler après l'envoi d'un nouveau logo : le menu latéral le recharge sans attendre. */
export function announceSchoolLogoChange(schoolId: string, logoPath: string | null): void {
  window.dispatchEvent(new CustomEvent<LogoChangedDetail>(LOGO_CHANGED_EVENT, { detail: { schoolId, logoPath } }));
}

export type CurrentSchoolLogo = {
  url: string | null;
  /** Un logo est attendu mais pas encore chargé : réserver sa place, sans afficher le symbole. */
  pending: boolean;
};

export function useCurrentSchoolLogo(): CurrentSchoolLogo {
  const { currentSchool, permissions } = useAuth();
  const schoolId = currentSchool?.id ?? null;
  const contextLogoPath = currentSchool?.logo_path ?? null;
  const canRead = permissions.includes("schools.read");

  // Chemin connu du logo : celui du contexte, sauf si un envoi en a annoncé un nouveau pour cette
  // école (le contexte d'authentification ne recharge pas l'école à ce moment-là).
  const [announced, setAnnounced] = useState<LogoChangedDetail | null>(null);
  const logoPath = announced && announced.schoolId === schoolId ? announced.logoPath : contextLogoPath;

  useEffect(() => {
    const listener = (event: Event) => {
      const detail = (event as CustomEvent<LogoChangedDetail>).detail;
      if (detail?.schoolId) setAnnounced(detail);
    };
    window.addEventListener(LOGO_CHANGED_EVENT, listener);
    return () => window.removeEventListener(LOGO_CHANGED_EVENT, listener);
  }, []);

  const expectedKey = schoolId && logoPath && canRead ? `${schoolId}:${logoPath}` : null;
  const [loaded, setLoaded] = useState<{ key: string; url: string | null } | null>(null);

  useEffect(() => {
    if (!expectedKey || !schoolId) return;
    let cancelled = false;
    let created: string | null = null;
    void getSchoolLogoBlobUrl(schoolId).then((blobUrl) => {
      if (cancelled) {
        if (blobUrl) URL.revokeObjectURL(blobUrl);
        return;
      }
      created = blobUrl;
      setLoaded({ key: expectedKey, url: blobUrl });
    });
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [expectedKey, schoolId]);

  if (!expectedKey) return { url: null, pending: false };
  if (loaded?.key !== expectedKey) return { url: null, pending: true };
  return { url: loaded.url, pending: false };
}
