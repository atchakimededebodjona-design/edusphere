"use client";

import { useEffect, useState } from "react";
import { MessageSquareIcon } from "@/components/landing/icons";
import { whatsappLink } from "@/lib/landing/contact";

/** 2026-11-24 — appel à l'action toujours à portée de pouce sur téléphone : une barre « Essayer
 * gratuitement » apparaît en bas de l'écran une fois le haut de page (#accueil) dépassé, et disparaît
 * dans la section « Contact » (qui propose déjà les mêmes boutons) et sur le pied de page. Absente sur
 * grand écran. */
export function StickyCta() {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const hero = document.getElementById("accueil");
    const contact = document.getElementById("contact");
    const footer = document.querySelector("footer");
    if (!hero || typeof IntersectionObserver === "undefined") return;
    // Masquée en haut de page, dans « Contact » et sur le pied de page (qu'elle ne doit jamais couvrir).
    const shown = new Map<Element, boolean>([[hero, true]]);
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) shown.set(entry.target, entry.isIntersecting);
      setVisible(![...shown.values()].some(Boolean));
    });
    for (const el of [hero, contact, footer]) if (el) observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div
      className={`fixed inset-x-0 bottom-0 z-40 border-t border-slate-200 bg-white/95 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 shadow-[0_-4px_16px_rgba(15,23,42,0.08)] backdrop-blur transition-transform duration-200 motion-reduce:transition-none sm:hidden ${
        visible ? "translate-y-0" : "pointer-events-none translate-y-full"
      }`}
      aria-hidden={!visible}
    >
      <a
        href={whatsappLink()}
        target="_blank"
        rel="noopener noreferrer"
        tabIndex={visible ? 0 : -1}
        className="flex min-h-12 items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-brand-blue to-brand-cyan px-6 text-sm font-semibold text-white shadow-sm"
      >
        <MessageSquareIcon className="h-5 w-5" />
        Essayer gratuitement — 1er trimestre offert
      </a>
    </div>
  );
}
