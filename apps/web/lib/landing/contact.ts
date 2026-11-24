// Contacts publics de la page d'accueil, choisis par l'exploitant : WhatsApp et appel sur le même
// numéro (2026-11-16), et adresse e-mail (2026-11-24). Aucun autre canal n'est affiché.
const WHATSAPP_NUMBER = "22870950343";

export const CONTACT_PHONE_DISPLAY = "+228 70 95 03 43";
export const CONTACT_PHONE_LINK = "tel:+22870950343";

export const CONTACT_EMAIL = "bigtechcorpdigital@gmail.com";
export const CONTACT_EMAIL_LINK = `mailto:${CONTACT_EMAIL}`;

export const SCHOOL_WHATSAPP_MESSAGE = "Bonjour, je souhaite découvrir EduLinkage pour mon école.";
export const PARTNER_WHATSAPP_MESSAGE = "Bonjour, je souhaite devenir partenaire EduLinkage.";

/** Lien qui ouvre une conversation WhatsApp avec le message prérempli. */
export function whatsappLink(message: string = SCHOOL_WHATSAPP_MESSAGE): string {
  return `https://wa.me/${WHATSAPP_NUMBER}?text=${encodeURIComponent(message)}`;
}
