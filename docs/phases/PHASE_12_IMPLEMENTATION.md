# PHASE 12 IMPLEMENTATION REPORT

Date : 2026-09-04
Périmètre : `apps/mobile` uniquement — aucun autre dossier du monorepo modifié.

## 1. Objectif

Rendre l'application mobile résiliente aux erreurs réseau courantes (coupure, timeout, refresh
token expiré) sans introduire d'offline-first, sans modifier le backend, sans nouvelle
dépendance. Corriger le problème actif identifié en Phase 12 Discovery : plusieurs écrans
restaient bloqués indéfiniment sur "Chargement..." lorsqu'une requête échouait, faute de
`.catch()`.

## 2. État initial

Inspection réelle du code (pas de supposition) avant toute modification :

- `lib/api/client.ts` : `apiFetch` centralisé, utilisé par tous les modules (`academics`,
  `attendance`, `grades`, `students`, `parent`) sauf `auth/client.ts::login`/`::logout` (raw
  `fetch`, avant authentification / best-effort) et `parent/client.ts::downloadReportCardPdf`
  (transfert binaire via `expo-file-system`, logique de refresh dupliquée intentionnellement et
  documentée comme telle).
- Aucun timeout nulle part : ni sur `fetch`, ni sur `apiFetch`, ni sur `refreshTokens`.
- `AuthProvider.tsx` : si `refreshTokens()` échoue à l'intérieur d'`apiFetch`, les tokens sont
  effacés (`clearStoredTokens()`) mais l'état React (`status`, `me`) n'est jamais notifié — aucun
  mécanisme de communication entre ce module utilitaire (hors de l'arbre React) et le contexte
  d'authentification.
- `(teacher)/_layout.tsx` et `(parent)/_layout.tsx` redirigent déjà vers `/login` quand
  `status === "anonymous"` — mécanisme de routing existant et suffisant, à réutiliser tel quel.
- 6 des 11 écrans identifiés chargeaient leurs données via un `.then(setX)` ou une IIFE `async`
  **sans aucun `.catch()`** : un rejet de promesse (réseau ou timeout) laissait l'état `null`
  pour toujours, et l'écran restait bloqué sur son indicateur de chargement.
- Un 7e écran (`ReportCardsTab` dans `(parent)/children/[studentId].tsx`) avait déjà un
  `.catch()` et un état d'erreur, mais **aucun bouton Retry**.
- Aucune infrastructure de test mobile n'existe (confirmé : pas de Jest, pas de fichier
  `*.test.*`/`*.spec.*`, `package.json` ne définit que `type-check`). La CI (`.github/workflows/
  ci.yml`, job `mobile`) exécute uniquement `tsc --noEmit`, pas de lint mobile (aucun
  `.eslintrc` dans `apps/mobile`, contrairement à `apps/web`).

## 3. Écrans traités

11 fichiers sous `app/` constituent les "11 écrans" du périmètre.

