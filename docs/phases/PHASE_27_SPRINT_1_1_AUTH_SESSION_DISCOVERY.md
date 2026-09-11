# Phase 27 — Sprint 1.1
# Auth & Session Resilience Discovery

Discovery uniquement — aucun fichier de code modifié, aucune migration, aucun commit, aucun push.
Chaque affirmation ci-dessous est ancrée dans une lecture réelle du code cité ; toute incertitude
est marquée explicitement comme telle plutôt que présentée comme un fait.

## 1. Résumé exécutif

Le commit `3577fc0` a renommé la clé de stockage de session Web de `edusphere.session` vers
`edulinkage.session`, **sans aucun mécanisme de migration**. Le code Web (`getStoredTokens()`) ne
connaît que la nouvelle clé. Un navigateur qui détenait une session valide sous l'ancienne clé se
retrouve, du point de vue du nouveau code, **sans aucune session** — pas de token corrompu, pas de
token expiré, simplement rien à lire. Cela déclenche exactement le chemin normal d'un utilisateur
non authentifié : aucun header `Authorization` envoyé, 401 `"Could not validate credentials"` côté
API (comportement backend correct et inchangé), puis un rafraîchissement qui échoue immédiatement
lui aussi (rien à rafraîchir). Une déconnexion/reconnexion complète écrit une session fraîche sous
la bonne clé et résout le problème — ce qui correspond exactement à l'observation.

Au-delà de cet incident précis, l'audit révèle que **le mécanisme 401→refresh→retry du Web est
nettement moins robuste que celui déjà existant côté Mobile** dans ce même dépôt : pas de
distinction réseau/rejet explicite, pas de notification à `AuthProvider` en cas d'échec définitif,
et une architecture qui rend possible une **race condition confirmée** entre requêtes 401
concurrentes (rotation du refresh token côté serveur + absence de mutex côté client). Le Mobile a
déjà résolu ces deux problèmes (Phase 12, code existant) — la recommandation principale de ce
rapport est de porter ces patterns déjà éprouvés vers le Web plutôt que d'inventer un nouveau
mécanisme.

## 2. Architecture actuelle

```
Login (email+password)
  → access_token (JWT, HS256, 15 min, "sub"=user_id, "type"="access")
  → refresh_token (opaque, 48 octets urlsafe, hashé SHA-256 en base, 30 jours)
       ↓ stocké dans UserSession (device_id/ip/user_agent, expires_at, revoked_at)

Chaque requête API :
  Authorization: Bearer <access_token>
  → get_current_user() décode le JWT, charge le User, applique le contexte tenant

Refresh :
  POST /auth/refresh {refresh_token}
  → session trouvée par hash, vérifiée (non révoquée, non expirée)
  → session.revoked_at = maintenant (rotation immédiate — l'ancien refresh_token devient inutilisable)
  → nouvelle UserSession créée, nouveau couple (access_token, refresh_token) renvoyé
```

Stockage client :
- **Web** : `localStorage`, clé unique `edulinkage.session` → `{access_token, refresh_token}` en JSON.
- **Mobile** : `expo-secure-store` (natif) ou `localStorage` (web Expo), même clé `edulinkage.session`, même format.
- Aucun cookie n'est utilisé nulle part — uniquement `Authorization: Bearer` en en-tête, token géré entièrement côté client.

## 3. Authentification Backend

Fichiers inspectés : `apps/api/app/modules/auth/{router.py,service.py,models.py,schemas.py}`,
`apps/api/app/core/{security.py,permissions.py}`.

