"use client";

import { useEffect, useId, useRef, useState } from "react";
import type { Organization } from "@/lib/organizations/client";
import type { School } from "@/lib/schools/client";
import type { TenantContextStatus } from "@/lib/auth/AuthProvider";
import { useAuth } from "@/lib/auth/useAuth";

// Sélecteur de contexte organisation/école, permanent dans le header, une fois authentifié.
// Source unique de vérité : AuthProvider (currentOrganization(Id), currentSchool(Id),
// availableOrganizations, availableSchools, selectOrganization, selectSchool,
// organizationContextStatus, schoolContextStatus, retryTenantContext) — ce composant ne fait
// qu'afficher/déclencher, aucune logique de résolution ni de stockage ici (jamais un second
// système de gestion du tenant, voir tenantContext.ts).
//
// Toutes les options proposées viennent de ces listes, déjà vérifiées côté API : jamais une
// saisie libre, jamais un UUID choisi arbitrairement — voir aussi les gardes déjà en place dans
// AuthProvider::selectOrganization/selectSchool (n'acceptent que ce qui figure dans ces listes).

function GroupHeading({ children }: { children: React.ReactNode }) {
  return <p className="mb-1 px-2 text-xs font-semibold uppercase tracking-wide text-slate-400">{children}</p>;
}

function ItemButton({
  label,
  checked,
  onClick,
}: {
  label: string;
  checked: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="menuitemradio"
      aria-checked={checked}
      onClick={onClick}
      className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900 ${
        checked ? "font-medium text-slate-900" : "text-slate-700"
      }`}
    >
      <span aria-hidden="true">{checked ? "●" : "○"}</span>
      {label}
    </button>
  );
}

function SwitchGroup<T extends { id: string; name: string }>({
  title,
  items,
  currentId,
  status,
  error,
  onSelect,
  onRetry,
  className,
}: {
  title: string;
  items: T[];
  currentId: string | null;
  status: TenantContextStatus;
  error: string | null;
  onSelect: (id: string) => void;
  onRetry: () => void;
  className?: string;
}) {
  return (
    <div className={className} role="group" aria-label={title}>
      <GroupHeading>{title}</GroupHeading>
      {status === "loading" && <p className="px-2 py-1 text-sm text-slate-500">Chargement...</p>}
      {status === "error" && (
        <div className="flex flex-col items-start gap-1.5 px-2 py-1">
          <p role="alert" className="text-sm text-red-700">
            {error ?? "Une erreur est survenue."}
          </p>
          <button
            type="button"
            onClick={onRetry}
            className="rounded border border-red-300 bg-white px-2 py-1 text-xs font-medium text-red-800 hover:bg-red-100"
          >
            Réessayer
          </button>
        </div>
      )}
      {status !== "loading" && status !== "error" && (
        <div className="flex flex-col gap-0.5">
          {items.map((item) => (
            <ItemButton key={item.id} label={item.name} checked={item.id === currentId} onClick={() => onSelect(item.id)} />
          ))}
        </div>
      )}
    </div>
  );
}

export function TenantSwitcher() {
  const {
    currentOrganization,
    currentSchool,
    availableOrganizations,
    availableSchools,
    organizationContextStatus,
    schoolContextStatus,
    organizationContextError,
    schoolContextError,
    selectOrganization,
    selectSchool,
    retryTenantContext,
  } = useAuth();

  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  const canSwitchOrganization = availableOrganizations.length > 1;
  const canSwitchSchool = availableSchools.length > 1;
  const canSwitch = canSwitchOrganization || canSwitchSchool;

  // Fermeture au clic extérieur / touche Échap — pattern minimal, aucune dépendance ajoutée
  // (aucun composant de menu/dropdown n'existe déjà dans le projet, voir components/ui/).
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  // Rien à afficher tant qu'aucun nom n'est encore connu (bref instant au premier chargement) :
  // jamais un UUID ni un espace vide trompeur à la place.
  const label = currentSchool?.name ?? currentOrganization?.name ?? null;
  if (!label) return null;

  if (!canSwitch) {
    // Cas 1 (une organisation / une école) : le contexte reste visible, sans menu de changement
    // inutile — voir mission.
    return (
      <span className="flex items-center gap-1.5 rounded border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm text-slate-700">
        <span aria-hidden="true">🏫</span>
        <span className="max-w-[10rem] truncate sm:max-w-[16rem]">{label}</span>
      </span>
    );
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={`Contexte actuel : ${label}. Changer d'organisation ou d'école.`}
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900"
      >
        <span aria-hidden="true">🏫</span>
        <span className="max-w-[10rem] truncate sm:max-w-[16rem]">{label}</span>
        <span aria-hidden="true">▾</span>
      </button>

      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label="Changer de contexte"
          className="absolute right-0 z-20 mt-2 w-72 rounded border border-slate-200 bg-white p-3 shadow-lg"
        >
          {canSwitchOrganization && (
            <SwitchGroup
              title="Organisation"
              items={availableOrganizations}
              currentId={currentOrganization?.id ?? null}
              status={organizationContextStatus}
              error={organizationContextError}
              onRetry={retryTenantContext}
              onSelect={(id) => {
                // Ne ferme pas le panneau : si la nouvelle organisation a plusieurs écoles, le
                // choix de l'école suit immédiatement dans ce même panneau (voir mission,
                // "Lorsqu'une organisation est choisie... permettre le choix de l'école").
                selectOrganization(id);
              }}
            />
          )}
          {canSwitchSchool && (
            <SwitchGroup
              title="École"
              items={availableSchools}
              currentId={currentSchool?.id ?? null}
              status={schoolContextStatus}
              error={schoolContextError}
              onRetry={retryTenantContext}
              onSelect={(id) => {
                selectSchool(id);
                setOpen(false);
              }}
              className={canSwitchOrganization ? "mt-3 border-t border-slate-100 pt-3" : undefined}
            />
          )}
        </div>
      )}
    </div>
  );
}