| Écran | Problème | Correction | Retry | Timeout |
|---|---|---|---|---|
| `app/index.tsx` (racine) | Aucun — pas d'appel réseau propre, ne fait que lire `useAuth().status` | Aucune (vérifié, hors périmètre) | N/A | N/A |
| `app/login.tsx` | Catch déjà présent mais message générique, sans distinction timeout/coupure réseau | `toUserMessage()` centralisé ; `login`/`logout` passent désormais par `fetchWithTimeout` | Resoumission manuelle du formulaire (inchangé) | 15s (login) / 5s (logout, best-effort) |
| `(teacher)/_layout.tsx` | Aucun — gate uniquement sur `status`, pas d'appel réseau propre | Aucune (bénéficie automatiquement de la correction AuthProvider, §5) | N/A | N/A |
| `(teacher)/index.tsx` | `schoolClasses.list().then(setClasses)` sans `.catch()` — bloqué indéfiniment sur coupure réseau | Converti vers `useAsyncData` + `ErrorView` | Oui | 15s (via `apiFetch`) |
| `(teacher)/classes/[classId].tsx` | IIFE `async` sans try/catch, 4 appels réseau en cascade — bloqué indéfiniment | Converti vers `useAsyncData` (fetcher composé `loadClassDetail`) + `ErrorView` | Oui | 15s |
| `(teacher)/attendance/[classId].tsx` | IIFE `async` sans try/catch, jusqu'à 5 appels séquentiels dont création de session — bloqué indéfiniment | Converti vers `useAsyncData` (fetcher composé `loadAttendanceSetup`) + `ErrorView` ; bouton "Enregistrer l'appel" utilise `toUserMessage` | Oui (chargement) + resoumission (enregistrement, déjà existante) | 15s |
| `(teacher)/assessments/[classSubjectId].tsx` | `assessments.list().then(setItems)` sans `.catch()` | Converti vers `useAsyncData` + `ErrorView` | Oui | 15s |
| `(teacher)/assessments/[assessmentId]/grades.tsx` | IIFE `async` (`Promise.all`) sans try/catch pour le chargement initial | Converti vers `useAsyncData` (fetcher composé `loadGradeEntrySetup`) + `ErrorView` ; bouton "Enregistrer les notes" utilise `toUserMessage` | Oui (chargement) + resoumission (enregistrement, déjà existante) | 15s |
| `(parent)/_layout.tsx` | Aucun — gate uniquement sur `status` | Aucune (bénéficie automatiquement de la correction AuthProvider) | N/A | N/A |
| `(parent)/index.tsx` | `childrenClient.list().then(setItems)` sans `.catch()` | Converti vers `useAsyncData` + `ErrorView` | Oui | 15s |
| `(parent)/children/[studentId].tsx` | Onglets Présence et Notes sans `.catch()` (bloqués indéfiniment) ; onglet Bulletins avait un `.catch()` mais aucun Retry | Les 3 onglets convertis vers `useAsyncData` + `ErrorView`, harmonisés | Oui, ajouté aux 3 onglets (dont Bulletins qui ne l'avait pas) | 15s |

**Limitation pré-existante identifiée mais volontairement non corrigée** (hors périmètre,
documentée pour rester honnête sur ce qui a réellement changé) :
- `(teacher)/index.tsx` et `(teacher)/classes/[classId].tsx` : si `currentSchoolId` est
  durablement `null` (utilisateur sans rôle scopé école), l'écran reste sur "Chargement..."
  indéfiniment — un problème de configuration/permission, pas une erreur réseau. Comportement
  identique à avant cette phase.
- `(teacher)/attendance/[classId].tsx` : si aucune période académique ne couvre la date du jour,
  `term` reste `null` après un chargement réussi et l'écran reste sur "Chargement..." — même
  raison (configuration, pas réseau), comportement identique à avant.
- `parent/client.ts::downloadReportCardPdf` (téléchargement PDF) n'a pas de timeout : l'API
  `expo-file-system.downloadAsync` de cette version du SDK n'expose pas de mécanisme d'annulation
  aussi simple que l'`AbortController` de `fetch`. Ajouter un timeout ici aurait nécessité une
  logique sensiblement plus complexe pour un seul point d'entrée, non justifiée dans ce périmètre
  ciblé — le bouton reste déjà protégé par son propre état `openingId`/try-catch existant.

## 4. Architecture retenue

Trois petits ajouts centralisés plutôt qu'une logique dupliquée dans chaque écran :

- **`lib/api/client.ts`** : `fetchWithTimeout()` (wrapping `fetch` avec `AbortController`,
  15s par défaut) remplace l'appel `fetch` brut à l'intérieur d'`apiFetch` et de
  `refreshTokens()`, et est exporté pour `auth/client.ts::login`/`::logout` qui utilisaient un
  `fetch` direct (pré-authentification). Deux nouvelles classes d'erreur, `TimeoutError` et
  `NetworkError`, distinguent "délai dépassé" de "serveur injoignable" sans jamais réutiliser
  `ApiError` (qui porte toujours un vrai status HTTP serveur — les mélanger aurait été trompeur).
  `toUserMessage(err)` centralise la traduction de ces erreurs (+ `ApiError`) en un message
  humain, au lieu de dupliquer `err instanceof ApiError ? ... : "..."` dans chaque écran.
- **`lib/api/useAsyncData.ts`** (nouveau) : hook générique `Loading/Error/Success + retry()`
  pour les 8 écrans qui chargent des données au montage. Utilise une réf pour la fonction de
  chargement (pas une dépendance directe) afin que ce soit le tableau `deps` fourni par l'appelant
  — comme un `useEffect` classique — qui pilote le rechargement, pas l'identité de la fermeture
  recréée à chaque rendu. Une option `enabled` permet d'attendre qu'une dépendance obligatoire
  (ex. `currentSchoolId`) soit disponible sans déclencher un état d'erreur inapproprié.
- **`components/ScreenState.tsx`** (nouveau) : `LoadingView`/`ErrorView`, deux composants de
  présentation minimalistes réutilisés par les 8 écrans concernés, pour éviter de dupliquer huit
  fois le même bloc `View/ActivityIndicator/Text/TouchableOpacity`.

Ce choix évite la duplication du triplet loading/erreur/retry dans 8 fichiers différents tout en
restant délibérément petit — pas de bibliothèque de state/query externe (React Query, SWR...),
pas de nouvelle dépendance, seulement ~90 lignes de code réutilisant les patterns déjà en place
dans le projet (comparer à `apps/web/app/(app)/page.tsx` qui suit déjà un pattern
loading/erreur/vide analogue, non touché ici puisque hors périmètre web).

Les écrans à chargement multi-étapes (`classes/[classId]`, `attendance/[classId]`,
`assessments/[assessmentId]/grades`) ont chacun une fonction "fetcher" composée (`loadClassDetail`,
`loadAttendanceSetup`, `loadGradeEntrySetup`) qui regroupe la séquence d'appels réseau existante
en un seul résultat, passée telle quelle à `useAsyncData` — la logique métier de chaque séquence
n'a pas changé, seule sa gestion d'erreur l'a.

## 5. Auth refresh

**Avant** : dans `apiFetch`, un 401 déclenchait `refreshTokens()` ; si celui-ci renvoyait `false`
(refresh token invalide/expiré), les tokens locaux étaient effacés (`clearStoredTokens()`) mais
rien ne prévenait `AuthProvider` — `status` restait `"authenticated"` et `me` restait peuplé.
L'utilisateur voyait une coquille d'application apparemment connectée pendant que tous les appels
suivants échouaient silencieusement (unhandled côté écran, avant même la correction du §3).

**Après** :
- `lib/api/client.ts` expose `onSessionExpired(listener)` — un registre d'écouteurs minimal (pas
  de nouvelle dépendance de state management) permettant à ce module utilitaire, situé hors de
  l'arbre React, de notifier un événement sans y avoir de référence directe.
