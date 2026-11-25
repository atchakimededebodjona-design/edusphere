import type { Metadata } from "next";
import Link from "next/link";
import { ConsentSettingsButton } from "@/components/consent/ConsentSettingsButton";
import { LegalIdentityBlock, LegalPage } from "@/components/legal/LegalPage";
import { fetchLegalIdentity } from "@/lib/legal/identity";

export const metadata: Metadata = {
  title: "Politique de confidentialité",
  description: "Quelles données EduLinkage traite, pourquoi, combien de temps, avec qui, et comment exercer vos droits.",
  alternates: { canonical: "https://edulinkage.com/confidentialite" },
};

// Identité relue au plus une fois par heure (configuration du serveur).
export const revalidate = 3600;

export default async function PrivacyPage() {
  const identity = await fetchLegalIdentity();
  return (
    <LegalPage
      title="Politique de confidentialité"
      updated="24 novembre 2026"
      intro={
        <>
          <p>
            EduLinkage est une plateforme de gestion scolaire utilisée par des écoles, leurs enseignants et les parents
            d&apos;élèves. Cette page explique quelles données personnelles sont traitées, pourquoi, pendant combien de temps,
            avec qui elles sont partagées et comment exercer vos droits.
          </p>
          <p>
            Elle s&apos;applique au site edulinkage.com, à l&apos;application web et à l&apos;application mobile EduLinkage.
          </p>
        </>
      }
      sections={[
        {
          id: "responsable",
          title: "Qui est responsable de vos données",
          body: (
            <>
              <p>Le site et la plateforme sont exploités par :</p>
              <LegalIdentityBlock identity={identity} />
              <p>
                <strong>Les données des élèves et des familles</strong> (identité, classe, présences, notes, bulletins,
                frais, paiements, tuteurs, documents) sont saisies par chaque école, pour sa propre gestion. Pour ces
                données, <strong>l&apos;école est responsable du traitement</strong> ; EduLinkage les traite pour son
                compte, selon ses instructions, comme sous-traitant. Pour toute demande sur ces données, adressez-vous
                d&apos;abord à l&apos;école concernée.
              </p>
              <p>
                EduLinkage est responsable des données de ses propres clients (écoles, organisations, partenaires), de
                la facturation des abonnements, de la sécurité de la plateforme et de la mesure d&apos;audience du site.
              </p>
            </>
          ),
        },
        {
          id: "donnees",
          title: "Les données traitées",
          body: (
            <ul>
              <li>
                <strong>Comptes</strong> : nom, adresse e-mail, téléphone, rôle dans l&apos;école, photo d&apos;identité
                facultative, mot de passe (enregistré sous une forme chiffrée, jamais lisible).
              </li>
              <li>
                <strong>Vie scolaire</strong>, saisie par l&apos;école : identité des élèves, classes, présences, notes,
                bulletins, tuteurs, documents, frais et paiements, annonces.
              </li>
              <li>
                <strong>Abonnements</strong> : identité de l&apos;école ou de l&apos;organisation, factures, paiements
                (pour Mobile Money, les quatre derniers chiffres du numéro utilisé).
              </li>
              <li>
                <strong>Sécurité</strong> : journal des actions importantes (création de compte, changement de rôle,
                annulation de paiement…), adresse IP des tentatives de connexion pour bloquer les abus.
              </li>
              <li>
                <strong>Visite du site</strong>, seulement si vous l&apos;acceptez : pages vues, site d&apos;origine, type
                d&apos;appareil et de navigateur, pays. Aucun cookie, aucun identifiant personnel (voir la section 8).
              </li>
            </ul>
          ),
        },
        {
          id: "finalites",
          title: "Pourquoi ces données sont traitées",
          body: (
            <ul>
              <li>Fournir le service aux écoles, aux enseignants et aux parents (exécution du contrat d&apos;abonnement).</li>
              <li>Sécuriser la plateforme et prévenir les abus (intérêt légitime).</li>
              <li>Facturer les abonnements et tenir la comptabilité (obligation légale).</li>
              <li>Envoyer les e-mails et notifications utiles au service : invitation, mot de passe, annonces, rappels.</li>
              <li>Mesurer l&apos;audience du site public, avec votre accord.</li>
            </ul>
          ),
        },
        {
          id: "destinataires",
          title: "Qui peut y accéder",
          body: (
            <>
              <p>
                Dans une école, chaque compte ne voit que ce que son rôle permet (direction, comptabilité, caisse,
                enseignant, parent). Une école ne voit jamais les données d&apos;une autre école.
              </p>
              <p>EduLinkage fait appel à des prestataires techniques, chacun pour ce qui le concerne :</p>
              <ul>
                <li>hébergement du serveur : Hostinger (serveur privé loué) ;</li>
                <li>paiement Mobile Money des abonnements : PayGate Global ;</li>
                <li>envoi des e-mails : un service d&apos;envoi d&apos;e-mails ;</li>
                <li>notifications sur téléphone : le service de notification du navigateur utilisé (Google, Apple, Mozilla…).</li>
              </ul>
              <p>Aucune donnée n&apos;est vendue ni utilisée pour de la publicité.</p>
            </>
          ),
        },
        {
          id: "conservation",
          title: "Combien de temps",
          body: (
            <ul>
              <li>
                Données des écoles : pendant toute la durée de l&apos;abonnement, puis supprimées ou rendues anonymes au
                plus tard douze mois après sa fin, sauf demande contraire de l&apos;école.
              </li>
              <li>Comptes désactivés ou supprimés : effacés selon la même règle ; un compte supprimé ne peut plus se connecter.</li>
              <li>Factures et pièces comptables : dix ans, comme l&apos;exige la comptabilité.</li>
              <li>Tentatives de connexion : quelques minutes à quelques heures, le temps de bloquer un abus.</li>
              <li>Mesure d&apos;audience : statistiques sans donnée personnelle, conservées pour suivre la fréquentation.</li>
            </ul>
          ),
        },
        {
          id: "securite",
          title: "Sécurité",
          body: (
            <ul>
              <li>Connexion chiffrée (HTTPS) sur tout le site.</li>
              <li>Mots de passe chiffrés, connexion bloquée après plusieurs échecs.</li>
              <li>Séparation stricte des données entre écoles, contrôle d&apos;accès selon le rôle.</li>
              <li>Données gardées hors connexion sur un appareil : chiffrées, effacées à la déconnexion.</li>
            </ul>
          ),
        },
        {
          id: "droits",
          title: "Vos droits",
          body: (
            <>
              <p>
                Vous pouvez demander l&apos;accès à vos données, leur rectification, leur suppression, leur portabilité, ou
                vous opposer à un traitement, dans les limites prévues par la loi.
              </p>
              <p>
                Pour les données saisies par une école (élèves, notes, paiements…), adressez-vous à l&apos;école ; elle
                peut corriger ou supprimer ces données depuis EduLinkage, et nous l&apos;aidons si besoin. Pour toute autre
                demande, écrivez-nous à l&apos;adresse indiquée en section 1 : nous répondons dans un délai d&apos;un mois.
              </p>
              <p>
                Vous pouvez aussi saisir l&apos;autorité de protection des données à caractère personnel compétente au
                Togo.
              </p>
            </>
          ),
        },
        {
          id: "cookies",
          title: "Cookies et mesure d'audience",
          body: (
            <>
              <p>
                EduLinkage ne pose <strong>aucun cookie publicitaire</strong>. Pour garder votre session ouverte et
                permettre l&apos;usage hors connexion, l&apos;application enregistre des informations techniques dans
                votre navigateur : elles sont indispensables au service et effacées à la déconnexion.
              </p>
              <p>
                Sur le site public, la fréquentation est mesurée avec <strong>Umami</strong>, un outil installé sur nos
                propres serveurs : <strong>sans cookie</strong>, sans identifiant personnel, sans revente ni partage. Cette
                mesure ne démarre <strong>qu&apos;avec votre accord</strong>, et respecte le réglage « Ne pas me suivre »
                de votre navigateur. L&apos;espace connecté des écoles n&apos;est jamais mesuré.
              </p>
              <p>
                <ConsentSettingsButton className="font-semibold text-brand-blue underline underline-offset-2 hover:text-brand-text">
                  Modifier mon choix sur la mesure d&apos;audience
                </ConsentSettingsButton>
              </p>
            </>
          ),
        },
        {
          id: "mineurs",
          title: "Données des élèves mineurs",
          body: (
            <p>
              Les élèves sont en majorité mineurs. Leurs données sont saisies par l&apos;école et consultées par
              l&apos;école, leurs enseignants et leurs parents ou tuteurs disposant d&apos;un compte rattaché par
              l&apos;école. Les comptes des parents et des élèves sont créés uniquement par l&apos;administration de
              l&apos;école.
            </p>
          ),
        },
        {
          id: "modifications",
          title: "Modifications",
          body: (
            <p>
              Cette politique peut évoluer avec le service. La date de mise à jour figure en haut de la page ; en cas de
              changement important, les écoles clientes sont prévenues. Voir aussi les{" "}
              <Link href="/cgu" className="text-brand-blue underline underline-offset-2">
                conditions générales d&apos;utilisation
              </Link>{" "}
              et les{" "}
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
