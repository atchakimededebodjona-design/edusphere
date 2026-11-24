"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";

// Refonte, phase 0 (2026-11-23) — fenêtre accessible commune : rôle « dialog », titre annoncé, touche
// Échap, focus placé dans la fenêtre puis rendu à l'élément d'origine, page derrière figée. Deux formes :
// centrée (confirmation) ou feuille montant du bas (menus sur téléphone).
export function Modal({
  open,
  onClose,
  title,
  children,
  placement = "center",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  placement?: "center" | "sheet";
}) {
  const titleId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    // Phase 3 (2026-11-24) — `[data-autofocus]` d'abord : dans une seule liste de sélecteurs,
    // `querySelector` rend le premier élément DANS L'ORDRE DE LA PAGE, donc toujours le bouton
    // « Fermer » de l'en-tête, jamais le champ ou le bouton désigné.
    const focusable =
      panel.current?.querySelector<HTMLElement>("[data-autofocus]") ??
      panel.current?.querySelector<HTMLElement>("button, a[href], input, select, textarea");
    (focusable ?? panel.current)?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      previous?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  const sheet = placement === "sheet";
  return (
    <div
      className={`fixed inset-0 z-[60] flex bg-slate-900/50 ${sheet ? "items-end" : "items-center justify-center p-4"}`}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={
          sheet
            ? "max-h-[85vh] w-full overflow-y-auto rounded-t-2xl bg-white pb-[max(1rem,env(safe-area-inset-bottom))] shadow-xl"
            : "w-full max-w-md rounded-xl bg-white shadow-xl"
        }
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <h2 id={titleId} className="text-base font-bold text-slate-900">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fermer"
            className="flex h-10 w-10 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100"
          >
            <Icon name="close" />
          </button>
        </div>
        <div className="px-4 py-4">{children}</div>
      </div>
    </div>
  );
}

/** Confirmation d'une action sensible, à la place des confirmations faites à la volée. */
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  tone = "primary",
  busy = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: ReactNode;
  confirmLabel: string;
  tone?: "primary" | "danger";
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <Modal open={open} onClose={onCancel} title={title}>
      <div className="flex flex-col gap-4">
        <div className="text-sm text-slate-700">{message}</div>
        <div className="flex flex-wrap justify-end gap-2">
          {/* Action dangereuse : le focus part sur « Annuler », jamais sur le bouton qui détruit. */}
          <Button variant="secondary" onClick={onCancel} disabled={busy} data-autofocus={tone === "danger" ? true : undefined}>
            Annuler
          </Button>
          <Button variant={tone} onClick={onConfirm} disabled={busy} data-autofocus={tone === "danger" ? undefined : true}>
            {busy ? "Un instant..." : confirmLabel}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
