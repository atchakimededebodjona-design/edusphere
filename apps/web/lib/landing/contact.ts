// Contacts publics de la page d'accueil, choisis par l'exploitant : WhatsApp et appel sur le même
// numéro (2026-11-16), et adresse e-mail (2026-11-24). Aucun autre canal n'est affiché.
const WHATSAPP_NUMBER = "22870950343";

export const CONTACT_PHONE_DISPLAY = "+228 70 95 03 43";
export const CONTACT_PHONE_LINK = "tel:+22870950343";

// Protection anti-spam (2026-11-24) : l'adresse n'est jamais écrite en clair dans le HTML envoyé par le
// serveur. Elle est assemblée dans le navigateur (components/landing/ProtectedEmail.tsx), après le
// chargement : les robots qui moissonnent les pages à la recherche d'adresses ne la trouvent pas.
const CONTACT_EMAIL_PARTS = ["bigtechcorpdigital", "gmail.com"] as const;

export function contactEmail(): string {
  return CONTACT_EMAIL_PARTS.join("@");
}

export const SCHOOL_WHATSAPP_MESSAGE = "Bonjour, je souhaite découvrir EduLinkage pour mon école.";
export const PARTNER_WHATSAPP_MESSAGE = "Bonjour, je souhaite devenir partenaire EduLinkage.";

/** Lien qui ouvre une conversation WhatsApp avec le message prérempli. */
export function whatsappLink(message: string = SCHOOL_WHATSAPP_MESSAGE): string {
  return `https://wa.me/${WHATSAPP_NUMBER}?text=${encodeURIComponent(message)}`;
}
