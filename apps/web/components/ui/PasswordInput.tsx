"use client";

import { useState, type InputHTMLAttributes } from "react";
import { Icon } from "@/components/ui/Icon";

type PasswordInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  /** Classes du bloc qui entoure le champ (marges, largeur), le champ prenant toute sa largeur. */
  wrapperClassName?: string;
  /** Nom du bouton, à préciser quand la page a deux champs (mot de passe et confirmation). */
  toggleLabel?: string;
};

/**
 * Champ de mot de passe avec un bouton pour l'afficher ou le masquer (2026-11-24). Le bouton est
 * dans le champ, à droite ; il ne soumet jamais le formulaire. Il se lit « Afficher le mot de passe »,
 * enfoncé ou non (aria-pressed), et le mot de passe redevient masqué au prochain affichage du
 * formulaire. Toutes les autres propriétés (placeholder, autoComplete, required…) passent au champ.
 */
export function PasswordInput({
  className = "",
  wrapperClassName = "",
  toggleLabel = "Afficher le mot de passe",
  ...props
}: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  return (
    <span className={`relative flex ${wrapperClassName}`}>
      <input
        {...props}
        type={visible ? "text" : "password"}
        autoCapitalize="none"
        autoCorrect="off"
        spellCheck={false}
        className={`w-full min-w-0 pr-11 ${className}`}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        aria-pressed={visible}
        aria-label={toggleLabel}
        title={visible ? "Masquer" : "Afficher"}
        className="absolute inset-y-0 right-0 flex w-11 items-center justify-center rounded-r-lg text-slate-600 hover:text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-primary-600"
      >
        <Icon name={visible ? "eyeOff" : "eye"} />
      </button>
    </span>
  );
}
