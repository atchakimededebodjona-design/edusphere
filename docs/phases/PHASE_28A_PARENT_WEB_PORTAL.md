# Phase 28A — Parent Web Portal & Production Preparation

Suite au Discovery pré-pilote (gaps classés A/B/C/D), cette sous-phase traite uniquement le
premier gap classé **bloquant pilote** : l'absence de portail web pour les parents, alors que le
backend `apps/api/app/modules/parent/` est complet, testé (`tests/test_parent.py`, 16 tests) et
déjà consommé par le mobile (`apps/mobile/app/(parent)/`) depuis la Phase 21.

## Ce qui a été ajouté

Un portail parent web, entièrement en lecture seule, sous `/parent` :

- `/parent` — tableau de bord (liste courte des enfants).
- `/parent/children` — liste complète des enfants liés au compte.
- `/parent/children/{id}` — détail d'un enfant en 4 onglets : Présence, Notes, Bulletins (avec
  téléchargement PDF via le mécanisme sécurisé existant), Frais (solde + historique des paiements
  + reçus).
- `/parent/notifications` — réutilise tel quel `app/(app)/notifications/page.tsx` (ré-export
  direct, aucune dépendance à l'espace admin dans ce composant).

**Aucun endpoint backend créé ni modifié.** Le portail consomme exclusivement les endpoints
`/api/v1/parent/*` existants (`apps/web/lib/parent/client.ts`), chacun revalidant côté serveur
que l'élève ciblé appartient bien à l'utilisateur courant (`_get_child_or_404`) — un `student_id`
dans l'URL du web n'est donc jamais une preuve d'autorisation en soi, exactement comme pour le
mobile.

## Architecture de routage

Le portail vit dans un groupe de routes séparé (`apps/web/app/parent/`, un **vrai segment
d'URL**, pas un groupe `(parent)` — voir piège ci-dessous), avec son propre gate
(`ParentGate.tsx`) qui ne vérifie que le statut de connexion, sans la résolution
organisation/école qu'exige `app/(app)/AuthGate.tsx` : un parent voit ses enfants toutes écoles
confondues (`parent/service.py::list_children`, sans notion de "tenant actif"), une résolution
d'école unique n'aurait pas de sens pour ce compte.

- `AuthProvider.login()` renvoie désormais `Me` (au lieu de `void`) pour que la page de connexion
  puisse rediriger immédiatement un compte dont **tous** les rôles sont `PARENT` vers `/parent`
  (`lib/auth/roles.ts::isParentOnlyAccount`), sans attendre un rendu supplémentaire.
- `AuthGate.tsx` (espace admin) redirige aussi tout compte parent-only qui atteindrait directement
  une route admin (URL tapée, rechargement) — avant toute résolution de tenant.
- Un compte qui cumule un rôle `PARENT` et un rôle admin/staff (ex. un directeur tuteur de son
  propre enfant) n'est jamais renvoyé hors de `/parent` (`hasAnyParentRole`) : les deux espaces
  restent accessibles.

**Piège rencontré et corrigé** : un premier essai utilisait un groupe de routes `(parent)`
(parenthèses) en pensant obtenir un préfixe d'URL — en Next.js App Router, un groupe entre
parenthèses est retiré de l'URL, ce qui faisait entrer `(parent)/page.tsx` et `(parent)
/notifications/page.tsx` en collision directe avec `(app)/page.tsx` et `(app)/notifications/page.tsx`
(même URL `/` et `/notifications`), détecté par `next build` ("two parallel pages"). Corrigé en
utilisant un vrai dossier `app/parent/` (segment d'URL réel).

## Ce qui n'a PAS été fait (hors périmètre, par consigne)

TLS réel, choix d'hébergeur, domaine réel, SMTP réel, paiement en ligne, nouveau RBAC, RLS sur
`organizations`, correction de la dérive Alembic historique, toute fonctionnalité commerciale
(IA, WhatsApp, SMS, chat, offline-first, comptabilité, multi-devises).

## Variables d'environnement — audit (aucune modification)

`PUBLIC_BASE_URL`, `PUBLIC_WEB_BASE_URL`, `CORS_ALLOWED_ORIGINS`, `NEXT_PUBLIC_API_URL`,
`SMTP_*`, `EMAIL_PROVIDER` sont déjà présentes et cohérentes dans `.env.example`, alignées avec
`docs/deployment/PRODUCTION_CONFIGURATION.md` — rien à corriger dans cet exemple. Le portail
parent ne consomme aucune variable supplémentaire.

## Découverte critique, hors périmètre de cette sous-phase — `NEXT_PUBLIC_API_URL`

En validant le nouveau portail par des tests Playwright réellement exécutés (voir section
suivante), une dérive de configuration **préexistante, sans rapport avec le portail parent
lui-même**, a été découverte :

`apps/web/next.config.js` (introduit Phase 26.2, CSP) fait :

```js
env: {
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "https://api.edulinkage.com",
},
```

Ce bloc `env` de Next.js **fixe** `process.env.NEXT_PUBLIC_API_URL` à ce placeholder dès que la
variable n'est pas explicitement exportée avant `pnpm dev`/`next build` — ce qui rend inopérant le
repli `?? "http://localhost:8000"` déjà présent dans `lib/api/client.ts` (qui ne voit jamais une
valeur vide, seulement ce placeholder non vide). Conséquence concrète, observée réellement dans un
navigateur Chromium piloté par Playwright : toute tentative de connexion/inscription locale sans
avoir exporté `NEXT_PUBLIC_API_URL=http://localhost:8000` échoue silencieusement côté utilisateur
("Une erreur est survenue"), la requête réelle partant vers `https://api.edulinkage.com` (domaine
non résolu/inexistant), bloquée par CORS avant même d'atteindre le réseau.

**Pourquoi ceci n'a jamais été détecté avant** : `.github/workflows/ci.yml` ne contient aucun job
Playwright (seulement lint/type-check/build pour le web) — la suite `apps/web/e2e/` n'a donc
**jamais été exécutée en CI**. En local, les navigateurs Playwright n'avaient jamais pu être
installés dans cet environnement avant cette session (blocage Windows/pnpm documenté
`PHASE_27_SPRINT_1_1_AUTH_SESSION_DISCOVERY.md`) — **cette session est, à la connaissance de ce
dépôt, la première fois que la suite Playwright s'exécute réellement avec de vrais navigateurs**,
ce qui explique qu'aucune phase précédente n'ait pu rencontrer ce problème. Reproduit à l'identique
sur `dashboard.spec.ts` (fichier non modifié par cette phase), confirmé indépendant de Phase 28A
par `git stash` des changements de cette phase avant nouvel essai.

**Non corrigé ici** (hors périmètre explicite de cette sous-phase — fichier de configuration
partagé, sans rapport avec le portail parent) : contournement utilisé uniquement pour valider ce
travail, `NEXT_PUBLIC_API_URL=http://localhost:8000 npx playwright test`. À traiter dans une phase
dédiée à la fiabilisation de la suite E2E (voir aussi l'absence de job Playwright en CI, jamais
mise en place).

## Tests

- `apps/web/e2e/parent-portal.spec.ts` (nouveau, 2 scénarios) : connexion parent → redirection vers
  `/parent` (jamais l'espace admin) → liste des enfants → détail d'un enfant → présence → notes →
  bulletin (téléchargement) → frais/paiements/reçu ; et isolation stricte entre deux parents
  (liste, navigation directe vers l'enfant d'autrui, et vérification API directe confirmant un
  404). Exécutés réellement (Chromium), **2/2 passés**.
- Backend : `pytest -q tests/test_parent.py` réexécuté (aucun changement backend) — 16/16 passés,
  confirmant l'absence de régression.
