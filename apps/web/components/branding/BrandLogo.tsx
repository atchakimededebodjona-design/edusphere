import Image from "next/image";

// Assets officiels EduLinkage — jamais recréés en HTML/CSS/SVG ni recolorés. 2026-11-24 : les fichiers
// servis sont les originaux REDIMENSIONNÉS (sans retouche), car les images sont servies telles quelles
// (images.unoptimized, revue de sécurité) : le symbole de 1254 px pesait 657 Ko pour un affichage de
// 32 à 40 px, le logo complet 1,7 Mo pour 260 px. Originaux gardés dans apps/web/branding-sources/
// (non servis). Dimensions des fichiers servis : next/image en déduit le ratio d'affichage.
const SYMBOL_SRC = "/branding/edulinkage-symbol.png";
const SYMBOL_SIZE = { width: 256, height: 256 };
const FULL_SRC = "/branding/edulinkage-full.webp";
const FULL_SIZE = { width: 780, height: 520 };

/** Symbole seul (mortier académique + "e") — favicon, sidebar compacte, espaces étroits. */
export function BrandSymbol({
  className = "h-8 w-8",
  priority = false,
  alt = "EduLinkage",
}: {
  className?: string;
  priority?: boolean;
  alt?: string;
}) {
  return (
    <Image
      src={SYMBOL_SRC}
      alt={alt}
      width={SYMBOL_SIZE.width}
      height={SYMBOL_SIZE.height}
      priority={priority}
      className={`${className} object-contain`}
    />
  );
}

/** Logo complet (symbole + nom + slogan) — pour les espaces suffisamment larges (page de
 * connexion notamment). */
export function BrandFull({
  className = "h-8 w-auto",
  priority = false,
  alt = "Logo EduLinkage",
}: {
  className?: string;
  priority?: boolean;
  alt?: string;
}) {
  return (
    <Image
      src={FULL_SRC}
      alt={alt}
      width={FULL_SIZE.width}
      height={FULL_SIZE.height}
      priority={priority}
      className={`${className} object-contain`}
    />
  );
}

// Pas de composant "marque combinée" (logo complet ⇄ symbole selon la largeur d'écran) pour les
// barres d'en-tête : essayé, puis abandonné après vérification visuelle réelle
// (apps/web/e2e/zz-branding-check.spec.ts) — dans une barre de hauteur fixe et étroite
// (min-h-16, TopBar/ParentTopBar), le logo complet devient illisible (nom/slogan trop petits)
// **à toute largeur d'écran**, y compris en plein desktop : ce n'est pas une contrainte de
// largeur (mobile vs desktop) mais de hauteur disponible. Ces deux en-têtes utilisent donc
// directement `BrandSymbol` + le nom "EduLinkage" en texte (déjà lisible, déjà existant) — voir
// components/app-shell/TopBar.tsx et components/parent-shell/ParentTopBar.tsx.
