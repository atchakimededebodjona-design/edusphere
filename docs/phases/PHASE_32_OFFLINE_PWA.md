# Phase 32 — Application installable, utilisable sans connexion

- **Demande** : 2026-11-16, « il faut créer l'application pour permettre à utiliser même sans connexion ».
- **Choix de l'exploitant** (2026-11-16) :
  - **Forme** : le site actuel, rendu installable (PWA). Pas d'application Android séparée.
  - **Usages** : enseignants (appel et notes), parents (consultation), caisse (encaissement), direction (consultation).
- **Revient sur** les phases 12 à 20, qui avaient repoussé le hors connexion faute de besoin exprimé. Le besoin est maintenant exprimé. Le principe qu'elles avaient fixé reste valable : commencer par la lecture, puis l'appel, et finir par les paiements.

## 1. Découpage

| Lot | Contenu | Risque |
|---|---|---|
| **1** (en production le 2026-11-16, PR #44) | Site installable. Tout ce qui a été ouvert avec internet reste **consultable** hors connexion, pour tous les espaces. Aucune écriture hors connexion. | Faible : lecture seule, l'API reste seule juge. |
| **2** (en production le 2026-11-16, PR #45, §4) | **Enseignants** : appel et notes saisis hors connexion, envoyés automatiquement au retour du réseau. | Moyen : doublons et conflits. Côté API, il faut une clé d'idempotence à la création d'une séance d'appel. Les présences (`uq_attendance_record`) et les notes (`uq_assessment_result`) ont déjà une clé naturelle unique. |
| **3** (en production le 2026-11-17, PR #47, §5) | **Caisse** : encaissement en espèces hors connexion, avec reçu provisoire. | Élevé. Les paiements ont déjà une clé d'idempotence (`uq_payment_idempotency`), mais **le numéro de reçu est attribué par le serveur** (`RCPT-…`). Hors connexion, on ne peut remettre qu'un **reçu provisoire**. Décisions de l'exploitant au §5. |
| **Connexion** (branche `feat/offline-login`, §6) | **Se reconnecter sans internet** sur un appareil où le compte s'est déjà connecté avec internet. | Moyen : sécurité de l'appareil. Les données restent chiffrées par le mot de passe. Le site seul, sans migration. |

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
  - Un vrai téléphone Android : à faire après le déploiement. (Fait le 2026-11-16 par l'exploitant : « ça marche sur téléphone ».)

## 4. Lot 2 — appel et notes sans connexion

- **Demande** : 2026-11-16, « ça marche sur téléphone, commence le lot 2 ».
- **Migration** : `0032`, additive.

**API (migration `0032`).**
- **Colonnes** : `attendance_sessions.idempotency_key` et `assessments.idempotency_key` (VARCHAR(128), NULL).
- **Unicité** : sur `(school_id, idempotency_key)` (`uq_attendance_session_idempotency`, `uq_assessment_idempotency`).
- **Création** : `POST /attendance-sessions` et `POST /assessments` acceptent une `idempotency_key` facultative, de 8 à 128 caractères.
  - Même clé, mêmes données : l'élément déjà créé est renvoyé.
  - Même clé, autres données : refus 409.
  - Sans clé : comportement inchangé.
- **Ordre des contrôles** : la clé est cherchée **après** le contrôle d'accès, dans l'école de la classe.
- **Envois simultanés** : `IntegrityError`, puis rollback, contexte RLS repositionné et relecture. C'est le motif des paiements (`fees/service.py::record_payment`) et des mouvements de caisse.
- **Déjà renvoyables sans risque** : les présences et les notes, mises à jour élève par élève. Une même absence renvoyée ne redéclenche pas le courriel aux familles (`maybe_notify_absence`).
- **Compatibilité** : l'ancienne API fonctionne avec la base migrée (colonnes facultatives). Un retour en arrière ne demande donc que les anciennes images, sans annuler la migration.

**Site.**
- **Boîte d'envoi** (`lib/offline/outbox.ts`, magasin `outbox` d'IndexedDB, base en version 2) :
  - une saisie par compte et par cible ; réenregistrer remplace (la dernière saisie gagne) ;
  - une séance ou une évaluation créée sur l'appareil porte sa clé d'idempotence (`offline-<uuid>`).
- **Envoi** (`lib/offline/sync.ts`) :
  - Chaque « Créer la session », « Enregistrer l'appel », « Créer » (évaluation) et « Enregistrer les notes » garde d'abord la saisie sur l'appareil, puis l'envoie aussitôt si possible.
  - Avec internet, rien ne change à l'écran. Sans réponse, la saisie reste en attente, et c'est aussi le cas d'une coupure **pendant** l'envoi : la renvoyer est sans risque.
  - Envoi automatique à l'ouverture, au retour du réseau, puis toutes les minutes. « Envoyer maintenant » est proposé dans le bandeau.
  - Un seul envoi à la fois, y compris entre onglets (Web Locks).
- **Refus du serveur** :
  - **À l'enregistrement en ligne** : message immédiat, rien n'est gardé.
  - **Lors d'un envoi différé** : la saisie est gardée « refusée », avec la raison traduite (séance verrouillée, bulletin publié, élève retiré, date hors période…). L'enseignant choisit « Réessayer » ou « Supprimer » ; jamais de suppression silencieuse.
  - **Création réussie, enregistrement refusé** : la saisie refusée vise alors la séance (ou l'évaluation) réellement créée, qui n'apparaît qu'une fois à l'écran.
- **Écrans** (`teacher/attendance`, `teacher/grades`) :
  - les séances et évaluations créées sur l'appareil sont listées « en attente d'envoi » ;
  - un appel ou des notes en attente priment sur la version du serveur à l'ouverture ;
  - l'enregistrement reste bloqué tant que la feuille de la séance ouverte n'est pas chargée. Avant, une erreur de chargement laissait affichée la feuille précédente, qu'on pouvait enregistrer sur la mauvaise séance.
  - Les notes sont contrôlées entre 0 et la note maximale avant l'envoi.
- **Déconnexion** : avertissement s'il reste des saisies non envoyées (les trois barres). Si on confirme, les saisies de ce compte sont retirées de l'appareil. Les saisies d'autres comptes sur un poste partagé ne sont jamais envoyées avec une autre session.

**Vérifications (2026-11-16).**
- **API** :
  - `tests/test_offline_idempotency.py`, 9 tests : renvoi sans doublon, clé réutilisée refusée, création sans clé inchangée, clé propre à chaque école, parcours réel d'un enseignant affecté envoyant deux fois séance et appel, clé trop courte refusée ;
  - non exécutés en local (pas de PostgreSQL) : ruff, mypy et collecte pytest seulement. Ils tournent dans la CI.
- **Site** : vérification des types, analyse du code, `test:config`.
- **Parcours de bout en bout** : build de production, API simulée **avec état**, Chromium. 24 vérifications :
  - séance, appel et notes saisis hors connexion, retrouvés après rechargement ;
  - note au-dessus du maximum arrêtée avant l'envoi ;
  - rien n'arrive au serveur pendant la coupure ;
  - au retour du réseau : une séance par saisie, l'absence reçue, une évaluation et ses notes, bandeau vidé ;
  - séance verrouillée : refus affiché avec sa raison, une seule ligne, suppression volontaire ;
  - avertissement à la déconnexion, annulation possible, saisies retirées après confirmation ;
  - aucune erreur de page.
- **Coupure pendant l'envoi** (le serveur enregistre la séance mais la réponse se perd) : la séance est renvoyée avec la même clé, il n'y a aucun doublon, et l'appel est rattaché à la bonne séance.
- **Passage de la base locale de la version 1 (lot 1) à la version 2** : copies existantes conservées, boîte d'envoi utilisable.

## 5. Lot 3 — caisse sans connexion

- **Demande** : 2026-11-17.
- **Décisions de l'exploitant** (2026-11-17) :
  - **Reçu** : un reçu PROVISOIRE (`PROV-` + 10 caractères) est remis au payeur. Le reçu officiel (`RCPT-…`) arrive après l'envoi et nomme le reçu provisoire qu'il remplace. Faire valider la formule par le comptable reste conseillé.
  - **Élèves** : la liste des élèves de l'école qui ont encore des frais à payer est gardée sur l'appareil du caissier quand sa caisse est ouverte. **Exception voulue** à la règle des lots 1 et 2 de la caisse scolaire (« jamais une liste complète des élèves ») : sans elle, rien ne pourrait être encaissé au début d'une coupure.
  - **Contrôle** : les encaissements faits sans internet portent la mention « hors connexion » avec l'heure réelle d'encaissement, visible par la supervision.
  - **Plafond** : aucun.
- **Migration** : `0033`, additive.

**API (migration `0033`).**
- **Colonnes** `payments.offline_collected_at` (TIMESTAMPTZ) et `payments.provisional_receipt_number` (VARCHAR(32)), NULL pour tout paiement fait avec internet.
  - Contraintes : renseignées ensemble ou pas du tout (`ck_payment_offline_fields_together`) ; reçu provisoire unique par école (`uq_payment_provisional_receipt_number`).
- **`POST /payments`** accepte, pour un encaissement fait sans internet :
  - `offline_collected_at`, avec fuseau, jamais dans le futur (10 min de tolérance) ;
  - `provisional_receipt_number` ;
  - `cash_session_id` : la caisse ouverte au moment de l'encaissement.
  - Espèces uniquement, champs ensemble, sinon refus 422.
  - **Caisse** : si cette caisse n'est plus ouverte (clôturée entre-temps, par exemple par la supervision), refus 409. Le paiement n'est jamais rattaché en silence à une autre caisse, dont le comptage serait faussé.
  - **Renvoi** avec la même clé d'idempotence : le paiement déjà créé est rendu, même après la clôture.
- **Reçu PDF officiel** : ligne « Encaissé sans connexion internet le … — remplace le reçu provisoire n° PROV-… », à l'heure de l'école. Le journal d'audit le mentionne aussi.
- **`GET /cashier/offline-roster`** : élèves ayant encore des frais à payer, avec leurs frais.
  - Même calcul que `GET /students/{id}/financial-summary`, projection minimale (matricule, nom, classe).
  - Mêmes droits que la recherche de la caisse (`fees.read` et `payments.manage` dans l'école), et **seulement avec une caisse ouverte** par l'appelant (409 sinon).
  - Limite : 5 000 élèves (`truncated`).
- **Mention dans les vues** : `offline_collected_at` et `provisional_receipt_number` sont ajoutés au paiement, au journal du jour du caissier et au détail d'une caisse.
- **Compatibilité** : l'ancienne API fonctionne avec la base migrée (colonnes facultatives). Un retour en arrière ne demande que les anciennes images, sans annuler la migration.

**Site.**
- **Liste gardée** : téléchargée à l'ouverture de la page Caisse, caisse ouverte, puis toutes les 10 minutes. Elle est copiée comme toute lecture (lot 1), rangée par compte et effacée à la déconnexion.
- **Sans internet** :
  - la recherche se fait dans la liste gardée ;
  - la situation de l'élève vient de la copie la plus récente (liste ou situation déjà ouverte), **diminuée des encaissements encore en attente** sur l'appareil : deux encaissements hors connexion ne peuvent pas viser le même reste à payer.
- **Encaissement** (caisse ouverte connue de l'appareil) : gardé dans la boîte d'envoi (`payment:<clé>`), puis envoyé aussitôt.
  - **Serveur joignable** : l'encaissement part comme avant, sans mention.
  - **Serveur injoignable**, y compris une coupure pendant l'envoi : écran « Encaissement gardé sur cet appareil » et reçu provisoire, imprimable seul (`printProvisionalReceipt`). L'envoi différé ajoute la mention « hors connexion » et la caisse d'origine.
  - Le panneau suit l'état réel : en attente, envoyé (avec le reçu officiel), ou refusé.
- **Refus à l'envoi différé** (solde changé, caisse clôturée entre-temps…) : l'encaissement reste affiché, avec la raison et la consigne « l'argent a été reçu ; régularisez, puis supprimez la ligne ». Jamais de suppression silencieuse.
- **Garde-fous** :
  - **déconnexion bloquée** tant qu'un encaissement n'est pas accepté par le serveur ; l'effacement de la boîte d'envoi à la déconnexion épargne de toute façon les encaissements ;
  - **comptage et clôture de « Ma caisse » bloqués** tant qu'un encaissement attend, ou qu'un refus n'est pas régularisé.
- **Historique du jour** : encaissements en attente en tête (reçu provisoire à réimprimer), puis mention « Hors connexion · reçu provisoire PROV-… » sur les paiements envoyés. Même mention dans « Ma caisse ».
- **Supervision**, détail d'une caisse : tableau « Encaissements faits sans internet » (reçu officiel, reçu provisoire, heure d'encaissement, heure d'arrivée au serveur, élève, montant).
- **Limite connue** : si le serveur a enregistré l'encaissement mais que sa réponse s'est perdue, le payeur a reçu un reçu provisoire, et le paiement, enregistré comme un encaissement ordinaire, ne le mentionne pas. Le renvoi rend ce paiement sans doublon, et le panneau de la caisse affiche le reçu officiel.

**Vérifications (2026-11-17).**
- **API** :
  - `tests/test_offline_cash_payments.py`, 17 tests : encaissement marqué et compté dans sa caisse, renvoi après clôture sans doublon, refus si la caisse n'est plus ouverte, 9 cas de validation, reçu provisoire unique, reçu PDF officiel, liste gardée (contenu, calcul, droits, caisse ouverte exigée, isolation) ;
  - en local : ruff, mypy, collecte pytest, et les deux tests sans base (reçu PDF, validation du paiement) exécutés et réussis. Les autres tournent dans la CI.
- **Site** : vérification des types, analyse du code, `test:config`.
- **Parcours de bout en bout** : build de production, API simulée avec état, Chromium. 36 vérifications :
  - encaissement en ligne inchangé ;
  - hors connexion : recherche dans la liste gardée, reste à payer correct, reçu provisoire numéroté, impression du reçu seul en haut de page ;
  - second encaissement du même élève : reste diminué de l'encaissement en attente ;
  - déconnexion bloquée, clôture de « Ma caisse » bloquée ;
  - au retour du réseau : envoi avec la mention, historique et supervision à jour ;
  - coupure pendant l'envoi : aucun doublon, reçu officiel affiché ;
  - caisse clôturée entre-temps : refus affiché avec sa raison, suppression volontaire ;
  - écran de téléphone sans défilement horizontal ;
  - aucune erreur de page.
- **Non-régression** : parcours des lots 1 et 2 (consultation, appel et notes, coupure, passage de la base locale, bandeaux du bas), tous réussis.

## 6. Connexion sans internet

- **Demande** : 2026-11-17, « c'est possible de faire en sorte qu'on puisse se connecter également sans la connexion ? ».
- **Choix de l'exploitant** : connexion hors ligne pour un compte déjà connecté avec internet sur l'appareil. « Déconnexion » verrouille au lieu d'effacer ; « Effacer de cet appareil » reste possible.
- Site seulement, **sans migration** ni changement d'API.

**Fonctionnement** (`lib/offline/vault.ts`, magasin `vault` d'IndexedDB, base en version 3).
- **À chaque connexion avec internet** : une clé de données aléatoire (AES-GCM 256) est créée, ou reprise si le compte avait déjà un coffre. Elle est gardée **chiffrée par une clé tirée du mot de passe** (PBKDF2-SHA-256, 600 000 tours, sel aléatoire de 16 octets).
  - Le mot de passe n'est jamais gardé, ni en clair ni sous forme d'empreinte : seul le bon mot de passe déchiffre la clé.
  - Si le compte était verrouillé, ses données sont reprises, saisies en attente comprises. Si son mot de passe a changé entre-temps, l'ancien contenu chiffré est illisible : il est effacé.
- **« Déconnexion »** (les trois barres et les écrans d'erreur), quand le coffre est prêt : la session est **verrouillée**.
  - Copies des lectures, saisies en attente (appel, notes) et jetons de session sont chiffrés avec la clé de données, en une seule transaction. La clé est ensuite retirée de l'appareil, et la session de l'onglet.
  - La session n'est **pas révoquée** sur le serveur : le mot de passe la rouvrira.
  - Aucune question à la déconnexion, puisque rien n'est perdu.
- **Connexion quand le serveur ne répond pas** (appareil hors ligne, ou passerelle 502/503/504) : le mot de passe est vérifié sur l'appareil, en déchiffrant la clé de données. Si c'est le bon, tout est déchiffré, la session est rouverte et l'espace s'affiche comme avant la déconnexion. Les saisies en attente repartent au retour d'internet.
- **Connexion avec internet** : inchangée. Le serveur vérifie le mot de passe, puis le coffre est repris (voir plus haut).
- **Page de connexion** : liste « Connexion possible sans internet », avec la date limite de chaque compte et un bouton « Effacer de cet appareil » (coffre, copies et saisies en attente supprimés).

**Limites et garde-fous.**
- **7 jours** au plus depuis le dernier échange réussi avec le serveur sur cet appareil. Au-delà, la connexion demande internet.
- **5 essais ratés** sans internet : la connexion de ce compte demande internet. Une connexion en ligne remet le compteur à zéro.
- **Pris en compte seulement au retour d'internet** : un compte désactivé, un mot de passe changé ou une session révoquée. Les requêtes échouent alors, et la connexion en ligne est redemandée.
- **Encaissements en attente** (lot 3) : jamais chiffrés, jamais effacés par la déconnexion ni par « Effacer de cet appareil ». Un mot de passe changé ailleurs rendrait sinon illisible la seule trace d'un argent reçu.
- **Poste partagé** :
  - un autre compte qui se connecte efface les copies **en clair** des autres comptes, comme avant ;
  - les données **chiffrées** des comptes verrouillés restent, illisibles sans leur mot de passe.
- **Session ouverte avant cette version** (aucun coffre) : la déconnexion reste complète, comme avant (session révoquée, tout effacé). Le coffre se crée à la connexion suivante.
- **Appareil volé** : les données d'un compte verrouillé ne s'ouvrent qu'avec son mot de passe. Les 600 000 tours ralentissent fortement les essais en série, mais un mot de passe faible reste devinable. Un mot de passe solide est donc recommandé aux comptes qui utilisent la connexion sans internet.
- **Navigateur sans chiffrement** (page hors HTTPS, stockage indisponible) : pas de coffre, et le comportement d'avant s'applique.

**Vérifications (2026-11-17).**
- **Site** : vérification des types, analyse du code, `test:config`.
- **Parcours de bout en bout** : build de production, API simulée, Chromium. 26 vérifications :
  - coffre prêt après une connexion en ligne, mot de passe absent du stockage ;
  - déconnexion sans question : session retirée, copies et saisie en attente chiffrées, aucune copie en clair, aucune révocation sur le serveur ;
  - sans internet : mauvais mot de passe refusé (essais restants), bon mot de passe accepté, appel consultable, séance en attente retrouvée puis envoyée au retour d'internet ;
  - reconnexion en ligne : données reprises ;
  - blocage après 5 essais, levé par une connexion en ligne ;
  - refus au-delà de 7 jours ;
  - « Effacer de cet appareil » ;
  - ancienne session sans coffre : déconnexion complète comme avant ;
  - aucune erreur de page.
- **Non-régression** : parcours des lots 1, 2 et 3 (consultation, appel et notes, coupure, passage de la base locale de la version 1 à la version 3, bandeaux du bas, caisse), tous réussis.
