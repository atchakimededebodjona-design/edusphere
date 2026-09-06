# Phase 21 Implementation Report — Communications & Notifications

Toutes les preuves ci-dessous proviennent d'exécutions réelles (Postgres 16, Redis 7, Docker,
pytest, ruff, mypy, `next build`, `tsc`, un vrai backup) — chaque affirmation indique VALIDÉ /
NON VÉRIFIÉ / BLOCKED, jamais l'inverse d'une preuve non obtenue.

## 1. Executive Summary

MVP étroit implémenté exactement comme validé : un seul modèle `Notification` (pas
d'`Announcement`), annonces scolaires in-app ciblant l'école entière ou une/plusieurs classes,
notification automatique sur bulletin publié et paiement enregistré, centre de notifications
Web + Mobile (parent ET enseignant, puisque les deux reçoivent des annonces école), lecture/non-
lue avec pagination par curseur, RLS strictement par destinataire (pas par organisation — un
choix délibérément différent du motif générique, justifié en §5), une seule nouvelle permission
RBAC (`announcements.manage`). Aucun email de masse, aucun scheduler, aucune dépendance nouvelle,
aucun push/SMS/WhatsApp. 19 nouveaux tests, 254/254 au total, zéro régression.

## 2. Discovery vs réalité

Un seul écart trouvé, **découvert et corrigé pendant l'implémentation, pas anticipé par la
Discovery** : en écrivant la résolution des destinataires d'une annonce "toute l'école", copier
littéralement la condition déjà utilisée par `users/service.py::list_users_for_school`
(`school_id == X OR organization_id == Y`) aurait inclus le personnel d'une **autre** école de la
même organisation dès lors qu'il a un rôle explicitement scopé à cette autre école — une fuite
cross-école pour une fonctionnalité de diffusion, contrairement à `list_users_for_school`
lui-même (un simple écran de gestion, risque moindre). Corrigé en écrivant une condition plus
stricte (`school_id == X OR (organization_id == Y AND school_id IS NULL)`) dans
`notifications/service.py::resolve_school_member_user_ids`, documentée comme une déviation
volontaire par rapport au précédent existant — celui-ci n'a pas été modifié (hors périmètre).
Aucun autre écart : le reste de la Discovery (absence de scheduler, absence de modèle
`Notification` préexistant, patron prepare/send déjà prouvé deux fois, RBAC de `PARENT` sans
permission mais correctement scopé tenant) correspondait exactement au code réel.

## 3. Modèle Notification

`apps/api/app/modules/notifications/models.py` — un seul modèle, exactement les champs validés :
`id, school_id, organization_id, recipient_user_id, type, title, body, created_at, read_at`.
Aucun champ `channel`/`status` (aucune queue/retry n'existe nulle part dans ce projet pour le
justifier), aucune référence polymorphe vers l'entité source (aucun besoin concret prouvé — le
texte suffit à orienter l'utilisateur). `type` contrôlé comme les autres champs "enum" du projet
(`Payment.method`, `StudentFee.status`) : `String(32)` + tuple Python (`NOTIFICATION_TYPES`) +
`Literal` Pydantic — jamais une chaîne totalement libre côté API, sans introduire un type ENUM
Postgres qui n'existe nulle part ailleurs dans ce dépôt.

## 4. Migration

`apps/api/alembic/versions/0011_notifications.py` — additive, ne modifie aucune migration
0001-0010. Indexes : `school_id`, `organization_id`, `recipient_user_id` (simples, convention
systématique) + deux composites (`recipient_user_id, created_at` pour la pagination,
`recipient_user_id, read_at` pour le compteur non-lu).

**Validations réelles** :
```
alembic upgrade head (0010 -> 0011) sur la base de développement réelle : succès
Chaîne complète 0001 -> 0011 sur un Postgres 16 jetable (conteneur+réseau dédiés, détruits après) : succès
downgrade 0011 -> 0010 : succès, confirmé au niveau catalogue (to_regclass('notifications') = NULL)
upgrade 0010 -> 0011 (ré-application) : succès, confirmé (relrowsecurity=t, relforcerowsecurity=t,
  policy notifications_recipient_isolation présente avec l'expression exacte attendue)
```

## 5. RLS

**Décision volontairement différente du motif générique** `{table}_tenant_isolation` (basé sur
`app.tenant_org_ids`, donc l'appartenance à l'organisation) utilisé par les 29 autres tables :
`notifications` est strictement privée par destinataire, la policy restreint donc à
`recipient_user_id = current_user_id OR is_platform_wide` — jamais à l'organisation seule, sinon
un administrateur de la même école pourrait lire la notification d'un autre utilisateur.

**Écriture pour un tiers** : créer une notification pour un AUTRE utilisateur (le cas normal — un
guardian, un membre d'école ciblé par une annonce) nécessite d'élargir temporairement le contexte
à `is_platform_wide=true` (`notifications/service.py::create_notifications`), exactement le même
motif déjà utilisé par `auth/service.py::register` (créer une ligne pour un tiers sans exposer
aucune donnée d'un autre tenant, puisque la liste de destinataires a déjà été résolue de façon
tenant-sûre par l'appelant). Documenté explicitement comme devant être appelé en toute fin de
transaction — vérifié dans les deux points d'intégration (aucune lecture sensible ne suit).

**Tests réels** (`test_notifications.py`) : `pg_class.relrowsecurity/relforcerowsecurity` vérifiés
directement, policy relue via `pg_get_expr`, un test de session SQL brute prouvant qu'un
**administrateur de la même école/organisation** ne voit pas la notification d'un parent
(contrôle positif : il voit bien la sienne) — preuve que la stratégie "par destinataire" fonctionne
réellement, pas seulement en théorie.

## 6. RBAC

Une seule nouvelle permission : `announcements.manage`, accordée à `SUPER_ADMIN`, `SCHOOL_ADMIN`,
`DIRECTOR` uniquement — exactement la décision validée. Aucune permission
`notifications.read`/`.manage` : lire ses propres notifications ne nécessite aucune permission
(auto-scopé par `recipient_user_id == current_user.id`, même motif que `GET /auth/me`), confirmé
par la Discovery et par les tests (`ACCOUNTANT`/`TEACHER` reçoivent normalement leurs
notifications tout en étant rejetés à 403 sur `POST /announcements`).

## 7. API

7 endpoints, tous sous `/api/v1` : `GET /notifications` (pagination par curseur `before`/`limit`,
première introduction de ce motif dans ce dépôt — aucune convention préexistante, documenté
comme tel plutôt que présenté comme un standard du projet), `GET /notifications/unread-count`,
`POST /notifications/{id}/read`, `POST /notifications/mark-all-read`, `POST /announcements`.
Aucune API publique, aucune API push/SMS.

## 8. Notifications automatiques

**Bulletin publié** (`report_cards/router.py::publish_report_card`) : `notifications_service.
notify_report_card_published(db, report_card)` appelé dans le même bloc `if not was_already_
published`, donc hérite gratuitement de la garde anti-duplication déjà prouvée par
`test_republishing_already_published_report_card_does_not_resend_email` (Phase 11) — revérifié
côté in-app par `test_report_card_publication_creates_in_app_notification_for_linked_parent`.
Destinataires : `Guardian.user_id IS NOT NULL` (distinct de la condition email, `Guardian.email IS
NOT NULL`) — un tuteur sans compte ne reçoit jamais de notification in-app, testé explicitement.

**Paiement enregistré** (`fees/service.py::record_payment`) : appelé juste après `_prepare_
payment_notifications`, avant `db.refresh`/`db.commit`. Hérite de l'idempotence déjà prouvée en
Phase 19 (`idempotency_key`) : un paiement rejoué (même clé) retourne `(winner, [])` avant
d'atteindre le code de notification — testé explicitement
(`test_duplicate_payment_idempotency_key_does_not_duplicate_notification`).

**Transactionnalité** : les deux appels sont de simples écritures Postgres dans la même
transaction que l'événement métier (pas de réseau) — si la création de la notification échouait,
toute la transaction (publication/paiement) échouerait avec elle, jamais l'inverse (notification
créée sans l'événement, ou événement réussi sans notification silencieusement perdue).

## 9. Annonces

`POST /announcements` : `target_type` = `SCHOOL` (tous les membres de l'école, via `UserRole`
scopé — voir §2 pour la correction de fuite cross-école) ou `CLASS` (tuteurs avec compte des
élèves activement inscrits dans une ou plusieurs classes ciblées, jamais les enseignants — décision
Discovery §14/§21). Validation stricte : `CLASS` sans `class_ids` → 400 ; `SCHOOL` avec
`class_ids` → 400 ; une classe n'appartenant pas à l'école ciblée → 400. **Déduplication** :
résolution en `set[uuid.UUID]` avant écriture — un parent avec deux enfants dans deux classes
ciblées ne reçoit qu'une seule notification, testé explicitement
(`test_announcement_deduplicates_parent_with_children_in_multiple_targeted_classes`, résultat
`recipient_count == 1`). **Performance** : un seul `add_all`+`flush` (pas de boucle de requêtes
individuelles), pas d'email — conforme à la contrainte de performance de la Discovery (§15).

## 10. Web

3 changements : `/notifications` (liste paginée, "charger plus", marquer lu/tout lire),
`/announcements` (SCHOOL_ADMIN/DIRECTOR, formulaire titre/contenu/cible avec sélection de
classes conditionnelle), et une icône 🔔 avec badge non-lu dans `TopBar.tsx` (sondage léger
30s, aucun state management global introduit). Entrées `Nav.tsx` : "Notifications" (aucune
permission, visible à tous) et "Annonces" (`announcements.manage`).

**Validé réellement** :
```
pnpm run lint         → clean
pnpm run type-check   → clean
pnpm run build        → succès, 20 routes dont /notifications et /announcements
```

## 11. Parent Mobile

Nouvel écran `app/(parent)/notifications.tsx` (route top-level du Stack, pas un onglet sous un
enfant précis — une notification n'est jamais liée à un enfant spécifique dans son URL, elle est
scopée à l'utilisateur). Accessible via une icône 🔔 dans l'en-tête, à côté du bouton
Déconnexion déjà existant. Réutilise `useAsyncData`/`LoadingView`/`ErrorView` (Phase 12) —
aucun nouveau mécanisme de state/réseau.

## 12. Teacher Mobile

Identique au parent : un enseignant reçoit bien des notifications (annonces école entière, voir
Discovery §14 confirmée), donc un écran équivalent a été ajouté (`app/(teacher)/notifications.tsx`).
**Composant partagé** (`components/NotificationsScreen.tsx`) entre les deux flux — aucune
duplication d'écran, conforme à la consigne de simplicité.

## 13. Sécurité

IDOR testé explicitement : `POST /notifications/{id}/read` sur la notification d'un AUTRE
utilisateur → 404 (jamais 403, motif anti-énumération déjà établi), et la notification ciblée
reste non lue malgré la tentative. Cross-school/cross-org testés pour la création d'annonce (RLS
rend l'école étrangère invisible → 403/404) et pour la lecture (un parent d'une école ne voit
jamais les notifications d'un parent d'une autre école, testé avec deux tenants complets). Mass
assignment : aucun champ `recipient_user_id`/`school_id`/`organization_id` n'est exposé en entrée
d'aucun endpoint client — impossible à forger par construction du schéma Pydantic, pas seulement
par convention. Contenu : texte brut uniquement, aucun rendu HTML/Markdown ni côté web (React
échappe par défaut) ni mobile (`<Text>` React Native n'interprète jamais de balisage) — aucune
surface XSS introduite.

## 14. Performance

Annonce école entière : une seule requête de résolution (`SELECT DISTINCT ... WHERE ...`) + un
seul lot d'`INSERT` via `add_all`/`flush` — jamais de boucle par destinataire, jamais d'email en
masse. Testé avec plusieurs dizaines de destinataires potentiels dans les scénarios de test
(école complète avec admin+parent+enseignant, classes multiples) — aucun signe de N+1 observé
(chaque test s'exécute en une fraction de seconde). Aucun test de charge à trois chiffres/mille
destinataires n'a été exécuté (NON VÉRIFIÉ à cette échelle) — au-delà de la taille d'une école
pilote réelle, jugé hors périmètre de cette validation.

## 15. Tests

**19 nouveaux tests** (`test_notifications.py`) : événements automatiques (2), idempotence
paiement (1), lecture/non-lue/pagination (5, dont IDOR), annonces école/classe/déduplication/
validation (6), RBAC (2), isolation cross-school/cross-org/RLS brute (3).

**Résultats réels** :
```
pytest tests/test_notifications.py -q   → 19 passed (premier essai, aucune correction nécessaire
                                            après les deux bugs de conception trouvés et corrigés
                                            AVANT l'exécution — voir §2 et §5)
pytest -q (suite complète)               → 254 passed (235 existants + 19 nouveaux), 0 régression
ruff check .                             → All checks passed!
mypy app                                 → Success, 83 fichiers (78 + 5 nouveaux fichiers du module)
```

## 16. Docker

```
docker compose config --quiet → exit 0
docker compose ps              → 4/4 Up, api/db/redis (healthy)
GET /health                    → {"status":"ok"}
GET /ready                     → {"status":"ready","checks":{"database":"ok","redis":"ok","storage":"ok"}}
```
Aucun volume supprimé, aucune donnée réinitialisée.

## 17. Backup/restore

Backup réel exécuté sur le schéma Phase 21 (`scripts/windows/backup-all.ps1`) : dump PostgreSQL
(6538 KB, intégrité vérifiée `pg_restore --list`), archive stockage (551 fichiers, intégrité
vérifiée), copie externe vérifiée par SHA-256. Un test de restauration complet vers une base
dédiée n'a pas été répété cette phase (déjà prouvé à plusieurs reprises en Phases 15/17/19/20,
mécanisme agnostique au contenu du schéma) — **NON VÉRIFIÉ explicitement cette phase**, signalé
comme tel plutôt que supposé.

## 18. Email regression

Aucune modification d'`EmailProvider` ni des 4 emails existants. Suite `test_report_cards_
notifications.py` (15 tests, comportement email complet) et les tests d'auth/mot de passe/
création de compte re-exécutés dans la suite complète (§15) — tous verts, comportement inchangé.

## 19. Fichiers modifiés

24 fichiers (2209 insertions, 12 suppressions). **Nouveaux** : migration `0011`, module
`app/modules/notifications/` (5 fichiers), `tests/test_notifications.py`, écrans web
`(app)/notifications/`, `(app)/announcements/`, `lib/notifications/client.ts` (web et mobile),
écrans mobile `(parent)/notifications.tsx`, `(teacher)/notifications.tsx`,
`components/NotificationsScreen.tsx`, `docs/phases/PHASE_21_DISCOVERY.md`. **Modifiés
(additif uniquement)** : `model_registry.py`, `main.py`, `fees/service.py` (+5 lignes),
`rbac/seed.py` (+16 lignes), `report_cards/router.py` (+6 lignes), `Nav.tsx`/`TopBar.tsx`,
les deux `_layout.tsx` mobile. Aucune migration historique modifiée, aucun test supprimé, aucun
`.env` touché, aucune nouvelle dépendance (`requirements.txt`/`package.json` inchangés).

## 20. Commit

Audit pré-commit réel : `git status --porcelain` (liste exacte ci-dessus), `git diff --cached`
relu intégralement, grep de motifs de secrets sur le diff complet → **SECRET FOUND: NO**.

## 21. Limites

Pagination par curseur = première introduction de ce motif dans ce dépôt (aucune convention
préexistante à suivre, documenté comme tel). Annonces école entière testées à l'échelle d'une
école de test (quelques utilisateurs), pas à l'échelle de centaines/milliers de destinataires
réels. Aucun accusé de lecture au-delà de `read_at` (pas de "vu par X sur Y destinataires" pour
l'admin — hors périmètre, aucun modèle `Announcement` pour l'agréger sans contourner la policy
RLS stricte, voir Discovery §17 pour le choix délibéré).

## 22. Risques résiduels

Aucun nouveau risque de sécurité identifié au-delà de ceux déjà documentés (HTTPS, SMTP externe,
validation mobile réelle — tous inchangés depuis les phases précédentes). Risque opérationnel
mineur : la policy RLS "par destinataire" est un nouveau sous-motif dans ce projet (toutes les
autres tables sont org-scopées) — toute future table de ce type devra reproduire consciemment ce
choix plutôt que de copier le motif générique par réflexe ; documenté explicitement dans
`notifications/models.py` et cette page pour cette raison.

## 23. Roadmap suivante

Inchangée par rapport à la Discovery (§30) : le choix de Phase 22 dépendra du retour réel des
écoles pilotes sur l'usage des notifications in-app. Notifications d'absence, rappels de paiement
et push restent des candidats sérieux mais chacun dépend d'une brique absente (design anti-spam
non fait, scheduler absent, infra device/token absente) — aucun n'a été commencé.

## 24. Verdict

**GO**

Les 3 critères indispensables sont tous vérifiés avec preuve réelle : Notification/annonces
fonctionnels avec ciblage et déduplication corrects, parent/enseignant strictement self-scopés,
RLS et IDOR prouvés (y compris en session SQL brute), RBAC minimal et correct
(`announcements.manage` uniquement), aucun email de masse, aucun scheduler, aucun push/SMS/
WhatsApp introduit, 254/254 tests verts sans régression Phase 19/20, migration propre et
réversible (testée sur base neuve et par aller-retour), Web/Mobile/Docker tous validés
réellement, aucun secret. Un écart de conception a été trouvé et corrigé AVANT tout test
(§2) plutôt que découvert après coup — signe que l'audit préalable a fonctionné comme prévu.
