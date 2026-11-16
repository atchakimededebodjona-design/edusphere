# Phase 32 — Application installable, utilisable sans connexion

- **Demande** : 2026-11-16, « il faut créer l'application pour permettre à utiliser même sans connexion ».
- **Choix de l'exploitant** (2026-11-16) :
  - **Forme** : le site actuel, rendu installable (PWA). Pas d'application Android séparée.
  - **Usages** : enseignants (appel et notes), parents (consultation), caisse (encaissement), direction (consultation).
- **Revient sur** les phases 12 à 20, qui avaient repoussé le hors connexion faute de besoin exprimé. Le besoin est maintenant exprimé. Le principe qu'elles avaient fixé reste valable : commencer par la lecture, puis l'appel, et finir par les paiements.

## 1. Découpage

| Lot | Contenu | Risque |
|---|---|---|
| **1** (cette branche) | Site installable. Tout ce qui a été ouvert avec internet reste **consultable** hors connexion, pour tous les espaces. Aucune écriture hors connexion. | Faible : lecture seule, l'API reste seule juge. |
| **2** | **Enseignants** : appel et notes saisis hors connexion, envoyés automatiquement au retour du réseau. | Moyen : doublons et conflits. Côté API, il faut une clé d'idempotence à la création d'une séance d'appel. Les présences (`uq_attendance_record`) et les notes (`uq_assessment_result`) ont déjà une clé naturelle unique. |
| **3** | **Caisse** : encaissement hors connexion. | Élevé, à décider avant de construire. Les paiements ont déjà une clé d'idempotence (`uq_payment_idempotency`), mais **le numéro de reçu est attribué par le serveur** (`RCPT-…`). Hors connexion, on ne peut remettre qu'un **reçu provisoire**. Points à trancher : valeur légale du reçu provisoire (avis du comptable), session de caisse ouverte avant la coupure, plafond, contrôle par la supervision. |

## 2. Lot 1 — ce qui change

**Le site s'installe.**
- `app/manifest.ts` : nom, icônes, démarrage sur `/dashboard`.
- `public/icons/` et `app/apple-icon.png` : le symbole officiel, redimensionné seulement.
- Dès qu'un compte est connecté, un bandeau propose « Installer » ; « Plus tard » le masque pendant 30 jours.

