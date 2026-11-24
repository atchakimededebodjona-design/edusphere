import type { Metadata } from "next";
import Link from "next/link";
import { LegalIdentityBlock, LegalPage } from "@/components/legal/LegalPage";
import { fetchLegalIdentity } from "@/lib/legal/identity";

export const metadata: Metadata = {
  title: "Conditions générales d'utilisation",
  description: "Règles d'utilisation de la plateforme EduLinkage par les écoles, les enseignants et les parents.",
  alternates: { canonical: "https://edulinkage.com/cgu" },
};

export const revalidate = 3600;

export default async function TermsOfUsePage() {
  const identity = await fetchLegalIdentity();
  return (
    <LegalPage
      title="Conditions générales d'utilisation"
      updated="24 novembre 2026"
      intro={
        <p>
          Les présentes conditions encadrent l&apos;utilisation de la plateforme EduLinkage (site web, application web et
          application mobile) par toute personne disposant d&apos;un compte : personnel d&apos;une école, enseignant,
          parent ou partenaire. Utiliser EduLinkage, c&apos;est les accepter.
        </p>
      }
      sections={[
        {
          id: "editeur",
          title: "Éditeur du service",
          body: <LegalIdentityBlock identity={identity} />,
        },
        {
          id: "acces",
          title: "Accès au service",
          body: (
            <>
              <p>
                Il n&apos;existe pas d&apos;inscription libre. Les comptes sont créés par l&apos;administration de
                l&apos;école ; ceux des parents et des élèves uniquement par l&apos;administrateur de l&apos;école.
                Chaque compte n&apos;accède qu&apos;aux informations de son rôle et de son école.
              </p>
              <p>
                L&apos;accès demande une connexion internet ; certaines fonctions (appel, notes, caisse, consultation)
                restent utilisables sans internet sur un appareil déjà connecté, puis se synchronisent au retour du
                réseau.
              </p>
            </>
          ),
        },
        {
          id: "compte",
          title: "Votre compte",
          body: (
            <ul>
              <li>Votre mot de passe est personnel : ne le communiquez à personne et choisissez-le assez long.</li>
              <li>Prévenez l&apos;administration de votre école si vous pensez que votre compte est utilisé par un tiers.</li>
              <li>
                Sur un appareil partagé, déconnectez-vous après usage : la déconnexion efface aussi les données gardées
                hors connexion.
              </li>
            </ul>
          ),
        },
        {
          id: "usage",
          title: "Bon usage",
          body: (
            <>
              <p>Vous vous engagez à utiliser EduLinkage pour la vie scolaire, de bonne foi, et notamment à ne pas :</p>
              <ul>
                <li>saisir des informations fausses, injurieuses ou sans rapport avec la scolarité ;</li>
                <li>tenter d&apos;accéder aux données d&apos;un autre compte ou d&apos;une autre école ;</li>
                <li>perturber le service (envois massifs, robots, contournement des protections).</li>
              </ul>
              <p>
                L&apos;école reste responsable des informations qu&apos;elle saisit et de l&apos;usage qu&apos;en font ses
                comptes.
              </p>
            </>
          ),
        },
        {
          id: "disponibilite",
          title: "Disponibilité",
          body: (
            <p>
              EduLinkage fait le nécessaire pour que le service soit disponible en permanence, mais ne peut garantir
              l&apos;absence d&apos;interruption : maintenance, mises à jour, panne d&apos;un prestataire ou du réseau. Les
              interventions prévues sont, dans la mesure du possible, faites en dehors des heures de cours.
            </p>
          ),
        },
        {
          id: "propriete",
          title: "Propriété intellectuelle",
          body: (
            <p>
              La plateforme, son nom, son logo et ses contenus appartiennent à leur éditeur. Les données saisies par une
              école restent les siennes : elle les consulte à tout moment pendant son abonnement et peut en demander une
              copie.
            </p>
          ),
        },
        {
          id: "suspension",
          title: "Suspension d'un compte",
          body: (
            <p>
              L&apos;administration de l&apos;école peut désactiver un compte de son école à tout moment. EduLinkage peut
              suspendre un compte qui enfreint ces conditions ou met en danger la sécurité du service, en prévenant
              l&apos;école concernée.
            </p>
          ),
        },
        {
          id: "donnees",
          title: "Données personnelles",
          body: (
            <p>
              Le traitement des données personnelles est décrit dans la{" "}
              <Link href="/confidentialite" className="text-brand-blue underline underline-offset-2">
                politique de confidentialité
              </Link>
              .
            </p>
          ),
        },
        {
          id: "droit",
          title: "Droit applicable",
          body: (
            <p>
              Ces conditions sont soumises au droit togolais. En cas de différend, une solution amiable est recherchée en
              priorité ; à défaut, les tribunaux compétents de Lomé seront saisis. Les écoles abonnées sont aussi liées par
              les{" "}
              <Link href="/cgv" className="text-brand-blue underline underline-offset-2">
                conditions générales de vente
              </Link>
              .
            </p>
          ),
        },
      ]}
    />
  );
}
