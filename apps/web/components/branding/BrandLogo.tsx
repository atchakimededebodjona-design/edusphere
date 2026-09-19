import Image from "next/image";

// Assets officiels EduLinkage (apps/web/public/branding/) — fichiers fournis tels quels, jamais
// recréés en HTML/CSS/SVG ni recolorés. Dimensions réelles des fichiers sources : next/image
// calcule le ratio d'affichage à partir de ces valeurs, ce qui empêche toute déformation quelle
// que soit la classe Tailwind appliquée (hauteur fixée, largeur toujours proportionnelle).
const SYMBOL_SRC = "/branding/edulinkage-symbol.png";
const SYMBOL_SIZE = { width: 1254, height: 1254 };
const FULL_SRC = "/branding/edulinkage-full.png";
const FULL_SIZE = { width: 1536, height: 1024 };

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
