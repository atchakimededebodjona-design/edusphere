"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

// 2026-11-24 — bandeau de consentement à la mesure d'audience (Umami, hébergé sur le serveur de
// l'exploitant, sans cookie). Le script Umami n'est chargé QU'APRÈS « Accepter », et seulement sur les
// pages publiques : l'espace connecté des écoles n'est jamais mesuré. Le choix est gardé sur l'appareil
// (localStorage) ; « Modifier mon choix » (ConsentSettingsButton) rouvre le bandeau.
// Sans configuration Umami au build (config/analytics.js), rien ne s'affiche.

const SRC = process.env.NEXT_PUBLIC_UMAMI_SRC ?? "";
const WEBSITE_ID = process.env.NEXT_PUBLIC_UMAMI_WEBSITE_ID ?? "";
const STORAGE_KEY = "edulinkage-audience-consent";
export const OPEN_CONSENT_EVENT = "edulinkage:open-consent";
const PUBLIC_PATHS = new Set(["/", "/confidentialite", "/cgu", "/cgv"]);
// Les deux réponses ont exactement le même poids visuel : refuser doit être aussi simple qu'accepter.
const CHOICE_BUTTON_CLASS =
  "min-h-11 rounded-lg border border-brand-blue bg-white px-5 text-sm font-semibold text-brand-blue hover:bg-brand-blue/5 " +
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-blue sm:min-w-[7.5rem]";

type Choice = "granted" | "denied";

function readChoice(): Choice | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "granted" || value === "denied" ? value : null;
  } catch {
    return null;
  }
}

function loadUmami() {
  if (!SRC || !WEBSITE_ID || document.querySelector("script[data-edulinkage-umami]")) return;
  const script = document.createElement("script");
  script.src = SRC;
  script.defer = true;
  script.dataset.websiteId = WEBSITE_ID;
  script.dataset.doNotTrack = "true";
  script.dataset.edulinkageUmami = "true";
  document.head.appendChild(script);
}

export function AnalyticsConsent() {
  const pathname = usePathname();
  const configured = Boolean(SRC && WEBSITE_ID);
  const onPublicPage = PUBLIC_PATHS.has(pathname);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!configured) return;
    const stored = readChoice();
    setChoice(stored);
    setOpen(stored === null);
    const reopen = () => setOpen(true);
    window.addEventListener(OPEN_CONSENT_EVENT, reopen);
    return () => window.removeEventListener(OPEN_CONSENT_EVENT, reopen);
  }, [configured]);

  useEffect(() => {
    if (configured && onPublicPage && choice === "granted") loadUmami();
  }, [configured, onPublicPage, choice]);

  function decide(next: Choice) {
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Stockage indisponible (navigation privée stricte) : le choix vaut pour cette visite seulement.
    }
    setChoice(next);
    setOpen(false);
    // Un refus après acceptation : la mesure s'arrête au prochain chargement de page.
    if (next === "denied" && document.querySelector("script[data-edulinkage-umami]")) window.location.reload();
  }

  if (!configured || !onPublicPage || !open) return null;

  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-labelledby="consent-title"
      aria-describedby="consent-text"
      className="fixed inset-x-3 bottom-3 z-50 mx-auto max-w-xl rounded-2xl border border-slate-200 bg-white p-5 shadow-2xl sm:inset-x-6 sm:bottom-6"
    >
      <p id="consent-title" className="text-base font-bold text-brand-text">
        Mesure d&apos;audience
      </p>
      <p id="consent-text" className="mt-1 text-sm leading-relaxed text-slate-700">
        Avec votre accord, nous mesurons la fréquentation de ce site avec Umami, installé sur nos propres serveurs :{" "}
        <strong>sans cookie</strong>, sans identifiant personnel, sans publicité.{" "}
        <Link href="/confidentialite#cookies" className="font-medium text-brand-blue underline underline-offset-2">
          En savoir plus
        </Link>
      </p>
      <div className="mt-4 grid grid-cols-2 gap-2 sm:flex sm:justify-end">
        <button type="button" onClick={() => decide("denied")} className={CHOICE_BUTTON_CLASS}>
          Refuser
        </button>
        <button type="button" onClick={() => decide("granted")} className={CHOICE_BUTTON_CLASS}>
          Accepter
        </button>
      </div>
    </div>
  );
}