- `AuthProvider.tsx` s'abonne une fois au montage (`useEffect`) : à la notification, il repasse
  `me` à `null` et `status` à `"anonymous"`.
- `(teacher)/_layout.tsx` et `(parent)/_layout.tsx` redirigeaient **déjà** vers `/login` quand
  `status === "anonymous"` — aucune ligne de routing n'a donc été ajoutée ; la correction se
  branche sur ce mécanisme existant.
- **Distinction volontaire, ajoutée pendant l'implémentation** : `notifySessionExpired()` n'est
  appelé que lorsque le serveur **rejette explicitement** le refresh token (réponse HTTP non-ok
  de `/auth/refresh`). Si `refreshTokens()` échoue parce que le réseau est coupé ou que la
  requête de refresh time-out, l'exception (`NetworkError`/`TimeoutError`) est simplement
  remontée à l'appelant d'origine (l'écran affiche "Réessayer") **sans** effacer la session ni
  notifier `AuthProvider` — une coupure réseau transitoire ne doit pas déconnecter un utilisateur
  dont la session est en réalité toujours valide. Cette distinction n'était pas explicitement
  demandée dans la consigne mais découle directement de la règle "ne pas continuer à utiliser une
  session invalide" / "ne pas boucler indéfiniment" : il ne fallait pas non plus créer l'effet de
  bord inverse (déconnecter à tort sur un simple problème réseau).
- Aucune boucle infinie possible : `notifySessionExpired()` ne déclenche aucune nouvelle requête,
  seulement un changement d'état React ; le passage à `"anonymous"` est terminal jusqu'au
  prochain `login()` explicite.

## 6. Tests

Aucune infrastructure de test n'existe pour `apps/mobile` (confirmé avant toute modification —
pas de Jest, pas de fichier de test, pas de script `test` dans `package.json`) et ce périmètre
interdit explicitement d'en créer une pour ce seul correctif.

