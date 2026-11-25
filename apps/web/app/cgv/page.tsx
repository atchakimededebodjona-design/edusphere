import type { Metadata } from "next";
import Link from "next/link";
import { LegalIdentityBlock, LegalPage } from "@/components/legal/LegalPage";
import { fetchLegalIdentity } from "@/lib/legal/identity";

export const metadata: Metadata = {
  title: "Conditions générales de vente",
  description: "Abonnements EduLinkage des écoles : offre, prix, premier trimestre offert, facturation, paiement, fin d'abonnement.",
  alternates: { canonical: "https://edulinkage.com/cgv" },
};

export const revalidate = 3600;

export default async function TermsOfSalePage() {
  const identity = await fetchLegalIdentity();
  return (
    <LegalPage
      title="Conditions générales de vente"
      updated="24 novembre 2026"
      intro={
        <p>
          Les présentes conditions régissent les abonnements à EduLinkage souscrits par les écoles et les organisations
          scolaires (le « client »). Elles complètent les{" "}
          <Link href="/cgu" className="text-brand-blue underline underline-offset-2">
            conditions générales d&apos;utilisation
          </Link>
          . Toute demande de facture vaut acceptation des présentes conditions.
        </p>
      }
      sections={[
        {
          id: "vendeur",
          title: "Le vendeur",
          body: <LegalIdentityBlock identity={identity} />,
        },
        {
          id: "offre",
          title: "L'offre",
          body: (
            <>
              <p>
                L&apos;abonnement donne accès à toutes les fonctions de la plateforme pour l&apos;école : élèves,
                présences, notes, bulletins, frais, caisse, annonces, espaces enseignants et parents, usage hors connexion.
              </p>
              <p>
                Il se souscrit par école, pour une durée de trois, six ou douze mois. Son prix dépend de l&apos;effectif
                d&apos;élèves actifs, selon la grille tarifaire en vigueur, publiée sur la{" "}
                <Link href="/#tarifs" className="text-brand-blue underline underline-offset-2">
                  page des tarifs
                </Link>
                .
              </p>
            </>
          ),
        },
        {
          id: "essai",
          title: "Premier trimestre offert",
          body: (
            <p>
              Chaque nouvelle école bénéficie d&apos;un premier trimestre gratuit, sans obligation de souscrire ensuite. À
              la fin de ce trimestre, la poursuite du service suppose le paiement d&apos;une période d&apos;abonnement.
            </p>
          ),
        },
        {
          id: "prix",
          title: "Prix",
          body: (
            <>
              <p>
                Les prix sont exprimés en francs CFA (FCFA), hors taxes. Selon le régime fiscal du vendeur, la TVA peut ne
                pas être applicable : la facture l&apos;indique.
              </p>
              <p>
                Le prix d&apos;une facture est figé à son émission : un changement ultérieur de la grille ne la modifie pas.
                Au-delà de certains effectifs, le prix est établi sur devis.
              </p>
            </>
          ),
        },
        {
          id: "facturation",
          title: "Facturation",
          body: (
            <p>
              L&apos;école demande sa facture depuis la page « Abonnement » de son espace. La facture indique la période,
              l&apos;effectif pris en compte et le montant ; elle reste valable trente jours. Une seule facture peut être
              ouverte à la fois. Un reçu est disponible après paiement.
            </p>
          ),
        },
        {
          id: "paiement",
          title: "Paiement",
          body: (
            <>
              <p>Le paiement se fait en une fois, pour le montant exact de la facture :</p>
              <ul>
                <li>par Mobile Money (Flooz ou T-Money), directement depuis l&apos;espace de l&apos;école, lorsque ce moyen est proposé ;</li>
                <li>par virement bancaire, ou en espèces auprès du vendeur, contre reçu.</li>
              </ul>
              <p>
                La période payée commence le jour du paiement, ou le lendemain de la fin de la période en cours (trimestre
                offert compris) : aucun jour n&apos;est perdu.
              </p>
            </>
          ),
        },
        {
          id: "echeance",
          title: "Échéance et fin d'abonnement",
          body: (
            <>
              <p>
                L&apos;abonnement n&apos;est pas reconduit automatiquement. Avant l&apos;échéance, l&apos;école reçoit des
                rappels pour renouveler sa période ; elle peut aussi ne pas renouveler, sans formalité.
              </p>
              <p>
                Sauf accord écrit entre les parties, une période commencée n&apos;est pas remboursée. À la fin de
                l&apos;abonnement, l&apos;école peut demander une copie de ses données ; elles sont ensuite traitées comme
                décrit dans la{" "}
                <Link href="/confidentialite#conservation" className="text-brand-blue underline underline-offset-2">
                  politique de confidentialité
                </Link>
                .
              </p>
            </>
          ),
        },
        {
          id: "responsabilite",
          title: "Responsabilité",
          body: (
            <p>
              Le vendeur s&apos;engage à fournir le service avec soin et à le maintenir disponible, sans pouvoir garantir
              l&apos;absence de toute interruption. Sa responsabilité est limitée au montant payé pour la période en cours.
              L&apos;école reste responsable des informations qu&apos;elle saisit.
            </p>
          ),
        },
        {
          id: "droit",
          title: "Droit applicable et litiges",
          body: (
            <p>
              Les présentes conditions sont soumises au droit togolais et aux actes uniformes de l&apos;OHADA. En cas de
              différend, les parties recherchent d&apos;abord une solution amiable ; à défaut, les tribunaux compétents de
              Lomé sont saisis.
            </p>
          ),
        },
      ]}
    />
  );
}
