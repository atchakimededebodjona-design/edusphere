# Retrait des comptes par la plateforme — désactiver, supprimer

- **Demande** (2026-11-18) : « il faut donner la permission à l'administrateur principal de la plateforme de pouvoir retirer ou supprimer un compte de l'application ».
- **Choix de l'exploitant** : « Désactiver + effacer ».
  - « Désactiver » est réversible.
  - « Supprimer » est définitif : les données personnelles sont effacées et l'historique gardé.
  - Une suppression totale de la ligne a été écartée. Elle effacerait « qui a encaissé ce paiement » sur les reçus, et la base la refuse déjà pour un caissier qui a ouvert une caisse (`ondelete=RESTRICT`).
- **Migration** `0035` : `users.deleted_at`, `users.deleted_by` et la permission `platform.accounts.manage` (SUPER_ADMIN, PLATFORM_OWNER).

## 1. Dans la page « Comptes » de la plateforme

- **Recherche** par nom ou email (sans tenir compte des majuscules).
- **Statut** : « Actif », « Désactivé » ou « Supprimé le … ».
- **« Désactiver »**, puis « Confirmer la désactivation ».
  - Effet immédiat : la session en cours, son renouvellement et toute nouvelle connexion sont refusés.
  - Les sessions sont fermées et les appareils retirés des notifications téléphone.
- **« Réactiver »** : le compte retrouve son mot de passe et ses rôles. Les anciennes sessions ne reviennent pas : il faut se reconnecter.
- **« Supprimer »** ouvre un panneau qui explique les conséquences. Le bouton « Supprimer définitivement » ne s'active qu'une fois **l'email du compte saisi à nouveau**. L'API vérifie aussi cet email.

## 2. Ce que fait la suppression (`apps/api/app/modules/platform/accounts.py`)

**Effacé ou retiré :**
- nom remplacé par « Compte supprimé », email remplacé par `supprime-<identifiant>@comptes-supprimes.invalid` (domaine réservé : aucun courrier possible), téléphone effacé, photo d'identité effacée (depuis la migration 0036), mot de passe remplacé par un secret aléatoire jamais conservé ;
- rôles, affectations d'enseignant, notifications reçues, sessions, liens de réinitialisation, appareils de notification ;
- lien entre le compte et une fiche de tuteur : **la fiche reste** dans le dossier de l'élève (fiche de l'école), sans compte.

**Gardé :**
- la ligne du compte, avec la date et l'auteur de la suppression ;
- tout l'historique qui y renvoie : paiements, caisses, appels, notes, bulletins, journal d'audit. Il s'affiche désormais « Compte supprimé ».

**L'email redevient libre** : un nouveau compte peut l'utiliser.

## 3. Garde-fous

- Seuls les comptes qui ont `platform.accounts.manage` (propriétaire et super administrateur de la plateforme). Tous les autres reçoivent 403.
- **Jamais son propre compte**, ni **un compte plateforme** (`is_platform_admin`, PLATFORM_OWNER, SUPER_ADMIN, PLATFORM_SUPPORT) : refus 409.
- **Compte partenaire** : il se désactive, mais ne se supprime pas (409), car sa fiche partenaire et ses commissions lui restent rattachées.
- **Compte supprimé** : plus aucune action possible, pas même une réactivation (409).
- Le compte visé est verrouillé pendant l'action (`SELECT … FOR UPDATE`) : deux actions simultanées ne se mélangent pas.
- **Traçabilité** : `audit_logs` exige une école, donc la suppression est tracée sur le compte lui-même (`deleted_at`, `deleted_by`). Chaque action est aussi écrite dans les journaux de l'API, avec les identifiants seulement.
- **Limite connue** : un compte désactivé ou supprimé qui s'était servi de la connexion sans internet sur un appareil peut encore ouvrir ses données gardées sur cet appareil, sans réseau, jusqu'à 7 jours. Rien ne passe : au retour d'internet, toute requête est refusée (voir `PHASE_32_OFFLINE_PWA.md` §6).

**API.**
- `GET /api/v1/platform/accounts?q=…` (`platform.accounts.read`) : recherche ; `deleted_at` ajouté à chaque compte.
- `POST /api/v1/platform/accounts/{id}/deactivate`.
- `POST /api/v1/platform/accounts/{id}/reactivate`.
- `POST /api/v1/platform/accounts/{id}/delete` avec `{confirm_email}`.

## 4. Vérifications (2026-11-18)

- **Migration** `0035` appliquée, annulée puis réappliquée sur PostgreSQL 16.
- **API** : 6 tests (`tests/test_platform_account_removal.py`).
  - Accès : sans session 401 ; administrateur d'école, enseignant, partenaire 403.
  - Désactivation immédiate (jeton, renouvellement, connexion), sessions et appareils retirés, réactivation.
  - Refus : son compte, autre propriétaire, ancien super administrateur, compte inconnu (404), suppression d'un partenaire.
  - Email de confirmation exact exigé.
  - Suppression d'un enseignant, d'un parent et d'un administrateur d'école : données effacées, affectation et rôles retirés, fiche de tuteur gardée, journal d'audit intact, email réutilisable.
  - Recherche, et marque « supprimé ».
- **Liste exacte des permissions du propriétaire** mise à jour (`tests/test_partner_isolation.py`).
- **Parcours de bout en bout** : build de production, **vraie API** sur PostgreSQL, Chromium. 25 vérifications :
  - pas d'action sur son propre compte ; partenaire sans « Supprimer » ;
  - désactivation (connexion refusée), réactivation (connexion acceptée) ;
  - suppression bloquée sans l'email exact, puis faite (connexion refusée, compte « Compte supprimé », plus d'action) ;
  - affichage sur téléphone sans débordement, « Annuler » ;
  - aucune erreur de page ni de politique de contenu (CSP).
