# Phase 19 Implementation Report — School Fees & Billing

Toutes les preuves ci-dessous sont issues d'exécutions réelles (Postgres 16, Redis 7, Docker,
pytest, ruff, mypy, `next build`, `tsc`) — aucune n'est déclarée sans avoir été réellement lancée.

## 1. État initial

Phases 0-18 terminées, dépôt Git synchronisé avec `origin/main` (CI GitHub verte sur la dernière
révision, run #25 — vérifié Phase précédente). `docs/phases/PHASE_19_DISCOVERY.md` lu intégralement
avant toute modification. Un audit du code réel (permissions.py, tenancy.py, storage.py, email.py,
config.py, rbac/seed.py, report_cards/*, students/schools/academics/models.py, main.py,
conftest.py, test_tenant_isolation.py, parent/*, web CRUD panel/client, mobile parent screens) a
été effectué avant d'écrire la moindre ligne de code — **aucun écart critique** entre la Discovery
et le code réel n'a été trouvé : tous les mécanismes décrits (RLS, `ensure_permission`,
`StorageProvider`/`EmailProvider`, pipeline PDF `report_cards`, `_get_child_or_404`, conventions de
migration) correspondaient exactement à ce que la Discovery documentait.

## 2. Rappel des décisions produit

Conformément à la validation humaine (§3-§21 de la commande) : 5 entités (pas 7 — pas d'`Invoice`
ni de `Receipt` séparées), méthodes de paiement `CASH/BANK_TRANSFER/CHEQUE/AGENT_DEPOSIT/OTHER`,
`PaymentProvider` avec une seule implémentation `MANUAL` (aucun appel réseau), paiements enregistrés
exclusivement depuis le Web Admin (aucune écriture financière offline/mobile), `ACCOUNTANT` gère
les paiements mais pas la configuration des frais (réservée à `SCHOOL_ADMIN`/`DIRECTOR`), reçu par
email = lien vers l'app mobile authentifiée (pas de pièce jointe, pas de modification
d'`EmailProvider`), pas de rappels d'échéance automatisés cette phase.

## 3. Architecture finale

Nouveau module `apps/api/app/modules/fees/` (models/schemas/service/router), suivant exactement le
gabarit `report_cards`/`grades`/`attendance` (service.py présent car logique non triviale :
génération, soldes, idempotence, verrouillage). Nouvelle abstraction `apps/api/app/core/payment.py`
(`PaymentProvider`/`ManualPaymentProvider`), calquée sur `StorageProvider`/`EmailProvider`. Extension
additive de `app/modules/parent/router.py` (3 nouvelles routes en lecture seule). Extension de
`app/modules/rbac/seed.py` (`PHASE19_PERMISSIONS`/`PHASE19_ROLE_PERMISSIONS`, sans toucher aux
dictionnaires des phases précédentes). Aucune modification du modèle académique, des permissions
existantes, de RLS existante, ni d'aucun test existant.

## 4. Entités créées

5 tables, toutes `school_id`+`organization_id` dénormalisées + RLS FORCE, montants en
`Numeric(12, 2)` (jamais `float` — première introduction de ce motif dans le dépôt, documentée dans
`fees/models.py`) :

- **`FeeCategory`** — catégories de frais définies par l'école.
- **`FeeSchedule`** — barème (montant, portée SCHOOL/CLASS/LEVEL, année académique, échéance,
  optionnel ou non). `currency` copiée de `School.currency` à la création.
- **`StudentFee`** — obligation financière d'un élève (sert à la fois de ligne de dette et de
  mini-facture, pas d'`Invoice` séparée). Statut dérivé `PENDING/PARTIALLY_PAID/PAID/CANCELLED`.
- **`Payment`** — paiement manuel, porte aussi les champs du reçu (`receipt_number`, `pdf_path` —
  pas de `Receipt` séparée), `idempotency_key` unique par école, immutable une fois `COMPLETED`
  (seule une transition vers `CANCELLED` est permise).
- **`PaymentAllocation`** — répartition d'un paiement sur une ou plusieurs `StudentFee`.

## 5. Migration

`apps/api/alembic/versions/0009_fees.py` — additive, ne modifie aucune migration 0001-0008. Suit le
gabarit exact de `0007_attendance.py` (`_org_scoped_columns()`, boucle RLS, seed RBAC via
`op.bulk_insert`/`INSERT ... SELECT ... VALUES`). Contraintes ajoutées : `CHECK amount > 0` sur les
4 colonnes monétaires, `CHECK` de cohérence de portée sur `fee_schedules`, unicité
`(student_id, fee_schedule_id)`, `(school_id, idempotency_key)`, `(school_id, receipt_number)`,
`(payment_id, student_fee_id)`.

**Validation réelle** (pas seulement une relecture) :
```
$ docker compose exec api alembic current   # avant
0008
$ docker compose exec api alembic upgrade head
INFO  Running upgrade 0008 -> 0009, fees (Phase 19 — School Fees & Billing)
$ docker compose exec api alembic current
0009 (head)
$ docker compose exec api alembic heads
0009 (head)
```
**Réversibilité testée réellement** : `alembic downgrade 0008` (succès, `current` → `0008`) puis
`alembic upgrade head` (succès, `current` → `0009 (head)`), suivi d'une ré-exécution de
`tests/test_fees.py` (25/25 passés) pour prouver que l'aller-retour n'a rien corrompu.

**Migration depuis une base neuve** : un Postgres 16 jetable (conteneur + réseau Docker dédiés,
détruits après coup) a reçu la chaîne complète `0001 → 0009` en une seule commande, succès
intégral :
```
Running upgrade  -> 0001, bootstrap check
... (0002 à 0008) ...
Running upgrade 0008 -> 0009, fees (Phase 19 — School Fees & Billing)
```

## 6. API

14 endpoints, tous sous `/api/v1`, suivant les conventions déjà en place (`Query(...)` pour les
listes scopées école, `ensure_permission` après chargement de la ressource, `IntegrityError` →
409, pas de pagination — cohérent avec le reste du dépôt qui n'en a nulle part) :

`POST/GET /fee-categories`, `POST/GET /fee-schedules`, `POST /fee-schedules/{id}/generate`,
`GET /students/{id}/financial-summary`, `PATCH /student-fees/{id}`, `POST /payments`,
`POST /payments/{id}/cancel`, `GET /payments`, `GET /payments/{id}/receipt.pdf`,
`GET /fees/summary`, plus 3 routes parent en lecture seule (§9).

Déviation documentée par rapport aux exemples illustratifs de la commande (`/schools/{id}/fees/...`) :
style query-param (`?school_id=`) choisi pour rester cohérent avec `report_cards`/`students`, les
gabarits les plus directement réutilisés, plutôt que d'introduire un style d'imbrication différent.

## 7. RBAC

Nouvelles permissions `fees.read`, `fees.manage`, `payments.read`, `payments.manage` (convention
`{domaine}.read/manage` respectée). Attribution exactement conforme à la décision produit §9 :
`SCHOOL_ADMIN`/`DIRECTOR` = les 4 ; `ACCOUNTANT` = `fees.read`+`payments.read`+`payments.manage`
(pas `fees.manage`) — premher contenu réel donné à ce rôle jusqu'ici vide (`PHASE_13_DISCOVERY.md`).
`TEACHER`/`STAFF` : rien (aucun besoin exprimé). `PARENT` : accès via le lien Guardian existant,
jamais via RBAC (identique à `report_cards`).

## 8. RLS

5 tables avec `ENABLE`/`FORCE ROW LEVEL SECURITY` + policy `{table}_tenant_isolation`, prédicat
identique (caractère pour caractère) à celui de toutes les tables existantes. Deux tests dédiés
prouvent la garantie **au niveau base**, pas seulement applicatif :
`test_row_level_security_hides_payment_row_even_bypassing_app_check` (session brute +
`apply_tenant_context`, contrôle positif inclus) et les tests cross-organization/cross-school
HTTP (§16).

## 9. Web

3 écrans, conformément à la consigne "pas 10 écrans si 3 suffisent" :
1. `/fees` (`apps/web/app/(app)/fees/page.tsx`) — catégories (`ResourceCrudPanel`) + barèmes
   (formulaire sur-mesure avec portée conditionnelle + bouton "Générer les frais élèves").
2. Fiche élève (`StudentFinancialSummary.tsx`, intégrée à `students/[id]/page.tsx`) — solde,
   liste des frais, formulaire d'enregistrement de paiement, historique avec téléchargement de
   reçu et annulation.
3. `/payments` — ledger école entière filtrable par statut, bandeau d'agrégats
   (`fees/summary`).

Nouveau `apps/web/lib/fees/client.ts` suivant exactement la convention `getJson/postJson/patchJson`
existante. Entrées de navigation ajoutées (`Nav.tsx`), gardées par permission comme les autres.

**Validation réelle** (fichiers copiés dans le conteneur `web` déjà en service, comme en Phase 18) :
```
$ pnpm run lint         → ✔ No ESLint warnings or errors
$ pnpm run type-check   → (aucune erreur)
$ pnpm run build        → ✓ Compiled successfully, 18 routes dont /fees et /payments
```

## 10. Mobile

Un seul ajout : onglet **"Frais"** (4ᵉ onglet) dans l'écran existant
`app/(parent)/children/[studentId].tsx` — lecture seule stricte (solde, liste des frais, historique
des paiements, bouton "Voir le reçu"). Réutilise `useAsyncData`/`ScreenState`
(`LoadingView`/`ErrorView`) et le motif `downloadReportCardPdf`/`Sharing.shareAsync` déjà en place
pour les bulletins, appliqué à l'identique pour les reçus (`childReceipts.openPdf`). Aucun écran de
saisie de paiement, aucune modification du routage des autres rôles.

**Validation réelle** : `tsc --noEmit` via un conteneur `node:20-alpine` temporaire réutilisant
`node_modules` existant — 0 erreur.

## 11. Paiements

Enregistrement transactionnel unique (`fees/service.py::record_payment`) : vérification
idempotence → validation `sum(allocations) == amount` → verrouillage (`SELECT ... FOR UPDATE`) des
`StudentFee` ciblées, triées par id → vérification `déjà_alloué + montant <= amount_due` par frais
→ insertion `Payment`+`PaymentAllocation` → recalcul du statut de chaque frais → génération du reçu
PDF → notification best-effort → commit. Aucune modification en place d'un paiement `COMPLETED` :
seule `POST /payments/{id}/cancel` existe (annulation tracée : `cancelled_at/cancelled_by/
cancellation_reason`, jamais de suppression physique).

## 12. PaymentProvider

`apps/api/app/core/payment.py` — `PaymentProvider(ABC)` / `ManualPaymentProvider` (aucun appel
réseau, aucun secret, aucune dépendance) / `get_payment_provider("manual")` / singleton
`payment_provider`, appelé par `record_payment` avant l'écriture en base. Codé en dur sur `"manual"`
(pas de nouvelle variable d'environnement — une seule option ne justifie pas un réglage
configurable, cf. consigne §28 anti-sur-architecture). Un futur `TMoneyProvider`/`FloozProvider`
s'ajouterait en implémentant la même interface, sans toucher au reste du module `fees`.

## 13. Reçus

PDF généré de façon synchrone à l'enregistrement du paiement, réutilisant `html_to_pdf`
(`report_cards/service.py`, `xhtml2pdf`) — pas de nouveau moteur de rendu : un simple gabarit HTML
échappé (`html.escape`) suffit puisque le contenu n'est jamais fourni par un utilisateur (contexte
interne uniquement, contrairement aux templates `report_cards` qui eux sont school-admin-authored).
Stocké via le singleton `storage` (`receipts/{school_id}/{payment_id}.pdf`), téléchargé via un
endpoint authentifié et scopé (`GET /payments/{id}/receipt.pdf`), jamais une URL publique. Pas de
QR (hors périmètre MVP, voir Discovery §15/§23).

## 14. Emails

`_prepare_payment_notifications`/`send_payment_notifications` (`fees/service.py`) — motif identique
à `report_cards` (lecture des destinataires avant commit, envoi best-effort après). Le corps de
l'email invite à se connecter à l'application mobile (aucun lien cliquable inventé — aucune vue web
parent n'existe, aucun schéma de lien profond mobile n'est établi ; en construire un pour cette
phase aurait été une nouvelle surface non éprouvée). `EmailProvider` non modifié — pas de pièce
jointe, conformément à la décision produit. L'échec d'envoi n'affecte jamais l'enregistrement du
paiement (`send_email_best_effort`, appelé après le commit).

## 15. Tests

**25 nouveaux tests** (`apps/api/tests/test_fees.py`), organisés par catégorie comme demandé :
modèles/frais (catégories, portée, génération idempotente, solde), règles de paiement (montant
exact, dépassement de solde, montant nul/négatif, frais inexistant), idempotence/concurrence
(double soumission avec `asyncio.gather`, sur-allocation concurrente sur le même frais — un seul
des deux paiements réussit), annulation (revert du statut, double-annulation refusée, immutabilité
du montant/méthode), RBAC (TEACHER refusé, ACCOUNTANT partiel), isolation cross-organization (404
RLS) et cross-school-en-lecture, RLS brute (session directe), et 5 tests parent (accès self-scoped,
404 sur enfant d'autrui, reçu d'un autre enfant inaccessible, écriture toujours refusée).

**Résultats réels** :
```
$ pytest tests/test_fees.py -q       → 25 passed in 33.35s
$ pytest -q (suite complète)          → 208 passed in 347.81s   (183 existants + 25 nouveaux)
$ ruff check .                        → All checks passed!
$ mypy app                            → Success: no issues found in 78 source files
```
Aucune régression : les 183 tests antérieurs à cette phase passent toujours.

## 16. Sécurité

IDOR : chaque route re-vérifie la ressource chargée via `ensure_permission(organization_id=,
school_id=)`, jamais un id de requête pris tel quel. Cross-school/cross-org : RLS + vérification
applicative, prouvé par test HTTP (`test_admin_a_cannot_record_payment_for_student_of_
organization_b` → 404, RLS rend l'élève invisible) et par un test RLS brut. Montants : `Numeric`
uniquement, jamais accepté depuis le client pour un solde/total (toujours recalculé serveur).
Paiement existant : aucun endpoint PATCH sur `amount`/`method`/`paid_at` — immutabilité par absence
de surface API, testée explicitement (`test_payment_amount_and_method_are_not_editable`). Parent :
`_get_child_or_404` réutilisé à l'identique (404, jamais 403, anti-énumération), testé pour les
frais ET pour le téléchargement de reçu d'un autre enfant.

## 17. Concurrence

Deux scénarios testés avec de véritables requêtes concurrentes (`asyncio.gather`, pas une
simulation séquentielle) :
- `test_concurrent_double_submission_creates_only_one_payment` — même `idempotency_key` : une
  seule ligne créée, les deux réponses HTTP renvoient le même paiement.
- `test_concurrent_payments_on_same_fee_never_overallocate` — deux paiements différents tentant
  chacun 30000 sur un solde de 50000 : exactement un 201 et un 422, jamais les deux 201 (ce qui
  aurait produit un solde négatif). Le verrouillage `SELECT ... FOR UPDATE` (trié par id pour
  éviter tout deadlock) sur les `StudentFee` ciblées est la garantie réelle testée ici, pas une
  affirmation théorique.

## 18. Docker

```
$ docker compose build api   → succès (2 fois, avant et après ajout de test_fees.py)
$ docker compose build web   → (fichiers copiés + build direct, voir §9)
$ docker compose config --quiet → exit 0
$ docker compose ps          → 4/4 services Up, api/db/redis (healthy)
$ GET /health  → {"status":"ok"}
$ GET /ready   → {"status":"ready","checks":{"database":"ok","redis":"ok","storage":"ok"}}
```
Aucun volume supprimé, aucune donnée de production touchée (base de développement locale
uniquement, déjà utilisée pour l'ensemble des tests des phases précédentes).

## 19. Limites

- Aucune intégration Mobile Money réelle (volontaire) — `PaymentProvider` prêt, une seule
  implémentation `MANUAL`.
- Email de reçu : lien vers l'app mobile, pas de lien direct cliquable vers le reçu (aucune vue web
  parent n'existe pour héberger un tel lien) ni de pièce jointe.
- Pas de garde-fou trop-perçu/crédit : un paiement doit s'allouer exactement à son montant (décision
  MVP la plus sûre, documentée dans la Discovery §15).
- Génération des `StudentFee` par action explicite uniquement — aucune automatisation à
  l'inscription/désinscription.
- `receipt_number` dérivé de l'UUID du paiement (`RCPT-{8 premiers hex}`), pas un compteur
  séquentiel humainement lisible par école — choix délibéré pour éviter toute condition de course
  sur un compteur partagé.

## 20. Éléments reportés

Rappels d'échéance automatisés (nécessite un ordonnanceur applicatif non prouvé dans ce dépôt),
saisie de paiement depuis mobile, document "facture" formel regroupant plusieurs frais, reçu avec
QR de vérification, remises/exonérations en entité dédiée, échéanciers automatisés, BI avancée au
delà des 4 agrégats du MVP (`fees/summary`) — tous explicitement actés comme hors périmètre dans
`PHASE_19_DISCOVERY.md` §31 et non traités ici.

## 21. Fichiers modifiés

21 fichiers (3641 insertions, 2 suppressions) :

**Nouveaux** : `apps/api/alembic/versions/0009_fees.py`, `apps/api/app/core/payment.py`,
`apps/api/app/modules/fees/{__init__,models,schemas,service,router}.py`,
`apps/api/tests/test_fees.py`, `apps/web/lib/fees/client.ts`,
`apps/web/app/(app)/fees/page.tsx`, `apps/web/app/(app)/payments/page.tsx`,
`apps/web/app/(app)/students/[id]/StudentFinancialSummary.tsx`, `docs/phases/PHASE_19_DISCOVERY.md`,
`docs/phases/PHASE_19_IMPLEMENTATION.md` (ce fichier).

**Modifiés (additif uniquement)** : `apps/api/app/db/model_registry.py`, `apps/api/app/main.py`,
`apps/api/app/modules/parent/router.py`, `apps/api/app/modules/rbac/seed.py`,
`apps/mobile/app/(parent)/children/[studentId].tsx`, `apps/mobile/lib/parent/client.ts`,
`apps/web/app/(app)/students/[id]/page.tsx`, `apps/web/components/app-shell/Nav.tsx`.

Aucune migration historique modifiée, aucun test supprimé, aucun fichier `.env` touché, aucune
nouvelle dépendance (`requirements.txt`/`requirements-dev.txt`/`package.json` inchangés).

## 22. Commit

Audit pré-commit réel : `git status --porcelain` (liste exacte ci-dessus), `git diff --cached`
relu, grep de motifs de secrets sur le diff complet (`password=`, `secret=`, `api[_-]?key`, clés
privées, préfixes de clés connus) → **SECRET FOUND: NO** (seules les valeurs de test connues
`SuperSecret123`/`OtherPass123`/`ParentPass123`, déjà utilisées dans tout le dépôt, apparaissent).

Commit créé (un seul, après validation complète) :
```
feat: implement school fees and billing (Phase 19)
```
Aucun `git push` — le dépôt reste synchronisé avec `origin/main` uniquement jusqu'au commit
précédent ; ce commit local attend une validation/push ultérieurs explicites.

## 23. Verdict final

**GO**

Tous les critères de la section 35 de la commande sont satisfaits avec preuve réelle : modèle
financier cohérent (5 entités, montants `Numeric`), migration propre et réversible (testée sur base
neuve et par aller-retour), RLS correcte (policy identique au reste du dépôt + test brut dédié),
RBAC correcte (permissions minimales, `ACCOUNTANT` enfin doté), paiements fiables et concurrence
réellement testée (`asyncio.gather`, jamais de sur-allocation), parent strictement self-scoped
(404 anti-énumération), reçus protégés (endpoint authentifié, jamais de lien public), aucun Mobile
Money fictif (une seule implémentation `MANUAL`, documentée comme telle), tests backend/web/mobile
tous verts (208 pytest, ruff, mypy, lint/type-check/build web, tsc mobile), Docker sain (4/4
healthy, `/health` et `/ready` réels), Alembic à jour (`current == heads == 0009`), aucune
régression, aucun secret, documentation à jour (cette page + `PHASE_19_DISCOVERY.md`).