**Résultat réel obtenu** : le host de développement ne dispose d'aucun binaire Node/pnpm
accessible (`node`, `pnpm`, `npm` introuvables sur ce PowerShell — confirmé par
`Get-Command`/`where.exe` avant de conclure). Docker est disponible. Un conteneur temporaire
`node:20-alpine` a été utilisé pour exécuter, sur le `node_modules` déjà installé du monorepo,
l'équivalent exact du job CI `mobile` (`pnpm --filter @edusphere/mobile type-check`, soit
`tsc --noEmit`) :

```
docker run --rm -v "${PWD}:/workspace" -w /workspace/apps/mobile node:20-alpine \
  node node_modules/typescript/bin/tsc --noEmit
```

Résultat réel : **exit code 0, aucune erreur affichée**, sur l'ensemble du projet TypeScript
`apps/mobile` (tous les fichiers `**/*.ts`/`**/*.tsx` inclus par `tsconfig.json`, donc les 11
écrans, les 2 nouveaux fichiers, et les 3 fichiers `lib/api|auth` modifiés). Ceci couvre
réellement les points suivants de la liste demandée en §9 : succès normal (types cohérents de
bout en bout), absence de référence non résolue, et cohérence des signatures entre
`useAsyncData`, `ScreenState` et chaque écran appelant.

