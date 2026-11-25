"use client";

import { useEffect, useState, type ReactNode } from "react";
import { contactEmail } from "@/lib/landing/contact";

/** Lien « mailto » assemblé dans le navigateur (protection anti-spam, voir lib/landing/contact.ts). Avant
 * le chargement, et pour un robot qui ne lit que le HTML, seul le texte de remplacement s'affiche.
 * `parts` : une autre adresse, découpée autour de « @ » (par défaut, l'adresse de contact du site). */
export function ProtectedEmail({
  className,
  icon,
  placeholder = "Adresse e-mail",
  parts,
}: {
  className?: string;
  icon?: ReactNode;
  placeholder?: string;
  parts?: readonly [string, string];
}) {
  const [email, setEmail] = useState<string | null>(null);
  const local = parts?.[0];
  const domain = parts?.[1];
  useEffect(() => setEmail(local && domain ? [local, domain].join("@") : contactEmail()), [local, domain]);
  if (!email) {
    return (
      <span className={className} aria-hidden="true">
        {icon}
        {placeholder}
      </span>
    );
  }
  return (
    <a href={`mailto:${email}`} className={className}>
      {icon}
      {email}
    </a>
  );
}
