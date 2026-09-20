"use client";

import { useEffect, useRef, useState } from "react";

/** Révélation douce au scroll (fade + léger translateY) pour les sections de la landing page.
 * Respecte `prefers-reduced-motion` de deux façons complémentaires : lecture directe de
 * `matchMedia` (affiche le contenu immédiatement, sans jamais l'animer) ET la variante Tailwind
 * `motion-reduce:` sur la transition elle-même (filet de sécurité si le média query change après
 * le montage). N'utilise aucune librairie — IntersectionObserver natif uniquement. */
export function ScrollReveal({
  children,
  className = "",
  delayMs = 0,
}: {
  children: React.ReactNode;
  className?: string;
  delayMs?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setVisible(true);
      return;
    }

    // rootMargin positif en bas : la section est considérée "visible" un peu AVANT d'entrer
    // réellement dans le viewport, pour que la transition (700ms) ait le temps de se terminer
    // avant que l'utilisateur ne l'atteigne visuellement — vérifié nécessaire lors d'un défilement
    // rapide ou d'un saut d'ancre instantané (nav), pas seulement un défilement lent au trackpad.
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0, rootMargin: "0px 0px 150px 0px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      style={{ transitionDelay: visible ? `${delayMs}ms` : "0ms" }}
      className={`transition-all duration-700 ease-out motion-reduce:transition-none motion-reduce:transform-none ${
        visible ? "translate-y-0 opacity-100" : "translate-y-6 opacity-0"
      } ${className}`}
    >
      {children}
    </div>
  );
}