**Non exécuté, et pourquoi** : aucun test runtime (unitaire, composant, ou end-to-end) n'a été
lancé — ni pour le comportement réseau normal, ni pour l'erreur réseau simulée, ni pour le
timeout, ni pour le refresh token — car cela nécessiterait Metro/Expo (serveur de développement)
et un simulateur ou appareil, dont ni l'un ni l'autre n'est disponible dans cet environnement
(pas de Node exécutable en dehors du conteneur ponctuel utilisé pour `tsc`, pas de simulateur
iOS/Android, pas d'Expo Go connecté). Cette limitation est documentée honnêtement plutôt que
contournée par une affirmation non vérifiée.

## 7. Validation manuelle

Conformément à la règle de vérité de cette phase, distinction stricte entre ce qui a été
réellement vérifié et ce qui ne l'a pas été :

**Testé réellement** :
- Compilation TypeScript complète du package `apps/mobile` (0 erreur) — voir §6.
- Relecture manuelle ligne par ligne de chaque écran modifié pour confirmer que la logique
  métier préexistante (tri du roster, calcul de moyenne, verrouillage de session, sélection de
  période, navigation) est strictement préservée — seule la gestion d'erreur a changé.
- Vérification que `(teacher)/_layout.tsx` et `(parent)/_layout.tsx` n'ont subi aucune
  modification et que leur redirection existante vers `/login` sur `status === "anonymous"`
  couvre bien le nouveau cas déclenché par `onSessionExpired` (lecture de code, pas d'exécution).

**Non testé — limitation environnementale explicite** :
- Cas A (réseau normal), B (coupure réseau), C (rétablissement), D (timeout), E (session
  expirée) du §10 de la consigne : **aucun n'a pu être exécuté**. Cet environnement ne dispose
  d'aucun moyen de lancer l'application mobile (pas de serveur Metro/Expo démarrable — Node
  n'existe que dans un conteneur Docker ponctuel utilisé uniquement pour `tsc` — et aucun
  simulateur iOS/Android ni appareil physique connecté). Aucune de ces validations n'est donc
  affirmée comme effectuée : ce serait contraire à la règle de vérité de cette phase.
- Aucune capture d'écran, aucun log d'exécution réelle de l'app mobile ne peut donc être produit
  ici. Une validation manuelle réelle (Cas A à E) reste à faire par une personne disposant d'un
  poste avec Node/Expo et un simulateur ou appareil, avant tout déploiement pilote.

## 8. Fichiers modifiés

Créés :
- `apps/mobile/lib/api/useAsyncData.ts`
- `apps/mobile/components/ScreenState.tsx`

Modifiés :
- `apps/mobile/lib/api/client.ts`
- `apps/mobile/lib/auth/AuthProvider.tsx`
- `apps/mobile/lib/auth/client.ts`
- `apps/mobile/app/login.tsx`
- `apps/mobile/app/(teacher)/index.tsx`
- `apps/mobile/app/(teacher)/classes/[classId].tsx`
- `apps/mobile/app/(teacher)/attendance/[classId].tsx`
- `apps/mobile/app/(teacher)/assessments/[classSubjectId].tsx`
- `apps/mobile/app/(teacher)/assessments/[assessmentId]/grades.tsx`
- `apps/mobile/app/(parent)/index.tsx`
- `apps/mobile/app/(parent)/children/[studentId].tsx`

Non modifiés (inspectés, confirmés déjà corrects ou hors périmètre) :
- `apps/mobile/app/index.tsx`
- `apps/mobile/app/(teacher)/_layout.tsx`
- `apps/mobile/app/(parent)/_layout.tsx`
- `apps/mobile/lib/academics/client.ts`, `lib/attendance/client.ts`, `lib/grades/client.ts`,
  `lib/students/client.ts`, `lib/parent/client.ts`, `lib/auth/session.ts` — déjà routés via
  `apiFetch` (bénéficient automatiquement du timeout centralisé), aucune modification nécessaire.

Aucun fichier en dehors de `apps/mobile` n'a été touché.

## 9. Dépendances

Confirmé explicitement : **aucune nouvelle dépendance**. `apps/mobile/package.json` n'a pas été
modifié. Le timeout réseau utilise `AbortController`, une API standard déjà disponible dans
l'environnement React Native/Expo de ce projet (SDK 51) — aucun package externe requis.

## 10. Backend/Web

Confirmé explicitement :
- **Aucun changement backend** — `apps/api` n'a pas été touché.
- **Aucun changement Web** — `apps/web` n'a pas été touché.
- Aucune migration, aucun nouveau endpoint, aucune modification de contrat d'API.

## 11. Risques résiduels

| Niveau | Risque |
|---|---|
| Medium | Aucune validation runtime réelle (Cas A-E) n'a pu être effectuée dans cet environnement — le correctif est correct par relecture et type-check, mais son comportement en conditions réseau réelles reste à confirmer avant un déploiement pilote. |
| Low | `AuthProvider.loadMe()` (chargement initial au lancement de l'app) traite toujours tout échec de `me()` — y compris un simple timeout réseau au démarrage — comme "non authentifié", renvoyant à `/login` un utilisateur dont la session est en réalité valide. Corriger ce point demanderait un nouvel état (ex. "vérification différée") sortant du périmètre explicite de cette phase (propagation refresh→auth uniquement) ; documenté ici pour une phase future. |
| Low | Le téléchargement de PDF (`parent/client.ts::downloadReportCardPdf`) reste sans timeout — `expo-file-system.downloadAsync` de cette version ne propose pas de mécanisme d'annulation aussi direct que `fetch`/`AbortController`. Risque limité : action explicite unique de l'utilisateur, déjà protégée par son propre état de chargement/erreur. |
| Low | `useAsyncData` ne annule pas activement une requête en vol si l'utilisateur appuie sur "Réessayer" deux fois rapidement — un drapeau `cancelled` empêche une réponse obsolète d'écraser une réponse plus récente, donc pas de corruption de données, seulement une requête réseau superflue possible. |
| Low (préexistant, non aggravé) | Aucune infrastructure de test mobile n'existe toujours — accepté comme dette, conformément à la consigne explicite de ne pas en créer une pour ce correctif ciblé. |

## 12. Statut final

GO WITH NOTES

Le code est corrigé, cohérent, et vérifié par une compilation TypeScript réelle et complète
(0 erreur) sur l'ensemble du package mobile modifié. La réserve porte uniquement sur
l'impossibilité, dans cet environnement, d'exécuter une validation manuelle runtime (Cas A à E) —
absence de Node/Expo/simulateur en dehors d'un conteneur Docker ponctuel utilisé pour le seul
type-check. Cette validation manuelle reste recommandée avant tout déploiement pilote réel.
