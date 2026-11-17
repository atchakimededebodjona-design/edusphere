# Alertes de nouvelle annonce — bandeau, cloche, notification téléphone

- **Demande** (2026-11-17) : « à l'arrivée de l'annonce, il n'y a rien pour signaler aux destinataires d'une nouvelle annonce sur leur page. Ils peuvent avoir l'annonce mais ne pas se rendre compte de cette annonce pendant des jours ».
- **Choix de l'exploitant** : notification téléphone (Web Push). Les signaux dans l'application sont ajoutés dans tous les cas.
- **Migration** `0034` : table `push_devices`. Deux réglages serveur : `WEB_PUSH_VAPID_PUBLIC_KEY` et `WEB_PUSH_VAPID_PRIVATE_KEY` (voir « Mise en service »).

## 1. Dans l'application (sans réglage)

Concerne les trois espaces : administration, parents et enseignants (`lib/notifications/useUnreadNotifications.ts`).

- **Bandeau « Nouvelle annonce »** (`components/notifications/NewAnnouncementBanner.tsx`).
  - Il s'affiche en haut de **chaque page** tant que la dernière annonce n'est pas lue : titre et début du texte.
  - « Lire » marque l'annonce comme lue et ouvre la page où elle se lit : `/notifications` (administration), `/parent/notifications`, `/teacher/announcements`.
  - « Plus tard » cache cette annonce pour la visite en cours (onglet) ; elle reste non lue. Une annonce plus récente s'affiche quand même.
  - Le bandeau n'apparaît pas sur la page où l'annonce se lit.
- **Cloche de l'espace enseignant** : le nombre de notifications non lues, en rouge, en haut de l'écran (l'administration et les parents avaient déjà ce compteur).
- **Pastille sur l'icône de l'application installée** (téléphone ou ordinateur, quand le navigateur le permet) : le nombre de non lues, effacé quand tout est lu.
- Le nombre est relu **toutes les 60 secondes** et à chaque retour sur l'onglet.

## 2. Notification téléphone

Elle s'affiche dans la barre de notifications, **même EduLinkage fermé** : « Nouvelle annonce — *école* », puis le titre et le début du texte (180 caractères au plus).

**Activation, appareil par appareil.**
- Après la connexion, un bandeau en bas propose : « 🔔 Recevez les annonces de l'école sur cet appareil, même quand EduLinkage est fermé. » avec « Activer » et « Plus tard ».
  - « Activer » déclenche la question du navigateur. **La permission n'est jamais demandée d'office.**
  - « Plus tard » : la proposition revient 7 jours après.
  - Notifications déjà refusées : plus de proposition. Elles se rétablissent dans les réglages du navigateur.
  - Sans internet, la proposition est retirée.
- Permission déjà accordée : l'appareil est ré-enregistré à chaque ouverture, sans question (les services de notification renouvellent parfois leurs adresses).
- **Toucher la notification** ouvre `/open-notifications`, qui mène chacun à ses annonces : parent → `/parent/notifications`, enseignant → `/teacher/announcements`, autres → `/notifications`. Sans session : page de connexion.

**Compatibilité.**
- **Android** (Chrome, Edge, Firefox, Samsung Internet) et ordinateurs : dans le navigateur, application installée ou non.
- **iPhone / iPad** (iOS 16.4 ou plus) : **seulement depuis l'application ajoutée à l'écran d'accueil** (Safari → Partager → « Sur l'écran d'accueil »). C'est une règle d'Apple.

**Envoi** (`apps/api/app/modules/notifications/push.py`).
- À chaque annonce publiée, **après la réponse** (tâche de fond) : publier une annonce à toute l'école n'attend jamais les services de notification.
- Mêmes destinataires que la notification dans l'application (portée et destinataires de l'annonce).
- Chaque message est **chiffré pour l'appareil** et signé avec la clé privée du serveur (protocole Web Push, VAPID). Le service de notification (Google, Mozilla, Apple, Microsoft) ne lit pas le contenu.
- Conservation par le service de notification : 7 jours si l'appareil est éteint.
- 8 envois en parallèle au plus, 10 secondes par envoi. Un échec n'empêche jamais la publication.
- Appareil désinscrit ou expiré (réponse 404 ou 410) : effacé de la table.

