import type { PublicPricing } from "@/lib/landing/pricing.mjs";

// Tarifs publics de la page d'accueil, lus CÔTÉ SERVEUR (jamais depuis le navigateur) et gardés en
// cache 5 minutes par Next.js. La page reste affichable sans l'API : en cas d'échec, de délai
// dépassé ou d'absence de grille active, elle indique « tarifs sur demande ».
const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? (process.env.NODE_ENV === "production" ? "" : "http://localhost:8000");

export const PRICING_REVALIDATE_SECONDS = 300;

export async function fetchPublicPricing(): Promise<PublicPricing | null> {
  if (!API_URL) return null;
  try {
    const response = await fetch(`${API_URL}/api/v1/public/subscription-pricing`, {
      next: { revalidate: PRICING_REVALIDATE_SECONDS },
      signal: AbortSignal.timeout(4000),
    });
    if (!response.ok) return null;
    const data = (await response.json()) as PublicPricing;
    if (!Array.isArray(data?.tiers) || !Array.isArray(data?.periods) || data.periods.length === 0) return null;
    return data;
  } catch {
    return null;
  }
}
