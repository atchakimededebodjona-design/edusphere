// 2026-11-24 — pays d'Afrique proposés dans une liste déroulante (inscription d'une organisation par la
// plateforme, inscription d'une école par un partenaire), au lieu d'un code à taper. Les 54 États membres
// de l'ONU situés en Afrique, nom en français et code ISO 3166-1 alpha-2 : c'est ce code que l'API
// enregistre (organizations.country_code, 2 lettres).

export type Country = { code: string; name: string };

const COUNTRIES: Country[] = [
  { code: "ZA", name: "Afrique du Sud" },
  { code: "DZ", name: "Algérie" },
  { code: "AO", name: "Angola" },
  { code: "BJ", name: "Bénin" },
  { code: "BW", name: "Botswana" },
  { code: "BF", name: "Burkina Faso" },
  { code: "BI", name: "Burundi" },
  { code: "CM", name: "Cameroun" },
  { code: "CV", name: "Cap-Vert" },
  { code: "CF", name: "Centrafrique" },
  { code: "KM", name: "Comores" },
  { code: "CG", name: "Congo" },
  { code: "CD", name: "Congo (RDC)" },
  { code: "CI", name: "Côte d'Ivoire" },
  { code: "DJ", name: "Djibouti" },
  { code: "EG", name: "Égypte" },
  { code: "ER", name: "Érythrée" },
  { code: "SZ", name: "Eswatini" },
  { code: "ET", name: "Éthiopie" },
  { code: "GA", name: "Gabon" },
  { code: "GM", name: "Gambie" },
  { code: "GH", name: "Ghana" },
  { code: "GN", name: "Guinée" },
  { code: "GQ", name: "Guinée équatoriale" },
  { code: "GW", name: "Guinée-Bissau" },
  { code: "KE", name: "Kenya" },
  { code: "LS", name: "Lesotho" },
  { code: "LR", name: "Liberia" },
  { code: "LY", name: "Libye" },
  { code: "MG", name: "Madagascar" },
  { code: "MW", name: "Malawi" },
  { code: "ML", name: "Mali" },
  { code: "MA", name: "Maroc" },
  { code: "MU", name: "Maurice" },
  { code: "MR", name: "Mauritanie" },
  { code: "MZ", name: "Mozambique" },
  { code: "NA", name: "Namibie" },
  { code: "NE", name: "Niger" },
  { code: "NG", name: "Nigeria" },
  { code: "UG", name: "Ouganda" },
  { code: "RW", name: "Rwanda" },
  { code: "ST", name: "Sao Tomé-et-Principe" },
  { code: "SN", name: "Sénégal" },
  { code: "SC", name: "Seychelles" },
  { code: "SL", name: "Sierra Leone" },
  { code: "SO", name: "Somalie" },
  { code: "SD", name: "Soudan" },
  { code: "SS", name: "Soudan du Sud" },
  { code: "TZ", name: "Tanzanie" },
  { code: "TD", name: "Tchad" },
  { code: "TG", name: "Togo" },
  { code: "TN", name: "Tunisie" },
  { code: "ZM", name: "Zambie" },
  { code: "ZW", name: "Zimbabwe" },
];

/** Pays d'Afrique triés par nom (ordre alphabétique français). */
export const AFRICAN_COUNTRIES: readonly Country[] = [...COUNTRIES].sort((a, b) => a.name.localeCompare(b.name, "fr"));

/** Pays proposé par défaut (siège de l'exploitant). */
export const DEFAULT_COUNTRY_CODE = "TG";

/** "TG" -> "Togo" ; un code hors de la liste (organisation plus ancienne) reste affiché tel quel. */
export function countryName(code: string): string {
  return COUNTRIES.find((c) => c.code === code.toUpperCase())?.name ?? code;
}
