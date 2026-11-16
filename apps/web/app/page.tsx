import type { Metadata } from "next";
import { LandingNav } from "@/components/landing/LandingNav";
import { Hero } from "@/components/landing/Hero";
import { AudienceSection } from "@/components/landing/AudienceSection";
import { ProblemSection } from "@/components/landing/ProblemSection";
import { FeatureGrid } from "@/components/landing/FeatureGrid";
import { ParentPortalSection } from "@/components/landing/ParentPortalSection";
import { AfricaSection } from "@/components/landing/AfricaSection";
import { ProductPreview } from "@/components/landing/ProductPreview";
import { TrustSection } from "@/components/landing/TrustSection";
import { FinalCta } from "@/components/landing/FinalCta";
import { PartnerSection } from "@/components/landing/PartnerSection";
import { PricingSection } from "@/components/landing/PricingSection";
import { LandingFooter } from "@/components/landing/LandingFooter";
import { fetchPublicPricing } from "@/lib/landing/fetchPricing";

const TITLE = "EduLinkage — Une école, des liens, un avenir.";
const DESCRIPTION =
  "Élèves, présences, notes, bulletins, frais scolaires et caisse : EduLinkage réunit la gestion de votre école. Premier trimestre offert, paiement par Mobile Money.";

// Métadonnées propres à cette route (landing page publique) — fusionnées avec, et prioritaires
// sur, les métadonnées par défaut du layout racine pour cette seule page. Le layout racine et son
// titre/description par défaut restent inchangés pour toutes les autres routes.
export const metadata: Metadata = {
  title: TITLE,
  description: DESCRIPTION,
  alternates: {
    canonical: "https://edulinkage.com/",
  },
  openGraph: {
    title: TITLE,
    description: DESCRIPTION,
    url: "https://edulinkage.com/",
    siteName: "EduLinkage",
    locale: "fr_FR",
    type: "website",
    images: ["/branding/edulinkage-full.png"],
  },
  twitter: {
    card: "summary_large_image",
    title: TITLE,
    description: DESCRIPTION,
    images: ["/branding/edulinkage-full.png"],
  },
};

// Page régénérée au plus toutes les 5 minutes (même durée que le cache des tarifs).
export const revalidate = 300;

// Landing page publique — "/". Seul appel à l'API : les tarifs publics, lus côté serveur
// (lib/landing/fetchPricing.ts). Si l'API est indisponible, la page s'affiche quand même, avec
// « tarifs sur demande ». Les compositions de type "dashboard"/"portail parent" restent des
// illustrations statiques (DashboardMockup, PhoneMockup, ProductPreview), jamais des données réelles.
export default async function LandingPage() {
  const pricing = await fetchPublicPricing();
  return (
    <>
      <LandingNav />
      <main>
        <Hero />
        <AudienceSection />
        <ProblemSection />
        <FeatureGrid />
        <ParentPortalSection />
        <PricingSection pricing={pricing} />
        <ProductPreview />
        <AfricaSection />
        <TrustSection />
        <PartnerSection />
        <FinalCta />
      </main>
      <LandingFooter />
    </>
  );
}
