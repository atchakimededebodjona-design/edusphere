// Contacts publics de la page d'accueil, choisis par l'exploitant le 2026-11-16 : WhatsApp et appel
// sur le même numéro. Aucun autre canal n'est affiché.
const WHATSAPP_NUMBER = "22870950343";

export const CONTACT_PHONE_DISPLAY = "+228 70 95 03 43";
export const CONTACT_PHONE_LINK = "tel:+22870950343";

export const SCHOOL_WHATSAPP_MESSAGE = "Bonjour, je souhaite découvrir EduLinkage pour mon école.";
export const PARTNER_WHATSAPP_MESSAGE = "Bonjour, je souhaite devenir partenaire EduLinkage.";

/** Lien qui ouvre une conversation WhatsApp avec le message prérempli. */
export function whatsappLink(message: string = SCHOOL_WHATSAPP_MESSAGE): string {
  return `https://wa.me/${WHATSAPP_NUMBER}?text=${encodeURIComponent(message)}`;
}
