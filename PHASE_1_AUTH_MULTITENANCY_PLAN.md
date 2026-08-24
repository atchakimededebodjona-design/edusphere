# PHASE 1 — AUTH + MULTI-TENANCY — EduSphere

Document de référence pour l'exécution de la Phase 1 par l'agent (Antigravity / Claude Code).
Prérequis : Phase 0 terminée et stable (voir rapport de Phase 0 — `docker compose up` démarre
web/api/db/redis, `GET /api/v1/health` répond 200, CI verte).

---

## 1. Objectif

Construire le socle d'authentification et de multi-tenancy sur lequel toutes les phases
suivantes (élèves, académique, finance, etc.) vont s'appuyer :

- comptes utilisateurs (`users`) ;
- organisations et écoles (`organizations`, `schools`) — la structure tenant ;
- rôles et permissions (`roles`, `permissions`, `role_permissions`, `user_roles`) — RBAC ;
- sessions et refresh tokens (`user_sessions`, `user_devices`) ;
- isolation stricte des données entre tenants.

**Toujours pas de logique métier scolaire** (pas d'élèves, classes, notes, finance). Ce module
est un prérequis technique, pas une fonctionnalité pédagogique.

## 2. Pourquoi cette phase maintenant

Le document d'architecture (§46, §50) place explicitement Auth + Multi-tenancy en Phase 1,
immédiatement après le bootstrap, car **tout le reste du produit dépend de cette fondation** :
sans tenant isolation fiable, aucune donnée scolaire ne peut être stockée en sécurité.

Le cahier des charges (§5, §6) impose :
- une isolation stricte entre établissements (« le système doit empêcher techniquement l'accès
  aux données d'un autre établissement ») ;
- un modèle RBAC par rôles avec permissions granulaires ;
- authentification complète (inscription, connexion, récupération de compte, sessions
  sécurisées, gestion des appareils, déconnexion distante).

Le document d'architecture liste un test critique obligatoire avant tout lancement
(« Test 1 — Isolation tenant : Utilisateur École A → impossible d'accéder aux données École B »).

## 3. Décisions prises pour cadrer la phase

| Sujet | Décision | Justification |
|---|---|---|
| Modèle tenant | `Organization` = racine du tenant. Une `Organization` peut posséder plusieurs `School` (cas des groupes scolaires). `Campus`, `Country` (en tant qu'entité gérée), `Partner` : **différés** (Phases 2/8/13). | Le cahier des charges décrit une hiérarchie `platform → country → partner → school → campus`, mais la Phase 1 de la roadmap officielle (architecture §46) ne demande explicitement que `users, organizations, schools, roles, permissions, sessions, RBAC, tenant isolation`. Construire `campus`/`partner` maintenant serait de la sur-ingénierie prématurée (règle explicite du projet). |
| Auth | JWT access token (courte durée, 15 min) + refresh token opaque (longue durée, stocké hashé en base, rotation à chaque refresh). | Standard, stateless pour les vérifications de permissions à chaque requête, révocable via `user_sessions`. |
| Hashing mot de passe | `bcrypt` via `passlib`. | Standard éprouvé, déjà largement utilisé avec FastAPI. |
| RBAC | Rôles fixes définis par le cahier des charges (§6) : `SUPER_ADMIN`, `PLATFORM_SUPPORT`, `PARTNER_ADMIN`, `SCHOOL_ADMIN`, `DIRECTOR`, `ACCOUNTANT`, `TEACHER`, `STAFF`, `PARENT`, `STUDENT`. Permissions granulaires via table `permissions` + `role_permissions`. | Conforme au cahier des charges. `PARTNER_ADMIN` est inclus comme rôle mais sans logique métier partenaire (différée Phase 8). |
| Portée des rôles | `user_roles` peut être scoped à une organisation (`organization_id`) ou à une école précise (`school_id`), les deux nullable. `SUPER_ADMIN`/`PLATFORM_SUPPORT` ont les deux à `NULL` (rôle plateforme, hors tenant). | Un enseignant est rattaché à une école précise ; un `SCHOOL_ADMIN` peut être rattaché à l'organisation entière (groupe scolaire). |
| Isolation des données | Niveau 1 (contrôle d'accès applicatif via dependency FastAPI qui extrait le tenant du token) + Niveau 2 (filtrage systématique par `organization_id`/`school_id` dans chaque requête, appliqué via un helper de requête commun). Niveau 3 (PostgreSQL Row Level Security) : **activé** sur les tables tenant-scopées de cette phase, car le coût est faible et cela répond directement au Test 1 critique du cahier des charges. | Le document d'architecture dit "RLS lorsque pertinent" — pertinent ici car c'est la première phase avec de vraies données multi-tenant et un test de sécurité obligatoire. |
| OTP / vérification téléphone / MFA | **Différé** à une phase de durcissement sécurité ultérieure (hors périmètre Phase 1). | Nécessite un fournisseur SMS externe (choix non tranché, cf. règle Phase 0 sur les fournisseurs). La roadmap officielle Phase 1 (architecture §46) ne les liste pas dans les tests obligatoires (`login, logout, refresh, permissions, tenant isolation`). Seuls email/mot de passe sont couverts maintenant. |
| Inscription (`register`) | Le endpoint `register` crée une nouvelle `Organization` + sa première `School` + son premier utilisateur `SCHOOL_ADMIN` (flux d'onboarding B2B). Il n'y a pas d'auto-inscription libre pour les autres rôles (enseignants/parents/élèves sont invités par un admin — l'invitation elle-même est hors périmètre Phase 1, ajoutée en Phase 2/9/10 avec les modules concernés). | Cohérent avec un SaaS multi-tenant B2B : le premier compte crée le tenant. |
| Réinitialisation mot de passe | `forgot-password` / `reset-password` par email uniquement (token à usage unique, expirant). Pas de SMS. | Couverte par le cahier des charges §6, ne dépend d'aucun fournisseur cloud non tranché (email via SMTP configurable, déjà prévu par `.env.example`). |

## 4. Périmètre inclus

### Base de données (migrations Alembic)
- `organizations` (id, name, slug, country_code, timezone, currency, created_at, updated_at)
- `schools` (id, organization_id FK, name, slug, address, phone, email, timezone, currency, created_at, updated_at)
- `users` (id, email UNIQUE, phone NULLABLE, hashed_password, is_active, is_platform_admin, created_at, updated_at, last_login_at)
- `roles` (id, code UNIQUE, name, is_system_role) — pré-remplie via migration (seed) avec les 10 rôles du cahier des charges
- `permissions` (id, code UNIQUE, description) — pré-remplie avec un premier set granulaire (`users.read`, `users.write`, `organizations.manage`, `schools.manage`, `roles.manage`, etc.)
- `role_permissions` (role_id FK, permission_id FK)
- `user_roles` (id, user_id FK, role_id FK, organization_id FK NULLABLE, school_id FK NULLABLE, created_at)
- `user_sessions` (id, user_id FK, refresh_token_hash, device_id NULLABLE, ip, user_agent, created_at, expires_at, revoked_at NULLABLE)
- `user_devices` (id, user_id FK, device_id, device_name, platform, last_seen_at)
- `password_reset_tokens` (id, user_id FK, token_hash, expires_at, used_at NULLABLE)
- Politiques PostgreSQL RLS sur `schools`, `user_roles` (scopées par organisation/école)

### API (`/api/v1/auth`, `/api/v1/organizations`, `/api/v1/schools`, `/api/v1/roles`)
- `POST /api/v1/auth/register` — crée organization + school + premier SCHOOL_ADMIN
- `POST /api/v1/auth/login` — retourne access + refresh token
- `POST /api/v1/auth/logout` — révoque la session courante
- `POST /api/v1/auth/refresh` — rotation du refresh token
- `POST /api/v1/auth/forgot-password`
- `POST /api/v1/auth/reset-password`
- `GET /api/v1/auth/me` — utilisateur courant + rôles + permissions effectives
- `GET /api/v1/auth/sessions` — liste des sessions/appareils actifs
- `DELETE /api/v1/auth/sessions/{id}` — déconnexion distante d'un appareil
- `GET/POST/PATCH /api/v1/organizations`, `/api/v1/schools` (CRUD minimal, protégé par permissions)
- `GET /api/v1/roles`, `GET /api/v1/permissions` (lecture seule, pour construire l'UI de gestion des droits plus tard)

### Backend (structure)
```
apps/api/app/
├── core/
│   ├── security.py       # hashing, JWT encode/decode, dependency get_current_user
│   └── permissions.py    # décorateur/dependency require_permission("x.y")
├── modules/
│   ├── auth/              # register, login, logout, refresh, password reset
│   ├── organizations/
│   ├── schools/
│   └── rbac/               # roles, permissions, user_roles
```
(reprend la structure `modules/` prescrite par le document d'architecture §4)

### Frontend web (`apps/web`)
- `app/(auth)/login`, `app/(auth)/register` — pages minimales connectées à l'API
- `lib/auth/` — client API auth, stockage du token (cookie httpOnly via l'API, pas de localStorage)
- Middleware Next.js de protection de route basique (redirection si non authentifié)

### Tests obligatoires (cf. document d'architecture §46 et cahier des charges §33/45)
- login / logout / refresh (succès + échecs : mauvais mot de passe, token expiré, token révoqué)
- permissions (un `TEACHER` ne peut pas appeler un endpoint réservé à `SCHOOL_ADMIN`)
- **isolation tenant** : un utilisateur de l'École A ne peut ni lire ni modifier une ressource de l'École B, y compris en forgeant un `organization_id`/`school_id` dans la requête
- rotation de refresh token (l'ancien token devient invalide après usage)

## 5. Hors périmètre (explicitement exclu)

- `campus`, `partners`, `partner_schools`, `country` en tant qu'entités gérées (Phases 2/8/13) — `country_code` reste un simple champ texte pour l'instant
- OTP, vérification téléphone, MFA, notifications SMS/WhatsApp (phase de durcissement future)
- Élèves, classes, notes, présence, finance (Phases 3 à 7)
- White-label, branding, domaines personnalisés (Phase 14)
- Invitation d'utilisateurs par email avec workflow complet (ajoutée avec les modules concernés en Phase 2+)
- Mobile : l'app Expo reste au stade Phase 0 (écran minimal) ; l'intégration auth mobile est traitée avec le Portail Enseignant/Parent (Phases 9-10)

## 6. Risques identifiés

- **Sur-ingénierie du modèle tenant** : ajouter `campus`/`partner` maintenant « pour préparer le terrain » va à l'encontre de la règle du projet. À éviter strictement — seuls `organization` et `school` sont créés.
- **RLS mal configuré** : une politique RLS incorrecte peut soit bloquer des requêtes légitimes soit, pire, laisser passer une fuite si mal écrite. Chaque politique doit être testée explicitement par le test d'isolation tenant avant d'être considérée fiable — **ne pas se reposer uniquement sur RLS**, le filtrage applicatif (Niveau 1+2) reste la protection primaire.
- **Confusion rôle plateforme vs rôle tenant** : `SUPER_ADMIN`/`PLATFORM_SUPPORT` doivent être strictement impossibles à obtenir via le endpoint `register` public — à vérifier par un test dédié.
- **Sécurité JWT** : `JWT_SECRET_KEY` doit rester le placeholder d'exemple en dev uniquement ; jamais de valeur par défaut faible utilisable en production (déjà couvert par `.env.example` de la Phase 0, à rappeler dans le rapport final).
- **Réutilisation de refresh token volé** : la rotation à chaque refresh limite l'impact, mais sans détection de réutilisation (« refresh token reuse detection ») un token volé reste exploitable jusqu'à expiration. Envisageable en durcissement futur, pas bloquant pour cette phase.

## 7. Tests / critères de réussite

- `pytest` (apps/api) : suite complète couvrant register/login/logout/refresh/permissions/tenant isolation, verte
- Test explicite : utilisateur École A → 403/404 sur une ressource École B (via API réelle, pas seulement unitaire)
- Test explicite : `register` ne permet jamais de créer un `SUPER_ADMIN`/`PLATFORM_SUPPORT`
- `docker compose up` + `alembic upgrade head` appliquent toutes les migrations sans erreur sur une base vierge
- CI (lint, type-check, tests) verte
- Aucune régression sur le health check de la Phase 0

## 8. Rapport attendu en fin de phase

Même format imposé que la Phase 0 :
1. Objectif · 2. Fichiers créés · 3. Fichiers modifiés · 4. Base de données · 5. API ·
6. Fonctionnalités · 7. Tests · 8. Résultats des tests · 9. Problèmes rencontrés ·
10. Corrections · 11. Risques · 12. Prochaine phase (Phase 2 — Administration scolaire)

## 9. Règle de transition

La Phase 2 (Administration scolaire : années scolaires, niveaux, classes, matières, salles,
enseignants) ne démarre qu'après validation explicite que la Phase 1 est stable : tests
d'isolation tenant verts, CI verte, rapport de phase relu.

---

## 10. Prompt exécutable

Bloc à copier-coller comme instruction de départ pour l'agent :

> Exécute la PHASE 1 (Auth + Multi-tenancy) du projet EduSphere telle que définie dans
> `PHASE_1_AUTH_MULTITENANCY_PLAN.md`. Respecte strictement le périmètre inclus/exclu : pas de
> campus/partenaires/country en tant qu'entités gérées, pas d'OTP/MFA/SMS, pas de module métier
> scolaire (élèves, classes, notes, finance restent hors périmètre). Construis le modèle
> `Organization` → `School` avec RBAC (`roles`, `permissions`, `role_permissions`, `user_roles`
> scopés organisation/école) et JWT access + refresh token avec rotation, sessions révocables.
> Implémente les endpoints listés en section 4, active PostgreSQL RLS sur les tables
> tenant-scopées, et ajoute les pages minimales `login`/`register` côté web. Avant d'implémenter,
> propose le plan détaillé des fichiers à créer/modifier (schéma des migrations Alembic inclus)
> et attends ma validation. Après implémentation, exécute la suite de tests (section 7), avec en
> particulier un test réel d'isolation tenant (École A ne peut pas accéder aux données de l'École
> B) et un test garantissant qu'aucun rôle plateforme ne peut être obtenu via `register`. Termine
> par le rapport de phase au format imposé (section 8).
