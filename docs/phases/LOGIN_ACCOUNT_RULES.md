# Connexion et création des comptes — règles du 2026-11-24

- **Demande** (2026-11-24) : « pour se connecter il faut que l'adresse email existe déjà dans la liste des utilisateurs [de la plateforme] ; sans ça, la tentative de se connecter se solde par une erreur et affiche compte inexistant. Les comptes des parents et des élèves sont créés par l'administrateur de l'école uniquement. Ajoute aussi la possibilité de rendre visible le mot de passe. »
- **Aucune migration.** Aucun changement de droits en base : la règle « parents et élèves » est vérifiée dans le code de l'API.

## 1. Messages de connexion (`apps/api/app/modules/auth/service.py`)

| Situation | Message affiché | Statut |
|---|---|---|
| Aucun compte n'a cette adresse (y compris un compte supprimé par la plateforme, dont l'adresse a été effacée) | « Compte inexistant. Vérifiez l'adresse email : les comptes sont créés par l'administration de l'école. » | 401 |
| Le compte existe, mauvais mot de passe | « Mot de passe incorrect. » | 401 |
| Compte désactivé, **bon** mot de passe | « Ce compte est désactivé. Contactez l'administration de votre école. » | 401 |
| Compte désactivé, mauvais mot de passe | « Mot de passe incorrect. » (la désactivation n'est annoncée qu'à qui connaît le mot de passe) | 401 |
| Trop d'essais (5 échecs par adresse en 5 minutes, ou 50 par adresse IP en 15 minutes) | « Trop d'essais de connexion. Patientez quelques minutes, puis réessayez. » (traduit par le site et l'application) | 429 |

Il n'existe toujours **aucune inscription libre** : pas de `POST /auth/register`. Un compte naît seulement de l'inscription d'une école par la plateforme ou un partenaire (son administrateur), ou de l'écran « Utilisateurs » de l'école.

### Ce que ce choix change pour la sécurité

Jusqu'ici (Phase 13, HIGH #2), l'API répondait volontairement le même message, que le compte existe ou non, pour qu'un tiers ne puisse pas vérifier qu'une adresse a un compte. **Ce n'est plus le cas** : « Compte inexistant » le dit. Ce qui reste en place :

- le statut est 401 dans tous les cas, donc **une adresse inconnue compte comme un échec**, dans les deux limites ci-dessus. Depuis une même adresse IP, au plus 50 vérifications par quart d'heure ;
- chaque essai coûte le même travail (une vérification bcrypt), que le compte existe ou non ;
- « Mot de passe oublié » garde sa réponse identique, que le compte existe ou non.

Une adresse email seule ne donne accès à rien : il faut aussi le mot de passe.

## 2. Comptes des parents et des élèves : administrateur de l'école uniquement

- **API** (`apps/api/app/modules/users/service.py::_ensure_school_admin_for_family_role`) : créer un compte, rattacher une adresse existante ou changer un rôle **vers « Parent » ou « Élève »** demande le rôle `SCHOOL_ADMIN` de cette école, ou de toute son organisation. Sinon : 403, « Seul l'administrateur de l'école crée les comptes des parents et des élèves. »
- **Avant ce changement**, le droit `users.manage` suffisait. Il appartient à `SCHOOL_ADMIN` et au rôle plateforme hérité `SUPER_ADMIN` (droit global). Un `SUPER_ADMIN` garde la création des autres rôles de l'école ; il perd seulement « Parent » et « Élève ».
- **Site** :
  - écran « Utilisateurs » : « Parent » et « Élève » ne sont proposés qu'à l'administrateur de l'école ; sinon une phrase explique pourquoi. Le rôle actuel d'une ligne reste affiché dans son sélecteur ;
  - fiche élève : « Créer un compte parent » n'apparaît qu'à l'administrateur de l'école ;
  - la règle commune est dans `apps/web/lib/users/client.ts` (`isSchoolAdminOf`).

## 3. Afficher le mot de passe

- **Site** : `apps/web/components/ui/PasswordInput.tsx`. Un bouton en forme d'œil, dans le champ à droite (44 px de large). Il ne soumet jamais le formulaire. Son nom est « Afficher le mot de passe », enfoncé ou non (`aria-pressed`). Sur une page à deux champs, le second s'appelle « Afficher la confirmation ».
- **Pages concernées** : connexion, définition du mot de passe (lien reçu par email), inscription d'une organisation par la plateforme, inscription d'une école par un partenaire, ajout d'un établissement à une organisation existante.
- **Application mobile** (`apps/mobile/app/login.tsx`) : bouton « Afficher » / « Masquer » dans le champ.

## 4. Vérifications (2026-11-24)

- API : nouveau fichier `tests/test_login_account_rules.py` ; `test_auth_timing.py` et `test_auth_rate_limit.py` mis à jour (même statut, messages différents) ; `test_platform_account_removal.py` vérifie les messages du compte désactivé et du compte supprimé.
- Site : `tsc`, `lint`, `test:config`, build de production, puis un scénario navigateur sur la vraie API locale, sur ordinateur et sur téléphone. Il couvre les quatre messages, le bouton (souris, doigt, clavier), la page de réinitialisation, l'écran « Utilisateurs » des deux profils et le blocage après trop d'essais.
- Application mobile : `tsc`.
