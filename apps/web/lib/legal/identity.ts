// 2026-11-24 — identité de l'entreprise pour les pages juridiques, lue CÔTÉ SERVEUR dans l'API
// (`GET /public/legal-identity`, configuration BILLING_* du serveur, la même que sur les reçus) et gardée
// en cache une heure. Rien de l'entreprise n'est écrit dans le code public. Sans API, les pages restent
// lisibles : seul le nom commercial s'affiche.
const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? (process.env.NODE_ENV === "production" ? "" : "http://localhost:8000");

export type LegalIdentity = {
  trade_name: string;
  legal_name: string;
  legal_form: string;
  address: string;
  nif: string;
  rccm: string;
  phone: string;
  email: string;
};

const FALLBACK: LegalIdentity = {
  trade_name: "EduLinkage",
  legal_name: "",
  legal_form: "",
  address: "",
  nif: "",
  rccm: "",
  phone: "",
  email: "",
};

export async function fetchLegalIdentity(): Promise<LegalIdentity> {
  if (!API_URL) return FALLBACK;
  try {
    const response = await fetch(`${API_URL}/api/v1/public/legal-identity`, {
      next: { revalidate: 3600 },
      signal: AbortSignal.timeout(4000),
    });
    if (!response.ok) return FALLBACK;
    const data = (await response.json()) as Partial<LegalIdentity>;
    return { ...FALLBACK, ...Object.fromEntries(Object.entries(data).filter(([, v]) => typeof v === "string")) };
  } catch {
    return FALLBACK;
  }
}