**Garde-fous.**
- **Adresses d'envoi acceptées** : seulement celles des services connus, en HTTPS (port 443, sans identifiants) :
  - `fcm.googleapis.com`, `android.googleapis.com` ;
  - `push.services.mozilla.com` ;
  - `push.apple.com` ;
  - `notify.windows.com`.

  Toute autre adresse est refusée (422). Le serveur ne peut donc pas être utilisé pour appeler une adresse choisie par un tiers.
- **Un navigateur = un compte** : un appareil réenregistré par un autre compte (poste partagé) quitte l'ancien.
- **« Déconnexion »** retire l'appareil : plus aucune notification de ce compte sur ce poste.
- **Isolation (RLS)** : chaque compte ne voit et ne retire que ses propres appareils. La lecture de tous les appareils sert uniquement à l'envoi (contexte plateforme), comme pour `user_sessions`.
- **Sans les deux clés**, aucune notification téléphone :
  - `GET /push/config` répond `enabled: false` et la proposition ne s'affiche pas ;
  - `POST /push/devices` répond 409 ;
  - le reste de l'application fonctionne normalement.

**API** (compte connecté).
- `GET /api/v1/push/config` : `{enabled, public_key}`.
- `POST /api/v1/push/devices` : `{endpoint, keys: {p256dh, auth}}`, réponse 204.
- `POST /api/v1/push/devices/remove` : `{endpoint}`, réponse 204.

## 3. Mise en service

1. Sauvegarde, puis migration `0034` (création de `push_devices`).
2. Clés VAPID générées **une seule fois, directement dans le `.env` du serveur**, sans jamais les afficher :

   ```
   docker compose run --rm --no-deps -T api python -m app.jobs.generate_push_keys >> .env
   ```

   Relancée alors que les clés existent déjà, la commande n'écrit rien et le signale.
3. `docker compose up -d api web`.

**La clé privée est un secret** : jamais dans le dépôt, une conversation ni une capture d'écran.
- Si elle fuit, il faut en générer une nouvelle paire (retirer les deux lignes du `.env`, relancer la commande, redémarrer l'API).
- Les appareils déjà inscrits ne reçoivent alors plus rien jusqu'à leur prochaine ouverture d'EduLinkage : ils se réinscrivent seuls avec la nouvelle clé.

## 4. Vérifications (2026-11-17)

- **API** : 8 tests (`tests/test_push_notifications.py`).
  - configuration absente (409) ou sans session (401) ;
  - adresses d'envoi acceptées et refusées ;
  - un navigateur pour un seul compte ; retrait réservé au propriétaire ;
  - isolation RLS ;
  - annonce aux enseignants : envoi aux seuls appareils des enseignants, appareil expiré (410) effacé ;
  - chiffrement et signature réels du message ;
  - texte tronqué ;
  - génération des clés.
- **Suite complète de l'API** et audit des dépendances (`pip-audit`, `pywebpush` compris) : rien de connu.
- **Parcours de bout en bout** : build de production, **vraie API** sur PostgreSQL, Chromium. 16 vérifications :
  - proposition affichée, « Plus tard » ;
  - annonce publiée par l'administration ;
  - bandeau sur une autre page de l'enseignant, cloche à 1, « Lire » ouvre les annonces, puis bandeau et cloche effacés ;
  - bandeau côté parent, « Plus tard » tenu pendant la visite, annonce toujours non lue ;
  - notification affichée par le service worker à la réception d'un message ;
  - `/open-notifications` vers les annonces de l'enseignant et du parent ;
  - aucune erreur de page.
- **Bandeaux du bas** avec la proposition : espace réservé égal à leur hauteur ; bouton « Enregistrer l'appel » visible et cliquable ; proposition retirée sans internet.
- **Non-régression** : bandeaux du bas, choix des destinataires des annonces, consultation, appel et notes hors connexion, connexion sans internet, caisse, politique de contenu (CSP).
- **Non vérifiable ici** : l'inscription réelle auprès d'un service de notification (le Chromium de test n'en a pas). À essayer sur un vrai téléphone après le déploiement.
