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
import { LandingFooter } from "@/components/landing/LandingFooter";

const TITLE = "EduLinkage — Une école, des liens, un avenir.";
const DESCRIPTION =
  "EduLinkage est une plateforme moderne de gestion scolaire qui connecte écoles, enseignants, parents et élèves.";

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

// Landing page publique — "/". Ne dépend d'aucun appel API : reste fonctionnelle même si le
// backend est momentanément indisponible (voir consigne "DONNÉES"). Toutes les compositions de
// type "dashboard"/"portail parent" sont des illustrations statiques (DashboardMockup,
// PhoneMockup, ProductPreview), jamais des données réelles.
export default function LandingPage() {
  return (
    <>
      <LandingNav />
      <main>
        <Hero />
        <AudienceSection />
        <ProblemSection />
        <FeatureGrid />
        <ParentPortalSection />
        <AfricaSection />
        <ProductPreview />
        <TrustSection />
        <FinalCta />
      </main>
      <LandingFooter />
    </>
  );
}