**Le site reste disponible sans réseau** (`sw/service-worker.js`, copié dans `public/sw.js` par `scripts/generate-sw.mjs` après `next build`).
- **Gardé à l'installation** : le code, les styles, les 49 pages sans identifiant et les fichiers de `public/`, soit 136 fichiers, environ 2,3 Mo (0,6 Mo compressé). Pour une même version, ces pages sont servies depuis l'appareil, même en ligne : elles sont identiques à celles du serveur.
- **Pages à identifiant** (fiche d'un élève, d'un enfant…) : gardées quand on les ouvre avec internet. Une page jamais ouverte affiche « Page indisponible hors connexion » (`/offline`).
- **Ce que le service worker ne touche pas** : les requêtes vers l'API (autre origine) et la navigation interne de Next.js (RSC). Sans réseau, Next.js recharge alors la page entière, servie depuis l'appareil.
- **Mise à jour** : chaque construction a sa propre version. La nouvelle version se télécharge en arrière-plan ; une fois prête, elle supprime l'ancienne. Le bandeau « Une nouvelle version d'EduLinkage est prête » propose de recharger. Le rechargement n'est jamais forcé, pour ne pas perdre une saisie en cours. `/sw.js` est servi en `Cache-Control: no-cache`.
- **Service worker inactif** : en développement, donc dans les tests e2e (`pnpm dev`), et pour un visiteur jamais connecté. Il n'est enregistré qu'après une connexion. Ensuite, sa mise à jour est demandée à chaque ouverture du site.
- **Retour en arrière** : si le serveur répond **404** pour `/sw.js` (image de secours d'avant cette phase), l'application retire le service worker, efface les fichiers gardés et recharge depuis le serveur. Sans cela, les navigateurs continueraient à servir la version gardée. Une simple coupure ne retire rien.

**Les données restent consultables** (`lib/api/client.ts`, `lib/offline/responseCache.ts`).
- Chaque **lecture** réussie de l'API est copiée dans IndexedDB, **rangée par compte**. L'identifiant du compte est lu dans le jeton ; il ne sert qu'au rangement. La copie est écrite **avant** l'affichage (1,5 s d'attente au plus) : ce qui a été vu reste consultable, même si l'application est fermée aussitôt.
- Si l'API est injoignable, la copie est servie à la place. C'est le cas quand l'appareil est hors ligne, quand aucune réponse n'arrive (wifi sans internet, forfait épuisé) ou quand la passerelle répond 502, 503 ou 504. En production, la copie est aussi servie après 10 s sans réponse ; la requête continue et met la copie à jour.
- **Aucune copie** : message « Hors connexion : ces informations n'ont pas encore été ouvertes avec internet sur cet appareil. »
- **Limites** : 5 Mo par réponse et 600 réponses par appareil ; les plus anciennes sont effacées au-delà.
- **Effacement** : toutes les copies à la **déconnexion** ; celles des **autres comptes** à chaque **connexion** (poste partagé).
- **Bandeau** : « Hors connexion » ou « Connexion au serveur impossible », avec la date de la copie la plus ancienne affichée. Au retour du réseau, « Connexion rétablie » propose d'actualiser. Quand le réseau est présent mais l'API injoignable, l'application interroge `GET /api/v1/health` toutes les 20 s.

**Écritures : rien ne change**, sauf deux messages.
- **Appareil hors ligne avant l'envoi** : `ApiError(…, 0)`, « Hors connexion : rien n'a été envoyé ».
- **Coupure pendant l'envoi** : l'erreur réseau d'origine est conservée. On ne sait pas si le serveur a reçu la demande (voir `lib/fees/cancelErrors.ts`).
- **Connexion hors ligne** : message clair. La connexion demande toujours internet.

**Sécurité.**
- Aucune donnée d'école dans le service worker : il ne garde que le site.
- Les copies de l'API ne sont lisibles que par l'application, pour le compte connecté.
- Aucun contrôle d'accès ne dépend de ces copies. L'application n'a aucun middleware serveur, et chaque écriture passe par l'API, qui applique ses permissions et le RLS.
- La durée de session est inchangée (jeton de renouvellement de 30 jours). Hors connexion, aucun jeton n'est envoyé.

## 3. Vérifications

- `pnpm test:config` : `scripts/generate-sw.test.mjs`. Il vérifie la liste des fichiers gardés : pages statiques, code, fichiers publics ; sans la 404 interne, sans `sw.js` ni fichiers cachés ; chemins Windows ; version de build sûre.
- **Hors connexion de bout en bout** (2026-11-16, build de production, `next start`, API simulée, Chromium par Playwright) :
  - service worker actif, 136 fichiers gardés ;
  - tableau de bord enseignant rouvert hors connexion, avec ses chiffres, le logo de l'école et le bandeau daté ;
  - navigation par le menu vers une page déjà ouverte ;
  - message explicite pour une page jamais ouverte, page de repli pour une page à identifiant ;
  - bandeau « Connexion rétablie » au retour du réseau ;
  - copies effacées à la déconnexion ;
  - message clair pour une connexion hors ligne ;
  - page École (administration) et son logo hors connexion ; envoi d'un logo hors ligne refusé sans requête ;
  - mise à jour d'une version à l'autre : bandeau affiché, page ouverte utilisable, seule la nouvelle version gardée, nouvelle version consultable hors connexion ;
  - retour en arrière : service worker gardé pendant une coupure ; service worker et fichiers retirés quand `/sw.js` répond 404, puis site servi normalement ;
  - aucune erreur de page ;
  - scénario hors connexion réussi deux fois de suite après la dernière modification.
- **Non vérifié** :
  - Safari et iPhone : pas d'invite d'installation (ajout manuel par Partager → « Sur l'écran d'accueil ») ; stockage moins durable.
  - Un vrai téléphone Android : à faire après le déploiement.
