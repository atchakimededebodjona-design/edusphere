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
| 1 | Enveloppes et navigation, accueil selon le rôle (caisse) | Livrée, validée sur téléphone le 2026-11-23 |
| 2 | Écrans du quotidien : tableaux de bord, caisse, appel et notes, fiche enfant | Livrée (voir plus bas) |
| 3 | Écrans de gestion. Lot A : élèves, paiements, frais en retard, utilisateurs, notifications. Lot B : barèmes de frais, fiche élève, bulletins, annonces, école, académique | Lots A et B livrés (voir plus bas) |
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

## Vérifications des phases 0 et 1 (2026-11-23)

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

## Phase 2 — écrans du quotidien

**Règle inchangée** : même logique, mêmes appels à l'API, même fonctionnement hors connexion. Seule la présentation change, plus deux petits comportements d'affichage, décrits plus bas : l'arrivée sur la saisie ouverte et le défilement des onglets.

**Nouvelles briques** (`components/ui/`) :
- `ActionBar` : barre d'action collée en bas pendant le défilement (« Enregistrer l'appel », « Enregistrer les notes »). Elle se pose au-dessus de la barre du bas et des bandeaux.
  - La hauteur des bandeaux est publiée dans `--bottom-banners-height` (`PwaSupport.tsx`).
- `Segmented` : choix exclusif en boutons au pouce (Présent / Absent / Retard). Ce sont de vrais boutons radio : flèches du clavier et lecteurs d'écran fonctionnent.
- `Tabs`, `TabPanel` : onglets accessibles (rôle `tab`, flèches, Début et Fin), qui défilent sur téléphone.
- `StatCard` : peut mener à l'écran de détail (`href`), avec une teinte d'icône. Libellé et chiffre occupent toute la largeur de la carte.
- `SectionTitle`, `Card padded={false}` pour les listes, `useReveal` pour amener à l'écran une zone qu'on vient d'ouvrir.
- `ErrorRetry` aligné sur les alertes communes.

**Tableaux de bord** :
- **École**, blocs affichés selon les droits du compte, chacun lu sur une route existante :
  - « Aujourd'hui » (supervision de caisse) : encaissé du jour et caisses ouvertes, via `GET /cash/reports/daily` ;
  - « Finances » (lecture des frais) : total attendu, déjà encaissé, reste à payer et frais en retard, via `GET /fees/summary` ;
  - « Scolarité » : les 4 indicateurs historiques ;
  - « Accès rapides » : 6 écrans du quotidien, selon le menu du compte.
  - Une carte ne mène à un écran que si le menu du compte le propose.
