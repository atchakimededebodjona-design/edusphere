"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";

// Refonte, phase 2 (2026-11-23) — onglets accessibles : rôle « tablist », onglet actif annoncé, flèches
// gauche/droite, Début et Fin pour passer d'un onglet à l'autre. Ils défilent sur le côté s'ils ne
// tiennent pas sur la largeur d'un téléphone. `id` (useId du parent) relie l'onglet actif à son panneau
// (TabPanel, même `id`).
export function Tabs<T extends string>({
  id,
  label,
  tabs,
  value,
  onChange,
}: {
  id: string;
  label: string;
  tabs: { key: T; label: string }[];
  value: T;
  onChange: (key: T) => void;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = tabs.length - 1;
    const target =
      event.key === "ArrowRight" ? (index === last ? 0 : index + 1)
      : event.key === "ArrowLeft" ? (index === 0 ? last : index - 1)
      : event.key === "Home" ? 0
      : event.key === "End" ? last
      : null;
    if (target === null) return;
    event.preventDefault();
    const key = tabs[target].key;
    onChange(key);
    refs.current[key]?.focus();
  }

  return (
    <div role="tablist" aria-label={label} className="-mx-4 flex gap-1 overflow-x-auto border-b border-slate-200 px-4 md:mx-0 md:px-0">
      {tabs.map((tab, index) => {
        const selected = tab.key === value;
        return (
          <button
            key={tab.key}
            ref={(node) => {
              refs.current[tab.key] = node;
            }}
            type="button"
            role="tab"
            id={`${id}-tab-${tab.key}`}
            aria-selected={selected}
            aria-controls={selected ? `${id}-panel` : undefined}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.key)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={`-mb-px min-h-11 shrink-0 border-b-2 px-4 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 ${
              selected ? "border-primary-600 text-primary-700" : "border-transparent text-slate-600 hover:text-slate-900"
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

/** Contenu de l'onglet actif, nommé par cet onglet pour les lecteurs d'écran. */
export function TabPanel({ id, active, children }: { id: string; active: string; children: ReactNode }) {
  return (
    <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-tab-${active}`} className="pt-4">
      {children}
    </div>
  );
}