- **Login** — `POST /api/v1/auth/login` (`auth/router.py:58`) → `service.login()` → `authenticate()` (vérifie mot de passe, mitigation de timing par hash factice si le compte n'existe pas ou est inactif) → `_issue_tokens()`.
- **Access token** — JWT HS256, `settings.jwt_secret_key`, payload `{sub, type:"access", iat, exp}`, expiration **15 minutes** (`settings.jwt_access_token_expire_minutes`, `app/core/security.py:20-28`).
- **Refresh token** — opaque (`secrets.token_urlsafe(48)`), jamais un JWT. Seul son hash SHA-256 est stocké (`UserSession.refresh_token_hash`). Expiration **30 jours** (`settings.jwt_refresh_token_expire_days`).
- **Rotation** — **confirmée par un test dédié** (`test_refresh_rotates_token_and_invalidates_old_one`, `apps/api/tests/test_auth.py:85-99`) : chaque appel à `/refresh` marque la session courante `revoked_at` puis crée une session **entièrement nouvelle**. Réutiliser l'ancien refresh_token après rotation renvoie **401** de façon certaine et immédiate.
- **Révocation** — `POST /auth/logout` marque la session `revoked_at`. `GET /auth/sessions` / `DELETE /auth/sessions/{id}` permettent de lister/révoquer les sessions actives d'un utilisateur (device management), non utilisés par le flux normal de connexion Web/Mobile.
- **Cookies** — aucun. Uniquement `Authorization: Bearer <token>`.
- **401 `"Could not validate credentials"`** — provient d'un seul endroit : `get_current_user()` (`app/core/permissions.py:26-47`), déclenché dans **trois cas indiscernables l'un de l'autre côté client** :
  1. aucun token présent (header `Authorization` absent) ;
  2. `jwt.InvalidTokenError` — ce qui **inclut l'expiration** (`ExpiredSignatureError` hérite de `InvalidTokenError` dans PyJWT), signature invalide, token malformé ;
  3. utilisateur introuvable ou désactivé.
- **401 sur `/refresh`** — `"Invalid or expired refresh token"` (message différent de celui de `get_current_user`), levé par `_get_active_session()` si la session n'existe pas, est révoquée, ou expirée.
- **403** — réservé aux permissions RBAC insuffisantes (`ensure_permission`), sans rapport avec l'authentification elle-même.

**Point confirmé important** : le commit `3577fc0` n'a touché **ni** `jwt_secret_key`, **ni**
`jwt_access_token_expire_minutes`, **ni** aucune logique de `auth/service.py` ou
`core/security.py` — vérifié en relisant le diff réel de ce commit. Aucun token émis avant le
déploiement n'a été invalidé côté serveur par ce déploiement.

## 4. Authentification Web

Fichiers inspectés : `apps/web/lib/auth/{AuthProvider.tsx,client.ts,session.ts,useAuth.ts}`,
`apps/web/lib/api/client.ts`, `apps/web/app/(app)/AuthGate.tsx`.

- **`session.ts`** — `STORAGE_KEY = "edulinkage.session"` (depuis `3577fc0`). Deux fonctions : `getStoredTokens()`/`setStoredTokens()`/`clearStoredTokens()`, toutes basées sur `window.localStorage`. Aucune connaissance de l'ancienne clé.
- **`api/client.ts::apiFetch`** — client HTTP unique, partagé par tous les modules :
  ```
  doFetch() → si stored existe, attache Authorization
  response = doFetch()
  si 401 :
      refreshed = refreshTokens()   // relit stored, POST /refresh, écrit les nouveaux tokens
      si refreshed : response = doFetch()   // UNE seule retentative
      sinon : clearStoredTokens()
  si !response.ok : throw ApiError
  ```
  Ce mécanisme **existe déjà** — ce n'est pas une lacune totale, mais il présente trois défauts précis (détaillés §7/§9) :
  1. `refreshTokens()` ne distingue pas un rejet explicite du serveur d'une erreur réseau — une exception de `fetch()` pendant le refresh remonte telle quelle, sans jamais appeler `clearStoredTokens()` ni la traiter proprement (comportement non testé).
  2. `clearStoredTokens()` agit uniquement sur `localStorage` — **aucune notification n'atteint `AuthProvider`**, dont l'état React `status`/`me` reste inchangé jusqu'au prochain remontage ou prochain appel `loadMe()`.
  3. **Aucun verrou "un seul refresh à la fois"** — chaque appel `apiFetch` gère son propre refresh indépendamment.
- **`AuthProvider.tsx`** — au montage, `loadMe()` n'est appelé **que si** `getStoredTokens()` renvoie quelque chose (`useEffect` ligne 68-74) ; sinon `status` passe directement à `"anonymous"` sans jamais interroger l'API.
- **`AuthGate.tsx`** — redirige vers `/login` uniquement sur `status === "anonymous"` (effet déclenché par le changement de `status`), affiche un écran de chargement pendant la résolution.
- **Synchronisation entre onglets** — **aucune**. `localStorage` est partagé entre onglets du même navigateur, mais rien n'écoute l'événement `storage` : un logout dans un onglet ne notifie pas les autres onglets ouverts (non testé, non implémenté — confirmé absent par grep, aucune occurrence de `window.addEventListener("storage"`).

## 5. Cause du problème observé

### Cause confirmée

Le renommage `edusphere.session` → `edulinkage.session` (commit `3577fc0`, `apps/web/lib/auth/session.ts`) **sans aucune compatibilité de lecture avec l'ancienne clé** signifie que tout navigateur ayant une session ouverte **avant** ce déploiement se retrouve, dès que le nouveau code JavaScript s'exécute, dans l'état suivant :
- `getStoredTokens()` lit `edulinkage.session` → **absent** → renvoie `null`.
- `apiFetch` : `stored` est `null` → **aucun header `Authorization` n'est envoyé**.
- Backend : `token is None` dans `get_current_user()` → `401 "Could not validate credentials"` (comportement backend strictement correct — il n'y a réellement aucune information d'authentification dans la requête).
- `apiFetch` tente un refresh : `refreshTokens()` relit `getStoredTokens()` → toujours `null` → retourne `false` immédiatement, **sans même contacter le serveur**.
- `clearStoredTokens()` est appelé (no-op, la clé n'existe pas) ; l'erreur 401 d'origine remonte à l'écran.

Une déconnexion (`logout()` — best-effort côté serveur, `clearStoredTokens()` local) suivie d'une reconnexion (`login()`) écrit une session neuve sous **la bonne** clé `edulinkage.session`, remettant tout en cohérence — exactement le comportement observé ("le problème a disparu").

Ce mécanisme est directement vérifiable dans le code, sans ambiguïté : ce n'est pas une hypothèse.

### Causes probables

- **Pourquoi "certaines pages" fonctionnaient encore juste après le déploiement** : probablement parce que l'onglet du navigateur, resté ouvert pendant le déploiement, exécutait encore tout ou partie du bundle JavaScript chargé **avant** la mise à jour (état React déjà en mémoire, pas de rechargement complet de page). Une navigation vers une route dont le code n'était pas encore chargé côté client a pu déclencher un nouveau chargement de chunk (le nouveau build), révélant le problème au premier appel `apiFetch` réellement exécuté avec le nouveau code. Ce mécanisme est cohérent avec Next.js (App Router, découpage par route) mais je ne peux pas prouver avec certitude, depuis le code seul, l'ordre exact de chargement des chunks côté navigateur au moment précis de l'incident — c'est une explication plausible, pas une certitude établie par le code.
- Il est **probable** (pas confirmé par un log de l'incident réel) que la race condition décrite en §7 (§9) n'est **pas** la cause de cet incident précis, puisque le refresh a échoué "immédiatement, faute de token stocké" plutôt que par un conflit entre deux refresh concurrents valides.

### Hypothèses

- Aucune hypothèse supplémentaire non déjà couverte ci-dessus n'a été jugée nécessaire — le mécanisme racine est suffisamment bien expliqué par la seule lecture du code.

## 6. Analyse des clés de session

| | Ancienne | Nouvelle |
|---|---|---|
| Web | `edusphere.session` (`localStorage`) | `edulinkage.session` (`localStorage`) |
| Web (école sélectionnée) | `edusphere.selected_school_id` | `edulinkage.selected_school_id` |
| Mobile | `edusphere.session` (`SecureStore`/`localStorage` web) | `edulinkage.session` |

- **Écriture** : `setStoredTokens()` (login, refresh réussi).
- **Lecture** : `getStoredTokens()` (chaque `apiFetch`, montage `AuthProvider`).
- **Suppression** : `clearStoredTokens()` (logout, refresh définitivement échoué).
- **Format** : JSON `{access_token: string, refresh_token: string}` — identique avant/après le renommage, **seule la clé a changé, pas le format de la valeur**.
- **Compatibilité avec l'ancien format** : totale au niveau du contenu (même structure) — le seul obstacle est le nom de la clé sous laquelle le lire.
- **Dépendance E2E** : `apps/web/e2e/setup-wizard.spec.ts:229` écrit directement `"edulinkage.session"` (déjà mis à jour dans `3577fc0`) pour simuler un token corrompu.
- **Dépendance Mobile** : clé déjà migrée dans le même commit (`apps/mobile/lib/auth/session.ts`) ; l'app n'étant pas publiée, aucun utilisateur réel n'a pu être affecté côté Mobile (confirmé par le contexte fourni).
- **Dépendance Web `AuthProvider.tsx`** : `SELECTED_SCHOOL_STORAGE_KEY` déjà migrée également.

## 7. Gestion actuelle des 401

Comportement réel (Web, `apiFetch`) :

```
REQUEST → 401 → refresh (une tentative) → si OK : retry UNE fois → résultat final
                                        → si échec : clearStoredTokens() localement, erreur remonte
```

- **Retry** : limité à **une seule** tentative (pas de boucle possible dans cette fonction — confirmé, il n'y a pas de récursion ni de compteur qui pourrait boucler).
- **Déconnexion automatique** : **partielle** — `localStorage` est nettoyé, mais **l'état React `AuthProvider` n'est jamais mis à jour** en dehors d'un nouveau montage ou d'un appel explicite à `loadMe()`. Un utilisateur peut donc se retrouver avec une UI qui se comporte comme "toujours connecté" (nav, TopBar) alors que chaque requête échoue silencieusement en arrière-plan, jusqu'à ce qu'il navigue d'une façon qui redéclenche `loadMe()`.
- **Redirection vers `/login`** : uniquement pilotée par `AuthGate`, qui réagit à `status === "anonymous"` — mais `status` n'étant pas mis à jour par `apiFetch`, cette redirection **ne se déclenche pas automatiquement** après un échec de refresh survenu après le montage initial.
- **Message utilisateur** : `ApiError` porte le message brut du backend (`"Could not validate credentials"` ou `"Invalid or expired refresh token"`) — **potentiellement affiché tel quel** selon l'écran (voir §11), jamais traduit en un message générique orienté utilisateur au niveau du client HTTP lui-même (contrairement au Mobile, qui a `toUserMessage()` centralisé).

Comparaison directe avec le Mobile (`apps/mobile/lib/api/client.ts`, `AuthProvider.tsx`) — **déjà implémenté, à porter, pas à réinventer** :
- Distinction stricte réseau/timeout (`NetworkError`/`TimeoutError`) vs rejet serveur explicite pendant le refresh — une simple coupure réseau ne détruit jamais une session potentiellement valide.
- `onSessionExpired()` : registre d'écouteurs minimal permettant à `apiFetch` (hors arbre React) de notifier `AuthProvider` d'un échec **définitif** de refresh — `AuthProvider` repasse alors immédiatement `status` à `"anonymous"`, ce qui déclenche la redirection existante sans code supplémentaire.
- `toUserMessage()` centralisé, jamais de message technique brut exposé directement.

## 8. Gestion du refresh

- Le Web **possède déjà** un mécanisme "401 → refresh → retry" fonctionnel pour le cas nominal (token simplement expiré, refresh valide disponible) — ce n'est **pas absent**, contrairement à ce qu'on pourrait supposer sans lire le code.
- Ce qui **manque** : la distinction entre un refresh qui échoue parce que le réseau est coupé (transitoire, ne devrait pas déconnecter) et un refresh qui échoue parce que le serveur rejette explicitement le refresh token (définitif, doit déconnecter) — Web traite aujourd'hui toute non-réussite de la même façon (`clearStoredTokens()`), sans distinguer les deux cas ni notifier `AuthProvider`.

## 9. Risques de concurrence

**Race condition confirmée par lecture du code**, indépendante de l'incident du renommage de clé :

Scénario : plusieurs requêtes (`GET /students`, `GET /classes`, `GET /notifications`, `GET
/schools`) sont lancées presque simultanément avec un access_token expiré mais un refresh_token
encore valide.

1. Chaque requête reçoit 401 indépendamment.
2. Chaque appel `apiFetch` déclenche **son propre** `refreshTokens()`, chacun relisant **le même** refresh_token encore stocké (aucune requête n'a encore écrit de nouveau token).
3. Côté serveur, `refresh()` **révoque immédiatement** l'ancienne session et en crée une nouvelle (confirmé §3, test dédié) — la **première** requête de refresh à atteindre le serveur réussit et écrit un nouveau couple de tokens ; **toute requête de refresh utilisant l'ancien refresh_token après cet instant reçoit 401 `"Invalid or expired refresh token"`**, car ce token est désormais réellement révoqué.
4. Une requête de refresh "perdante" voit `refreshed = false` → appelle `clearStoredTokens()` → **supprime les tokens flambant neufs qu'une autre requête gagnante venait d'écrire l'instant d'avant** (aucun verrou, aucune vérification de fraîcheur avant suppression).

Conséquence possible : un utilisateur avec une session par ailleurs parfaitement valide peut être déconnecté à tort simplement parce que plusieurs requêtes ont expiré en même temps (typiquement au chargement d'un tableau de bord qui lance plusieurs appels en parallèle) — un scénario **plausible en production**, bien plus probable qu'un simple aléa de timing isolé.

**Mécanisme recommandé** : "single refresh in flight" — un seul appel réel à `/auth/refresh` en cours à un instant donné ; toute requête 401 concurrente pendant qu'un refresh est déjà en cours attend la **même** promesse plutôt que d'en déclencher une nouvelle. Pattern standard (promesse partagée mémorisée le temps du refresh, libérée une fois résolue), sans dépendance externe. **Non implémenté actuellement, ni côté Web ni côté Mobile** — le Mobile n'a pas ce verrou non plus (vérifié : `refreshTokens()` mobile n'a aucune protection de concurrence), mais son usage typique (un écran à la fois, moins d'appels parallèles) rend le risque moins probable en pratique, sans l'éliminer.

## 10. Sécurité / Multi-tenancy

- Le mécanisme de refresh actuel **ne permet à aucun moment** de changer d'organisation, d'école, ou d'utilisateur : le refresh token est lié à un `user_id` unique via `UserSession.user_id`, et `_issue_tokens()` réémet toujours pour le **même** `user`. Aucune migration de session ne pourrait introduire un IDOR tant qu'elle se contente de lire/écrire des tokens déjà valides pour le même navigateur.
- **Aucune amélioration proposée ici ne doit jamais lire un token appartenant à un autre utilisateur** : toute migration douce de clé (§5 de la mission) doit se contenter de **déplacer une valeur déjà présente dans le `localStorage` de CE navigateur**, sans jamais accepter de source externe (paramètre d'URL, autre origine, etc.).
- RBAC, RLS, et la logique `ensure_permission`/tenant ne sont concernés par aucun des mécanismes discutés ici — le problème est intégralement situé en amont de l'autorisation, au niveau du transport du token.

## 11. Mobile

- Les clés `edusphere.session`/`edulinkage.session` sont bien utilisées côté Mobile (`apps/mobile/lib/auth/session.ts`), déjà migrées dans `3577fc0` vers `edulinkage.session`, exactement comme le Web.
- **Le même type de problème est théoriquement possible côté Mobile** si un appareil avait une session persistée sous l'ancienne clé au moment d'une mise à jour de l'app — mais l'application mobile **n'est pas publiée actuellement** (confirmé par le contexte fourni), donc **aucun utilisateur réel n'a pu être affecté**, et ce risque reste purement théorique tant qu'aucune distribution n'existe.
- Le Mobile est, à l'inverse, la **source d'inspiration recommandée** pour corriger le Web (§7/§9) : `onSessionExpired`, distinction réseau/rejet, `toUserMessage()` centralisé y existent déjà et sont testés en usage réel (Phase 12).

## 12. Tests existants

- **Backend** (`apps/api/tests/test_auth.py`) : couverture solide — login, rotation de refresh token (`test_refresh_rotates_token_and_invalidates_old_one`), rejet d'un refresh token invalide/garbage, refresh après logout, endpoints `/sessions`. Aucun test ne couvre spécifiquement le comportement de `get_current_user` face à un token **expiré** par opposition à malformé (les deux sont fusionnés dans le même `except`), mais le comportement (401 identique) est déterministe par lecture du code.
- **Web E2E** (`apps/web/e2e/`) :
  - `setup-wizard.spec.ts` (lignes 224-232) : corrompt les deux tokens stockés sous la clé actuelle, vérifie que la requête suivante échoue en 401 et que le refresh (silencieux) échoue aussi — **couvre déjà le cas "refresh invalide"**, mais avec la clé déjà correcte (pas de scénario "ancienne clé").
  - `admin-onboarding.spec.ts` (ligne 85) : vide tout `localStorage` pour simuler une reconnexion — ne teste pas la migration, seulement l'absence totale de session.
  - `password-reset.spec.ts` : couvre le flux mot de passe oublié/réinitialisation, pas la session elle-même.
  - **Aucun test** ne couvre : plusieurs requêtes 401 simultanées, une ancienne clé de session présente au chargement, une distinction réseau vs rejet serveur pendant un refresh, ou la notification de `AuthProvider` après un échec de refresh survenu après le montage initial.
- **Mobile** : aucun test automatisé trouvé dans `apps/mobile` (confirmé lors de l'audit Phase 27 précédent) — le comportement robuste qui y existe n'est validé que manuellement.

## 13. Tests nécessaires

| # | Scénario | Type | Existe déjà ? |
|---|---|---|---|
| A | Session valide, requête réussit du premier coup | E2E | Implicite dans tous les specs existants |
| B | Access token expiré + refresh valide → retry silencieux réussi | E2E/unitaire | Non — à ajouter |
| C | Access token expiré + refresh invalide → déconnexion propre | E2E | Partiellement (`setup-wizard.spec.ts`, sans vérifier la redirection ni l'état `AuthProvider`) |
| D | 401 → refresh → retry → succès | Unitaire (`apiFetch`) | Non |
| E | 401 sans refresh token stocké → erreur immédiate, pas d'appel réseau inutile | Unitaire | Non |
| F | Ancienne clé `edusphere.session` valide présente seule → comportement attendu après correctif | Unitaire/E2E | Non (le cas exact de l'incident) |
| G | Ancienne clé présente mais session expirée côté serveur | Unitaire | Non |
| H | Ancienne clé malformée (JSON invalide) | Unitaire | Non |
| I | Nouvelle clé valide (cas nominal actuel) | E2E | Oui, implicitement |
| J | Plusieurs requêtes 401 quasi simultanées → un seul refresh réel | Unitaire (mock réseau) | Non — couvre directement le risque §9 |
| K | Utilisateur non authentifié accède à une page protégée → redirection | E2E | Probablement couvert indirectement par `AuthGate`, à confirmer explicitement |
| L | Logout → session localement et serveur invalidée, aucun résidu | E2E | Non explicitement isolé |

## 14. UX

Le message brut `"Could not validate credentials"` est un texte anglais technique, non traduit,
qui **peut être exposé directement à l'utilisateur** dès lors qu'un écran affiche
`err.message`/`ApiError.message` sans le reformuler — confirmé comme pattern existant dans
plusieurs composants Web (`err instanceof ApiError ? err.message : "Une erreur est survenue."`,
présent tel quel dans plusieurs pages, ex. `DashboardPage`). Le Mobile a déjà résolu ce problème via
`toUserMessage()` centralisé ; le Web n'a pas d'équivalent.

Message recommandé (conceptuel, non implémenté) : remplacer l'affichage brut d'un `ApiError` de
statut 401 par quelque chose comme *"Votre session a expiré. Veuillez vous reconnecter."* — un
tel formatage existe déjà partiellement dans `AuthProvider.tsx::formatSchoolContextError` (ligne
40 : `"Votre session a expiré. Reconnectez-vous pour continuer."` pour le contexte école), un
précédent direct à généraliser.

## 15. Architecture corrective proposée

Priorité : sécurité > stabilité > UX > simplicité > compatibilité > maintenabilité.

1. **Migration douce de clé (une fois, au démarrage de `session.ts`)** :
   ```
   getStoredTokens() :
     valeur = localStorage["edulinkage.session"]
     si absente :
       ancienne = localStorage["edusphere.session"]
       si présente et JSON valide avec les deux champs attendus :
         écrire sous "edulinkage.session"
         supprimer "edusphere.session"
         valeur = ancienne
     retourner valeur (ou null)
   ```
   Aucun contrôle JWT n'est contourné : la valeur migrée est un `refresh_token`/`access_token` **déjà émis légitimement par ce serveur pour cet utilisateur** — la migrer d'une clé de stockage à une autre ne change ni son contenu ni sa validité. Si l'access_token est expiré, le flux normal `apiFetch` (401 → refresh) s'applique ensuite sans changement. Si le refresh_token est également invalide/expiré côté serveur, `refresh()` renverra 401 normalement — la migration ne fait que donner au flux existant une chance de fonctionner avec des tokens qui, avant, n'étaient simplement jamais lus.
   JSON malformé sous l'ancienne clé → traité comme absent (comportement actuel de `getStoredTokens` déjà tolérant au JSON invalide via `try/catch`).

2. **Porter `onSessionExpired`/notification d'échec définitif** du Mobile vers le Web (`api/client.ts` + `AuthProvider.tsx`), pour que `status` repasse à `"anonymous"` immédiatement après un refresh explicitement rejeté par le serveur, sans attendre un remontage.

3. **Distinguer réseau/timeout vs rejet explicite** dans `refreshTokens()` (Web), même pattern que Mobile — ne jamais détruire une session pour une simple coupure réseau.

4. **"Single refresh in flight"** — mémoriser la promesse de refresh en cours (variable de module, réinitialisée une fois résolue) ; toute requête 401 concurrente attend cette même promesse au lieu d'en déclencher une nouvelle.

5. **Message utilisateur générique pour un 401** — généraliser le pattern déjà présent dans `formatSchoolContextError` à l'ensemble des affichages d'erreur API, pour ne plus jamais exposer un message technique brut.

Aucun changement backend n'est nécessaire — tout le mécanisme corrigé reste côté client, consommant les endpoints existants tels quels.

## 16. Découpage des commits

**Commit 1 — Session migration compatibility**
- Objectif : lire l'ancienne clé `edusphere.session` en repli si la nouvelle est absente, migrer silencieusement, ne jamais perdre une session valide lors d'un futur renommage similaire.
- Fichiers : `apps/web/lib/auth/session.ts`, `apps/web/lib/auth/AuthProvider.tsx` (clé école, même traitement), `apps/mobile/lib/auth/session.ts` (par cohérence, même si non urgent — app non publiée).
- Risques : faible — lecture seule d'une clé existante, migration additive, aucun changement de format.
- Tests : F, G, H (§13).
- Rollback : trivial (revert du fichier), aucune donnée serveur concernée.

**Commit 2 — 401 refresh/retry hardening**
- Objectif : porter `onSessionExpired`, la distinction réseau/rejet, et le verrou "single refresh in flight" vers `apps/web/lib/api/client.ts` + `AuthProvider.tsx`.
- Fichiers : `apps/web/lib/api/client.ts`, `apps/web/lib/auth/AuthProvider.tsx`.
- Risques : moyen — modifie un chemin critique traversé par tous les modules ; nécessite une revue attentive pour ne pas introduire de régression sur le cas nominal (401 → refresh → retry qui fonctionne déjà).
- Tests : B, C, D, E, J.
- Rollback : possible indépendamment du Commit 1 (fichiers distincts, changements orthogonaux).

**Commit 3 — E2E auth resilience**
- Objectif : ajouter les scénarios de test manquants identifiés en §13 (concurrence, ancienne clé, redirection effective après échec de refresh).
- Fichiers : nouveaux specs dans `apps/web/e2e/`.
- Risques : faible — tests uniquement, aucun impact production.
- Tests : eux-mêmes (K, L notamment).
- Rollback : trivial.

**Commit 4 (optionnel) — UX message générique**
- Objectif : généraliser le formatage d'erreur 401 façon `formatSchoolContextError` à l'ensemble des écrans.
- Fichiers : potentiellement plusieurs pages Web consommant `ApiError` directement — périmètre à confirmer lors de l'implémentation, pas de cette Discovery.
- Risques : faible, cosmétique.
- Tests : vérification visuelle + E2E existants inchangés.
- Rollback : trivial.

Ce découpage n'est pas imposé comme rigide : si l'implémentation révèle qu'un regroupement (ex. Commit 1+2) est plus sûr à tester ensemble, cela reste cohérent avec l'esprit de cette proposition.

## 17. Risques

- Toute modification du chemin `apiFetch` touche **tous** les modules authentifiés du Web — la couverture de test (§13) doit être en place **avant** le Commit 2, pas après.
- Un verrou "single refresh in flight" mal implémenté (ex. promesse jamais réinitialisée en cas d'erreur) pourrait bloquer indéfiniment tous les refreshs suivants — nécessite un `finally` explicite pour libérer le verrou dans tous les cas (succès, échec, exception).
- La migration douce de clé doit être testée avec un JSON réellement malformé et avec des champs manquants, pas seulement le cas nominal.
- Aucun risque identifié pour PostgreSQL, RLS, RBAC, ou l'isolation multi-tenant — le périmètre de cette correction reste entièrement côté client et sur des endpoints déjà existants et déjà testés côté serveur.

## 18. Definition of Done

- Aucune session valide n'est invalidée inutilement (vérifié par test F/G/H).
- Une ancienne session (`edusphere.session`) valide est migrée proprement vers la nouvelle clé sans perte, si un tel scénario devait se reproduire.
- Un access token expiré déclenche un refresh automatique transparent pour l'utilisateur (déjà vrai aujourd'hui — non régressé).
- Un refresh explicitement rejeté par le serveur déclenche une déconnexion propre et une redirection effective vers `/login` (actuellement absent — à corriger).
- Une requête 401 n'est rejouée qu'une seule fois maximum (déjà vrai aujourd'hui — non régressé).
- Aucune boucle infinie possible (déjà vrai aujourd'hui — non régressé).
- Plusieurs 401 simultanés ne provoquent qu'un seul refresh réel et ne détruisent jamais une session fraîchement obtenue (actuellement faux — à corriger, voir §9).
- Isolation multi-tenant, RBAC, PostgreSQL : inchangés (aucune modification prévue de ce côté).
- Aucune donnée modifiée en base au-delà des tables `user_sessions` déjà gérées par le flux normal existant.
- Suite `pytest` complète verte (aucun changement backend attendu, donc aucune régression possible côté backend).
- Suite E2E Web verte, incluant les nouveaux scénarios du Commit 3.

## Implementation outcome

- **Cause confirmée** : renommage de `edusphere.session` → `edulinkage.session` sans compatibilité de lecture (§5). Corrigée.
- **Correction réalisée** :
  - `apps/web/lib/auth/session.ts` : lecture en repli sur l'ancienne clé, migration silencieuse, validation de forme (`isStoredTokens`) — jamais de bypass des contrôles JWT/refresh.
  - `apps/web/lib/auth/AuthProvider.tsx` : même migration pour `selected_school_id` (revalidée contre la liste réelle d'écoles, jamais une preuve d'autorisation) ; écoute `onSessionExpired` pour resynchroniser l'état React après un refresh définitivement rejeté, où qu'il survienne dans l'app.
  - `apps/web/lib/api/client.ts` : verrou "single refresh in flight" (promesse mémorisée, libérée via `finally`), distinction explicite `NetworkError` (jamais traitée comme une session expirée) vs rejet serveur explicite, message générique pour tout 401 issu de `apiFetch` (ne remplace jamais le message de `/auth/login`, qui emprunte un chemin séparé).
  - `apps/mobile/lib/auth/session.ts` : migration identique appliquée par cohérence (app non publiée, risque nul).
  - Aucun fichier backend modifié — confirmé non nécessaire par la Discovery et par la suite de tests.
- **Tests** :
  - Backend : `pytest -q` → **355 passed**, 0 régression (aucun changement backend).
  - Web : `pnpm lint` → aucune erreur ; `pnpm type-check` → aucune erreur ; `docker compose build web` → build complet réussi (20 pages).
  - Nouveau fichier E2E `apps/web/e2e/auth-session-resilience.spec.ts` (7 scénarios : nouvelle clé valide, ancienne clé valide migrée, ancienne clé malformée, refresh réel réussi avec token corrompu, refresh définitivement invalide → redirection, un seul refresh sur 401 concurrents réels du dashboard, coupure réseau ≠ déconnexion) — **écrit mais non exécuté dans cette session** (voir limite ci-dessous).
  - Mobile : `tsc --noEmit` — même problème préexistant `expo/tsconfig.base` déjà documenté en Phase 27 Sprint 1 (résolution des jonctions pnpm cassée sous Git Bash/Windows), confirmé non lié à `session.ts` (aucune erreur spécifique à ce fichier dans la sortie).
- **Limites** : les navigateurs Playwright ne sont pas installés dans cet environnement, et leur installation (`playwright install chromium`) échoue avec la même erreur `MODULE_NOT_FOUND` que `tsc`/`next` en local (résolution de jonctions pnpm sous Git Bash/Windows — cause déjà identifiée, pas nouvelle). Les 7 scénarios E2E ci-dessus n'ont donc **pas pu être exécutés réellement** dans cette session ; ils devront être validés sur un environnement où Playwright peut réellement tourner (CI GitHub Actions, ou une machine Linux/macOS) avant d'être considérés comme une preuve de bon fonctionnement.

## 19. Recommandation finale

Traiter cette correction en 3 commits distincts et testés indépendamment (§16), dans l'ordre
proposé (la migration douce de clé d'abord, car elle seule règle directement l'incident déjà
observé ; le durcissement 401/refresh ensuite, car il règle un risque latent plus large mais non
encore matérialisé en production ; les tests E2E en dernier pour verrouiller les deux). Réutiliser
explicitement le code déjà existant et déjà éprouvé côté Mobile (`onSessionExpired`, distinction
réseau/rejet, `toUserMessage`) plutôt que d'concevoir un nouveau mécanisme — cohérent avec le
principe déjà appliqué dans tout ce projet de réutilisation des patterns existants.