- **Plateforme** et **partenaire** : mêmes compteurs, en cartes qui mènent aux listes.
- **Enseignant** : deux grandes actions (« Faire l'appel », « Saisir les notes »), les chiffres, puis les dernières évaluations (dates en français) et notifications.
- **Parent** : une carte par enfant (initiales, matricule), qui mène à sa fiche.

**Caisse et Ma caisse** (`components/cashier`, `components/cash`, pages `cashier`) :
- passe de présentation : boutons principaux en bleu, champs de 44 px, coins arrondis, statuts en pastilles, texte secondaire lisible (contraste AA) ;
- **corrigé** :
  - sur téléphone, la barre « Encaisser » passait sous la barre du bas de la phase 1 : elle se pose maintenant au-dessus ;
  - les champs « Mode de paiement » et « Montant reçu » débordaient de leur cadre (défaut antérieur).
- Reçu provisoire (`ProvisionalReceipt.tsx`) et règles d'impression : **non modifiés**.

**Appel** (`teacher/attendance`) :
- champs avec libellés ;
- séances en boutons, avec une date au format français ;
- statut en `Segmented`, compteurs présents, absents et retards ;
- « Enregistrer l'appel » dans une `ActionBar` ;
- la feuille d'appel ouverte vient à l'écran.

**Notes** (`teacher/grades`) :
- champs avec libellés, dont « Nom de l'évaluation » et « Date de l'évaluation » ;
- évaluations en cartes ;
- saisie avec grands champs (pavé décimal) et compteur « x / y élèves notés ou absents » ;
- « Enregistrer les notes » dans une `ActionBar` ;
- la saisie ouverte vient à l'écran.

**Lecteurs d'écran** : les libellés par élève portent le nom complet (« Statut de NOM Prénom », « Note de NOM Prénom »). Deux élèves de même nom ne se confondent plus.

**Fiche enfant** (`parent/children/[id]`) :
- en-tête avec initiales ;
- vrais onglets ;
- présences en cartes ;
- moyenne générale en tête ;
- frais et paiements en lignes lisibles sur téléphone au lieu de tableaux ;
- statuts (« Partiellement payé », « Enregistré ») et dates en français ;
- montants avec séparateur de milliers.

**Limite connue, côté API** : les moyennes par matière de l'espace parent ne portent ni le nom de la matière ni celui de la période (`GET /parent/children/{id}/grades`). L'écran ne peut donc pas les nommer. Il faudrait ajouter ces deux noms à la réponse, ce qui est une petite mission serveur à part.

**Antérieur, noté pour la phase 5** : `AuthProvider` lit `GET /organizations/{id}` (et `GET /schools/{id}` pour la caisse et le parent) sans en avoir le droit. Le refus 403 est absorbé, sans effet visible. Ce fichier est protégé et n'a pas été modifié.

**Tests e2e du dépôt alignés** :
- `teacher-portal` : statut par le groupe radio, séance en date française ;
- `parent-portal` : onglets (rôle `tab`), montants « 10 000 » et « 5 000 ».

## Vérifications de la phase 2 (2026-11-23)

- **Site** :
  - vérification des types et analyse du code : aucune erreur ;
  - `test:config` : 25 tests ;
  - build de production réussi.
- **Écrans du quotidien** : build de production, **vraie API** sur PostgreSQL, Chromium, données réalistes : frais en retard, un paiement, une caisse ouverte. 95 vérifications réussies :
  - **direction** (ordinateur et téléphone) : encaissé du jour, reste à payer, frais en retard, scolarité, accès rapides, aucune erreur de droits ;
  - **comptable** : finances sans indicateurs scolaires ;
  - **caissier** : encaissement complet sur téléphone, avec « Encaisser » au-dessus de la barre du bas, reçu, journal du jour et Ma caisse ;
  - **appel** :
    - création, statut en boutons, compteurs, justification et motif ;
    - enregistrement, puis relecture après rechargement ;
    - flèches du clavier ;
    - barre d'action au-dessus de la barre du bas et du bandeau hors connexion ;
  - **notes** : création, note hors barème refusée, saisie, compteur, enregistrement ; la saisie ouverte vient à l'écran ;
  - **parent** (ordinateur et téléphone) : carte de l'enfant, onglets accessibles au clavier, frais en français ;
  - **plateforme** et **partenaire** ;
  - **partout** :
    - pas de défilement horizontal ;
    - aucun champ ni bouton hors de l'écran ;
    - aucune erreur JavaScript ou CSP ;
    - aucun refus 403 nouveau.
- **Non-régression** :
  - enveloppes de la phase 1 : 105 vérifications ;
  - appel et notes hors connexion : 24 ;
  - coupure pendant l'envoi : 5 ;
  - bandeaux du bas : 8 ;
  - connexion sans internet : 26 ;
  - base locale : 3 ;
  - caisse hors connexion et reçu provisoire : 36 ;
  - consultation hors connexion : 13 ;
  - proposition de notifications : 9.

## Phase 3, lot A — écrans de gestion (2026-11-24)

**Règle inchangée** : mêmes appels à l'API, mêmes permissions. Seules la présentation et trois confirmations changent.

**Nouvelles briques** (`components/ui/`) :
- `DataTable` : le tableau commun des écrans de gestion.
  - Sur ordinateur, c'est un vrai tableau.
  - Sur téléphone (moins de 640 px), **chaque ligne devient une carte** : le titre en tête, puis les valeurs deux par deux, chacune avec son libellé. Les actions occupent toute la largeur.
  - Il n'y a qu'une seule structure de tableau, jamais deux copies (tableau et cartes). Les tests et les lecteurs d'écran trouvent donc chaque ligne une seule fois.
  - Les libellés du téléphone sont écrits par le CSS (`data-label`), pas dans le texte des cellules.
  - Les rôles ARIA (`table`, `row`, `cell`) sont posés explicitement, parce que certains navigateurs les oublient quand l'affichage d'un tableau change.
  - Il accepte aussi un panneau ouvert sous une ligne (`after`) et un état vide.
- `Pager` : pagination précédente / suivante.
- `TableSkeleton` : lignes grises pendant le premier chargement.
- `NotificationItem` (`components/notifications/`) : une notification présentée de la même façon pour l'administration, le parent et l'enseignant (type en pastille, date en français, point bleu si non lue).
- Icônes ajoutées : `chevronLeft`, `search`, `plus`, `download`.
- `Button` : deux variantes discrètes colorées, `quiet` (bleu) et `quietDanger` (rouge). Ajouter une couleur de texte à `ghost` par `className` ne marchait pas : les deux couleurs Tailwind entraient en conflit et le gris l'emportait.
- **Corrigé** dans `Modal` : `[data-autofocus]` est maintenant cherché en premier. Avant, `querySelector` avec une seule liste de sélecteurs rendait le premier élément de la page, donc toujours le bouton « Fermer », jamais le champ ou le bouton désigné. Ainsi, une action dangereuse place bien le focus sur « Annuler ».

**Élèves** (`students`) :
- filtres avec libellés visibles (« Rechercher », « Filtrer par statut », « Filtrer par classe ») ;
- statuts en pastilles, « Non affecté » mis en évidence ;
- barre de sélection avec « Modifier en masse » et « Affecter à une classe » ;
- formulaire « Nouvel élève » avec libellés et confirmation d'ajout ;
- import et panneaux en masse alignés sur les composants communs ;
- **corrigé (antérieur)** : chaque lettre tapée dans la recherche remplaçait toute la page par « Chargement... », ce qui faisait perdre le curseur. Maintenant, seule la liste se recharge, et la recherche part 300 ms après la dernière lettre.

**Paiements** (`payments`) :
- totaux en cartes et montants en francs (« 25 000 FCFA » au lieu de « 25000.00 ») ;
- modes et statuts en français (« Virement », « Enregistré », « Annulé ») ;
- motif affiché sur un paiement annulé ;
- **l'annulation se confirme dans une fenêtre de l'application**, avec le champ « Motif de l'annulation » obligatoire, au lieu de la boîte `window.prompt` du navigateur. Les protections ne changent pas : un seul envoi par paiement, pas de rechargement sur refus, message d'erreur métier ;
- le reçu s'ouvre comme à la caisse (`openReceipt`), sans blocage de fenêtre surgissante.

**Frais en retard** (`fees/overdue`) :
- échéances en français, retard en pastille, montant restant formaté ;
- canaux de relance en pastilles (mêmes libellés prudents qu'avant) ;
- pagination commune.

**Utilisateurs** (`users`) :
- photo, nom, email, rôles, statut en pastille ;
- sélecteur de rôle nommé pour les lecteurs d'écran (« Rôle de NOM ») ;
- **activer / désactiver et retirer une photo se confirment dans une fenêtre commune**, au lieu de « Confirmer ? Oui / Non » dans la ligne ;
- panneau photo toujours sous la ligne ;
- formulaire de création avec libellés. La règle « Parent / Élève réservés à l'administrateur de l'école » est inchangée.

**Notifications** : `(app)/notifications`, aussi utilisée par le parent, et `teacher/notifications` ont la même présentation et des dates en français. Le bouton s'appelle « Marquer comme lue » ; sur téléphone, il passe sous le texte pour lui laisser toute la largeur. « Tout marquer comme lu » se trouve en tête.

**Tests e2e du dépôt alignés** :
- `payments-cancel` : fenêtre d'annulation, montants « 67 000 », statuts « Enregistré » et « Annulé » ;
- `audit-logs` : confirmation de désactivation dans la fenêtre.

Ils demandent Docker et la CI ne les lance pas ; ils n'ont pas été exécutés.

## Vérifications de la phase 3, lot A (2026-11-24)

- **Site** : vérification des types, analyse du code, build de production.
- **Écrans du lot A** : build de production, **vraie API** sur PostgreSQL, Chromium, sur ordinateur (1366 px) et sur téléphone (360 px). Données : 24 élèves dont un sans classe, 23 frais en retard sur deux pages, deux paiements, une annonce. **143 vérifications réussies** :
  - **élèves** :
    - en-têtes ;
    - matricule seul dans sa cellule ;
    - le curseur reste dans la recherche, qui réduit la liste ;
    - filtre « Non affectés » ;
    - sélection, panneau d'affectation ;
    - ajout d'un élève avec confirmation ;
  - **paiements** :
    - totaux et montants en francs, mode et date en français ;
    - annulation par la fenêtre : curseur dans le motif, confirmation impossible sans motif, Échap ferme sans rien envoyer ;
    - une seule demande, aucune boîte du navigateur ;
    - statut « Annulé » et motif affichés, totaux relus ;
  - **frais en retard** : nombre et pages annoncés, 20 lignes, retard en jours, échéance en français, pagination ;
  - **utilisateurs** :
    - désactivation puis réactivation par la fenêtre, avec le focus sur « Annuler » ;
    - panneau photo ;
    - sélecteur de rôle nommé ;
    - « Parent » et « Élève » proposés à l'administrateur ;
  - **notifications** :
    - administration, parent et enseignant ;
    - dates en français ;
    - « Marquer comme lue » et « Tout marquer comme lu » ;
    - texte sur toute la largeur sur téléphone ;
  - **téléphone** : lignes en cartes avec libellés, pas de défilement horizontal, aucun champ ni bouton hors de l'écran ;
  - **partout** : « Annuler » et « Désactiver » en rouge, aucune erreur JavaScript ou CSP, aucun refus 403 nouveau.
- **Non-régression** :
  - écrans du quotidien (phase 2) : 95 ;
  - enveloppes (phase 1) : 105 ;
  - appel et notes hors connexion : 24 ;
  - coupure pendant l'envoi : 5 ;
  - bandeaux du bas : 8 ;
  - connexion sans internet : 26 ;
  - base locale : 3 ;
  - caisse hors connexion et reçu provisoire : 36 ;
  - consultation hors connexion : 13 ;
  - proposition de notifications : 9.

## Phase 3, lot B — écrans de gestion (2026-11-24)

**Règle inchangée** : mêmes appels à l'API, mêmes permissions, mêmes `data-testid`. Seule la présentation change.

- **`ResourceCrudPanel`** (`components/crud/`), le panneau « liste + ajout + modification en ligne » partagé par les frais et l'académique :
  - il repose sur le tableau commun (`DataTable`), donc chaque ligne devient une carte sur téléphone ;
  - les dates s'affichent en français et les cases à cocher en « Oui / Non » ;
  - en modification, chaque champ porte son nom (« Nom », « Début »…) pour les lecteurs d'écran ;
  - le formulaire d'ajout a des libellés visibles ;
  - le bouton de détail (flèche) annonce s'il est ouvert (`aria-expanded`).
- **Frais scolaires** :
  - onglets communs (`Tabs`), accessibles au clavier ;
  - les barèmes affichent le montant en francs, la portée en français (« Toute l'école », « Classe : CM1 A »), l'échéance et une pastille « Facultatif » ;
  - « Générer les frais élèves » affiche son résultat dans la ligne ;
  - le formulaire « Nouveau barème » a des libellés visibles.
- **Académique** : onglets communs. Années, niveaux, matières et salles passent par `ResourceCrudPanel`. Les classes et les affectations des enseignants gardent leur logique ; seuls leurs styles ont été remplacés par ceux du système commun.
- **Bulletins** :
  - onglets communs, « Génération & suivi » en premier ;
  - filtres dans une carte, statut en pastille (« Brouillon », « Publié ») ;
  - modèles avec la pastille « Par défaut » et un champ « Nom du modèle » qui a un libellé.
- **Annonces** :
  - formulaire en carte, avec un compteur de caractères ;
  - les classes deviennent des cases faciles à toucher ;
  - la confirmation et les erreurs s'affichent en alertes communes ;
  - l'historique est daté en français.
  - Le repère `announcement-audience-hint` et les libellés des champs sont inchangés.
- **École** :
  - champs avec libellés au lieu de simples textes indicatifs, avec des exemples pour le fuseau horaire et la devise ;
  - logo dans une carte ;
  - le bouton « Changer le logo » est maintenant atteignable au clavier : le champ de fichier est masqué visuellement (`sr-only`) au lieu d'être retiré (`hidden`).
- **Fiche élève** :
  - lien de retour en bouton ;
  - statut en pastille ;
  - chaque partie (carte d'identité, tuteurs, inscriptions, documents, situation financière) dans sa carte ;
  - champs de 44 px, boutons du système commun, texte secondaire lisible.
  - Les `data-testid` utilisés par les tests e2e sont inchangés.
  - **Situation financière**, reprise entièrement (`StudentFinancialSummary`) :
    - totaux en cartes, montants en francs ;
    - échéances, modes et statuts en français (« Partiellement payé », « Virement », « Annulé ») ;
    - frais et historique dans le tableau commun, donc en cartes sur téléphone. Avant, le tableau sortait de l'écran ;
    - **l'annulation passe par une fenêtre de l'application** avec un motif obligatoire, au lieu de `window.prompt`. Un refus de l'API est maintenant affiché ; avant, il passait inaperçu (promesse non gérée) ;
    - le reçu s'ouvre comme à la caisse (`openReceipt`).
  - **Tuteurs** : le formulaire « Nouveau tuteur » a des libellés visibles (« Nom complet », « Lien avec l'élève », « Téléphone », « Email »).
  - **Photo** (`PassportPhotoPicker`, aussi utilisé par l'écran « Utilisateurs » et le profil de l'enseignant) : boutons du système commun, en bleu au lieu de noir.
- **Outil de travail** : pour les gros composants (`ClassesPanel`, `GenerationPanel`, `StudentGuardians`, `StudentDocuments`, `StudentEnrollments`, `StudentFinancialSummary`, `StudentPhoto`), seules les valeurs EXACTES de `className` ont été remplacées par celles du système commun. Ni le texte, ni la logique, ni les repères de test n'ont changé.

## Vérifications de la phase 3, lot B (2026-11-24)

- **Site** : vérification des types, analyse du code, build de production.
- **Écrans du lot B** : build de production, **vraie API** sur PostgreSQL, Chromium, sur ordinateur (1366 px) et sur téléphone (360 px). **136 vérifications réussies** :
  - **frais** :
    - onglets au clavier ;
    - ajout d'une catégorie ;
    - barème en francs, portée et échéance en français ;
    - « Générer les frais élèves » ;
    - création d'un barème limité à une classe ;
  - **académique** :
    - année en cours ;
    - détail des périodes (`aria-expanded`) ;
    - modification avec champs nommés ;
    - ajout d'un niveau, liste des classes ;
  - **bulletins** : onglets, modèle de départ, création d'un modèle « Par défaut » ;
  - **annonces** :
    - compteur de caractères, aide sur les destinataires ;
    - publication impossible sans classe ;
    - cases de classe de 40 px au moins ;
    - publication confirmée, historique daté en français ;
  - **école** : champs avec libellés, enregistrement, logo atteignable au clavier ;
  - **fiche élève** :
    - sections en cartes, statut en pastille ;
    - situation financière en francs et en français ;
    - annulation d'un paiement par la fenêtre, avec motif affiché et frais repassé « Non payé », sans boîte du navigateur ;
    - libellés du formulaire des tuteurs ;
    - bouton photo en bleu ;
    - enregistrement de la carte d'identité ;
  - **partout** :
    - pas de défilement horizontal, aucun champ ni bouton hors de l'écran ;
    - aucun texte en gris clair ;
    - aucune erreur JavaScript ou CSP, aucun refus 403 nouveau.
- **Non-régression** :
  - lot A : 143 ;
  - phase 2 : 95 ;
  - phase 1 : 105 ;
  - hors connexion :
    - appel et notes : 24 ;
    - coupure : 5 ;
    - bandeaux : 8 ;
    - connexion sans internet : 26 ;
    - base locale : 3 ;
    - caisse : 36 ;
    - consultation : 13 ;
    - notifications : 9.
