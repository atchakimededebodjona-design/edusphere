"use client";

import { useEffect, useRef } from "react";

/**
 * Refonte, phase 2 (2026-11-23) — amène une zone à l'écran quand l'utilisateur vient de l'ouvrir (ex. la
 * saisie des notes, placée sous la liste des évaluations sur téléphone). `token` augmente à chaque
 * ouverture voulue ; 0 = rien à faire (premier affichage). Sans animation si l'appareil demande moins de
 * mouvement. La zone porte `scroll-mt-*` pour ne pas passer sous la barre du haut.
 */
export function useReveal<T extends HTMLElement>(token: number) {
  const ref = useRef<T>(null);
  useEffect(() => {
    if (token === 0 || !ref.current) return;
    const reduce = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    ref.current.scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
  }, [token]);
  return ref;
}
