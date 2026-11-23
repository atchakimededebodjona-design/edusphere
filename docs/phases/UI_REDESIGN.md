# Refonte de l'interface web

- **Audit** (mission 1, 2026-11-23) : rapport privé remis à l'exploitant, hors du dépôt.
- **Décisions de l'exploitant** (2026-11-23, toutes les recommandations validées) :
  - actions principales en bleu de marque ;
  - polices Inter et Plus Jakarta Sans servies par le site ;
  - icônes dessinées dans le code, sans dépendance ;
  - barre de navigation en bas sur téléphone ;
  - accueil selon le rôle ;
  - phases 0 et 1 d'abord, validées sur téléphone avant la phase 2 ;
  - thème sombre hors périmètre.
- **Règle** : couche visuelle seulement. Aucune route, API, permission, logique hors connexion ou d'authentification ne change.

## Phases

| Phase | Contenu | État |
|---|---|---|
| 0 | Fondations : jetons, polices, icônes, composants de base | Livrée avec la phase 1 |
| 1 | Enveloppes et navigation, accueil selon le rôle (caisse) | Livrée |
| 2 | Écrans du quotidien : tableaux de bord, caisse, appel et notes, fiche enfant | À faire après validation sur téléphone |
| 3 | Écrans de gestion : élèves, frais, paiements, bulletins, annonces, utilisateurs… | À faire |
| 4 | Plateforme, partenaire, assistant, réinscriptions, pages publiques | À faire |
| 5 | Finitions : accessibilité, états vides et de chargement, tests e2e | À faire |

## Phase 0 — fondations

- **Polices** (`app/fonts.ts`) : Inter pour le texte, Plus Jakarta Sans pour les titres (`h1`, `h2` partout, `globals.css`).
  - `next/font` les télécharge au build et les sert depuis le site : la CSP (`font-src 'self'`) n'autorise aucune police externe.
- **Couleurs** (`tailwind.config.ts`, ajout seulement) :
  - échelle `primary` centrée sur le bleu de marque (`primary-600` = `#1565D8`) ;
  - teintes `navy` pour les menus ;
  - `font-sans` et `font-display`.
- **Icônes** (`components/ui/Icon.tsx`) : une trentaine d'icônes en traits, dessinées dans le code. Elles remplacent les emoji, dont le rendu change selon le téléphone.
- **Composants de base** (`components/ui/`), à utiliser dans les phases suivantes :
  - `Button`, `ButtonLink` : principal, secondaire, discret, danger ; 44 px de haut sur téléphone ;
  - `PageHeader`, `Card`, `StatCard`, `Badge`, `Alert`, `EmptyState`, `Skeleton` (`Surface.tsx`) ;
  - `TextField`, `SelectField` (`Field.tsx`) : libellé toujours visible, aide et erreur reliées au champ ;
  - `Modal`, `ConfirmDialog` (`Dialog.tsx`) : fenêtre accessible (titre annoncé, Échap, focus gardé puis rendu). Pour une action dangereuse, le focus part sur « Annuler ».

## Phase 1 — enveloppes et navigation

**Une seule enveloppe** (`components/shell/ShellFrame.tsx`) pour l'administration, la plateforme, le partenaire, l'enseignant et le parent :
- **menu latéral navy** sur ordinateur et tablette (`SideNav.tsx`) : entrées regroupées avec icônes, entrée active en bleu, logo de l'école en tête ;
- **barre du haut** (`ShellTopBar.tsx`) :
  - la marque, qui mène à la page d'accueil publique ;
  - le choix de l'école ;
  - la cloche et le nombre de non-lues ;
  - la photo ou les initiales, le nom et le rôle ;
  - « Déconnexion » sur ordinateur, « Se déconnecter » dans l'espace enseignant.
- **barre du bas sur téléphone** (`MobileTabBar.tsx`) : 4 raccourcis selon le rôle et « Plus », qui ouvre le menu complet et la déconnexion.

**Menus** (`lib/navigation/menus.ts`) : mêmes routes, mêmes libellés, mêmes permissions qu'avant.
- École : Scolarité, Finances, Communication, Établissement, et « Espace enseignant » pour un compte qui est aussi enseignant.
- Plateforme : Clients, Revenus, Réseau.

**Raccourcis du bas** :

| Profil | Raccourcis |
|---|---|
| Direction, administration | Accueil, Élèves, Paiements, Annonces |
| Comptabilité | Accueil, Frais, Paiements, Retards |
| Caisse | Caisse, Ma caisse, Paiements, Notifications |
| Enseignant | Accueil, Appel, Notes, Élèves |
| Parent | Accueil, Enfants, Notifications |
| Plateforme | Accueil, Écoles, Factures, Comptes |
| Partenaire | Accueil, Écoles, Commissions, Comptes |

**Bandeaux du bas** (hors connexion, mise à jour, envois en attente, notifications) : ils se posent juste au-dessus de la barre du bas. La hauteur de la barre est publiée dans `--bottom-nav-height` ; le contenu se réserve cet espace (`.shell-main`), en plus de celui des bandeaux.

**Accueil selon le rôle** :
- Un compte qui n'a que le rôle caisse arrive directement sur la caisse.
- Le tableau de bord de l'école ne demande plus que ce que le compte a le droit de voir. Avant, un comptable ou un caissier y voyait « Not enough permissions ». Sans accès aux indicateurs, il affiche des accès rapides vers les écrans du compte.

**Retirés** : `components/app-shell/Nav.tsx`, `TopBar.tsx`, `components/parent-shell/ParentNav.tsx`, `ParentTopBar.tsx`, remplacés par l'enveloppe commune.

**Tests e2e du dépôt alignés** :
- `teacher-portal` : menu « Navigation principale » ;
- `platform-owner-partner` : même menu ;
- `tenant-switcher` : le nom de l'école à la place de l'emoji.

Ils demandent Docker pour créer leurs comptes et la CI ne les lance pas ; ils n'ont pas été exécutés.

## Vérifications (2026-11-23)

- **Site** : vérification des types, analyse du code, `test:config` (25 tests).
- **Enveloppes** : build de production, **vraie API** sur PostgreSQL, Chromium. 105 vérifications sur 7 profils (direction, comptable, caissier, enseignant, parent, plateforme, partenaire) :
  - **sur ordinateur** : menu latéral, une seule entrée active, déconnexion visible, polices de la marque, aucune erreur de droits à l'arrivée ;
  - **sur téléphone** : barre du bas avec les raccourcis du rôle, pas de défilement horizontal, contenu dégagé de la barre ;
  - **feuille « Plus »** : elle s'ouvre, un lien suivi la referme, et la déconnexion depuis la feuille fonctionne ;
  - aucune erreur de page ni de politique de contenu (CSP).
- **Non-régression** :
  - bandeaux du bas au-dessus de la barre ;
  - appel et notes hors connexion, coupure pendant l'envoi, base locale ;
  - connexion sans internet, consultation hors connexion ;
  - caisse hors connexion ;
  - alertes d'annonce et notification affichée par le service worker ;
  - photos d'identité, retrait des comptes, destinataires des annonces ;
  - CSP des pages enseignant, administration et caisse.
