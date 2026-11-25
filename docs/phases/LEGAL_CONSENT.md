# Pages juridiques, bandeau de consentement et mesure d'audience — 2026-11-24

Ce document correspond à la troisième PR de la demande du 2026-11-24 (voir `SITE_QUALITY.md`). Choix de l'exploitant :
- identité de l'entreprise lue dans la configuration du serveur ;
- CGU et CGV ;
- Umami hébergé sur le serveur.

## Pages

| Adresse | Contenu |
|---|---|
| `/confidentialite` | Responsable, données traitées, finalités, destinataires, durées, sécurité, droits, cookies et mesure d'audience, élèves mineurs |
| `/cgu` | Éditeur, accès, compte, bon usage, disponibilité, propriété, suspension, droit applicable |
| `/cgv` | Vendeur, offre, premier trimestre offert, prix, facturation, paiement, échéance, responsabilité, droit applicable |

- **Identité de l'entreprise** :
  - nouvelle route `GET /api/v1/public/legal-identity`, sans authentification ni écriture, limitée par IP comme les tarifs publics ;
  - elle lit les réglages `BILLING_*` du serveur, les mêmes que sur les reçus ;
  - les pages la lisent côté serveur, au plus une fois par heure. Un champ vide n'est pas affiché ;
  - **e-mail** : choix de l'exploitant du 2026-11-25, les pages affichent toujours l'adresse de contact du site (`lib/landing/contact.ts`), pas `BILLING_EMAIL`. Celle-ci reste celle des reçus.
- **Liens** : colonne « Informations légales » dans le pied de page de l'accueil, liens en bas des pages d'accès (`AuthFrame`), sitemap.
- **Contenu vérifié dans le code** :
  - le paiement crée une période qui commence le jour même, ou le lendemain de la dernière période ;
  - une seule facture ouverte par école ;
  - validité de 30 jours ;
  - devis au-delà de certains effectifs ;
  - rappels d'échéance ;
  - aucune reconduction automatique.

### À faire relire par un juriste avant de s'y engager

Les textes sont des modèles. Les engagements suivants n'ont pas été décidés ailleurs :
- délai de suppression des données de l'école : 12 mois après la fin de l'abonnement ;
- réponse aux demandes en un mois ;
- conservation des pièces comptables : 10 ans ;
- non-remboursement d'une période commencée ;
- responsabilité limitée au montant de la période en cours ;
- tribunaux de Lomé.

Il reste aussi à nommer le prestataire d'envoi des e-mails.

### À renseigner dans le `.env` du serveur

Pour que les pages affichent l'identité complète : `BILLING_LEGAL_NAME`, `BILLING_LEGAL_FORM`, `BILLING_ADDRESS`, `BILLING_RCCM`, `BILLING_NIF`, `BILLING_PHONE`. Ce sont les mêmes champs que pour les reçus. `BILLING_EMAIL` n'est pas affiché, voir plus haut. Il faut ensuite redémarrer l'API ; les pages se mettent à jour dans l'heure.

## Bandeau et mesure d'audience

- **Configuration** (`apps/web/config/analytics.js`) :
  - deux variables figées au build, `NEXT_PUBLIC_UMAMI_SRC` et `NEXT_PUBLIC_UMAMI_WEBSITE_ID` ;
  - toutes deux absentes : aucune mesure, aucun bandeau, CSP inchangée ;
  - une seule renseignée, ou une valeur invalide (HTTPS obligatoire, identifiant UUID) : **le build échoue** ;
  - 5 tests ont été ajoutés à `test:config`.
- **CSP** : l'origine d'Umami est ajoutée à `script-src` et à `connect-src`, et à rien d'autre.
- **Bandeau** (`components/consent/AnalyticsConsent.tsx`) :
  - il apparaît sur les pages publiques tant qu'aucun choix n'est fait ; « Refuser » et « Accepter » ont le même style, côte à côte ;
  - le script Umami n'est chargé qu'après « Accepter », avec « Ne pas me suivre » respecté (`data-do-not-track`) ;
  - **suivi automatique d'Umami désactivé** (`data-auto-track="false"`, correctif du 2026-11-25). Sinon, une fois chargé, il suivait aussi les navigations sans rechargement (accueil, connexion, tableau de bord). Le site enregistre lui-même une page vue à chaque arrivée sur une page publique, et seulement là ;
  - le choix est gardé sur l'appareil ;
  - « Mesure d'audience » (pied de page) et « Modifier mon choix » (page de confidentialité) rouvrent le bandeau ;
  - un refus après acceptation arrête la mesure dès le rechargement de la page.
- **Installation d'Umami sur le serveur** : `docs/deployment/UMAMI.md`. Service `umami` du fichier `docker-compose.yml`, profil `analytics` : il ne démarre jamais avec les commandes habituelles.
