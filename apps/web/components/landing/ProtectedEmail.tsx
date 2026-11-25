"use client";

import { useEffect, useState, type ReactNode } from "react";
import { contactEmail } from "@/lib/landing/contact";

/** Lien « mailto » assemblé dans le navigateur (protection anti-spam, voir lib/landing/contact.ts). Avant
 * le chargement, et pour un robot qui ne lit que le HTML, seul le texte de remplacement s'affiche. */
export function ProtectedEmail({
  className,
  icon,
  placeholder = "Adresse e-mail",
}: {
  className?: string;
  icon?: ReactNode;
  placeholder?: string;
}) {
  const [email, setEmail] = useState<string | null>(null);
  useEffect(() => setEmail(contactEmail()), []);
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
