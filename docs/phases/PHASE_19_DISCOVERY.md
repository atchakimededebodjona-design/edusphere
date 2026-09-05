# Phase 19 Discovery — School Fees & Billing

Discovery uniquement. Aucun code applicatif, aucune migration, aucune dépendance, aucun commit,
aucun push n'ont été produits pendant cette phase. Seul ce document a été créé. Toute affirmation
ci-dessous distingue explicitement **PROUVÉ (lecture réelle du code)** de **PROPOSÉ (à valider avant
implémentation)**.

## 1. Executive Summary

Aucune brique financière n'existe dans EduSphere aujourd'hui — confirmé par une recherche exhaustive
(`fee|invoice|payment|billing|receipt|balance|solde|montant|paiement|facture`, insensible à la casse)
sur `apps/api`, `apps/web`, `apps/mobile` : **zéro résultat**. Ce constat n'est pas nouveau : six
Discovery précédentes (Phases 8 à 15) l'ont déjà fait et ont, à chaque fois, indépendamment conclu la
même chose : construire d'abord un module financier **interne** (frais, factures, soldes), **sans**
intégration Mobile Money, et attendre que l'infrastructure (stockage durable, email réel, sécurité
upload) soit solide avant de toucher à des données financières. Ces trois blocages cités (Phases 13,
14, 15) sont désormais résolus (stockage — Phase 14 ; sauvegarde/restauration — Phases 15/17 ; email
SMTP réel — Phase 16 ; sécurité upload — Phase 13). `README.md:129-133` cite explicitement
"paiements" comme exemple de prochaine étape métier.

**Conclusion de cette Discovery : School Fees & Billing est confirmé comme le candidat le plus
prioritaire** (voir scoring §11), et est réalisable en réutilisant presque exclusivement des
conventions déjà éprouvées dans le dépôt (RLS, RBAC, `StorageProvider`/`EmailProvider`, le module
`report_cards` comme gabarit direct pour la génération de documents PDF). Le modèle de données
minimal proposé compte **5 tables**, pas les 7 hypothétiques citées dans la commande de Phase 19 —
`Invoice` et `Receipt` sont volontairement absorbées dans `StudentFee` et `Payment` (voir §14).

**Verdict : GO WITH NOTES** (voir §33/34 — plusieurs points nécessitent une décision humaine avant de
lancer l'implémentation, mais aucun n'est bloquant).

## 2. État réel du dépôt

- Dépôt Git : branche `main`, synchronisée avec `origin/main` (`46e9cf5`), CI GitHub la plus récente
  sur ce commit : **success** (run #25).
- 11 modules sous `apps/api/app/modules/` : `academics, attendance, auth, grades, organizations,
  parent, rbac, report_cards, schools, students, users`. `service.py` existe uniquement là où la
  logique dépasse le CRUD trivial (attendance, grades, report_cards, students, users, auth) ;
  `academics`/`organizations` gardent leur logique directement dans `router.py`.
- Suite de tests : 183 tests, dernière exécution réelle connue (Phase 18) : **183 passed**.
- Aucune table, aucun modèle SQLAlchemy, aucune route, aucune permission RBAC, aucune référence UI
  (web ou mobile) liée aux frais/paiements n'existe.

## 3. Fonctionnalités financières existantes

**NOT FOUND** — confirmé par grep exhaustif sur `apps/api`, `apps/web`, `apps/mobile`, migrations et
tests. Les seules occurrences des mots-clés recherchés dans le dépôt sont :
- des mentions purement documentaires de l'**absence** de la fonctionnalité dans des rapports de
  Discovery précédents (voir §13 pour les citations),
- une correspondance fortuite dans `pnpm-lock.yaml` (nom de paquet, sans rapport),
- des correspondances sur le mot "Scheduled" (Windows Task Scheduler, sans rapport avec la
  planification financière).

`docs/phases/PHASE_9_DISCOVERY.md:35` : *"aucune trace de `fee`/`invoice`/`payment`/`receipt` dans
`apps/api/app`, et toujours aucune trace de..."* — confirmé toujours vrai aujourd'hui.

## 4. Audit des modèles existants

| Module | models.py | router.py | schemas.py | service.py |
|---|---|---|---|---|
| academics | ✅ | ✅ | ✅ | ❌ (logique inline) |
| attendance | ✅ | ✅ | ✅ | ✅ |
| auth | ✅ | ✅ | ✅ | ✅ |
| grades | ✅ | ✅ | ✅ | ✅ |
| organizations | ✅ | ✅ | ✅ | ❌ (logique inline) |
| parent | ❌ (réutilise Student/Guardian) | ✅ | ✅ | ✅ |
| rbac | ✅ | ✅ | ✅ | `seed.py` |
| report_cards | ✅ | ✅ | ✅ | ✅ |
| schools | ✅ | ✅ | ✅ | ✅ |
| students | ✅ | ✅ | ✅ | ✅ |
| users | ✅ | ✅ | ✅ | ✅ |

**Convention de colonnes tenant confirmée** : chaque table métier (academics, students, grades,
attendance, report_cards) porte **à la fois** `school_id` et `organization_id` en FK non-nullables,
dénormalisées (justifié explicitement dans le code : éviter une sous-requête via `schools` dans
chaque policy RLS). Exceptions confirmées : `organizations` (racine tenant, aucune des deux
colonnes), `schools` (seulement `organization_id`), `users`/`user_sessions`/
`password_reset_tokens` (identité globale, aucune colonne tenant).

**`Student`** (`apps/api/app/modules/students/models.py:14-37`) : `id, school_id, organization_id,
matricule, first_name, last_name, date_of_birth, sex, place_of_birth, address, status, photo_path,
created_at, updated_at` — unique `(school_id, matricule)`. **Pas de `class_id` direct** : le lien
classe/niveau passe par `StudentEnrollment` (`student_id, class_id, academic_year_id,
enrollment_date, status`) — c'est ce point de jointure qui doit être utilisé pour tout barème de
frais dépendant de la classe/niveau, jamais `Student` directement.

**`School`** (`apps/api/app/modules/schools/models.py:12-33`) : `id, organization_id, name, slug,
address, phone, email, timezone (default "Africa/Lome"), currency (String(3), default "XOF"),
logo_path, created_at, updated_at`. **`currency` et `timezone` existent déjà** au niveau École et
Organisation (confirmé aussi dans `organizations/models.py:23`) — un montant de frais peut être
libellé dans la devise de l'école sans ajouter aucune configuration nouvelle.

## 5. Audit API

Mécanisme de permission (`apps/api/app/core/permissions.py`) — **pas un décorateur** : une fonction
`await ensure_permission(db, current_user, "<code>", organization_id=..., school_id=...)` appelée
explicitement dans chaque handler après chargement de la ressource cible. `require_permission(code)`
existe en variante `Depends(...)` pour les routes sans ressource précise à charger (ex. liste
d'organisations). `CurrentUser`/`DbSession` sont les deux annotations `Depends` utilisées dans
quasiment toutes les signatures de routes.

Chaque module expose des routes REST classiques (`GET/POST/PATCH`, parfois `DELETE`), scopées par
école/organisation, avec des sous-ressources imbriquées pour les relations (ex.
`/classes/{id}/subjects`, `/classes/{id}/teachers`). Ce même schéma s'applique directement aux
endpoints de frais proposés (§17).

## 6. Audit RBAC

Source de vérité unique : `apps/api/app/modules/rbac/seed.py`. Son en-tête anticipe explicitement ce
travail : *"Les modules futurs (élèves, académique, finance...) ajouteront leurs propres permissions
et enrichiront ce mapping via de nouvelles migrations, sans modifier celle-ci."*

**Rôles existants** : `SUPER_ADMIN, PLATFORM_SUPPORT, PARTNER_ADMIN, SCHOOL_ADMIN, DIRECTOR,
ACCOUNTANT, TEACHER, STAFF, PARENT, STUDENT`. **`ACCOUNTANT` existe déjà comme rôle mais n'a
actuellement que `schools.read`** (confirmé aussi par `docs/phases/PHASE_13_DISCOVERY.md:250` :
*"le rôle `ACCOUNTANT` reste vide de permissions"*) — un point d'ancrage tout trouvé pour les
permissions financières.

**Permissions existantes** (aucune ne concerne la finance) :
```
organizations.read/manage, schools.read/manage, users.read/manage, roles.read,
academics.read/manage, students.read/manage, grades.read/manage,
report_cards.read/manage, attendance.read/manage
```

## 7. Audit tenant/RLS

`apps/api/app/core/tenancy.py` fixe trois variables de session Postgres à chaque requête
authentifiée (`app.current_user_id`, `app.is_platform_wide`, `app.tenant_org_ids`), via
`SELECT set_config(:name, :value, true)` (portée transaction). Chaque migration introduisant une
table tenant-scopée répète le même motif (`0003`, `0004`, `0005`, `0006`, `0007`) :

```python
op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
op.execute(f"""
    CREATE POLICY {table}_tenant_isolation ON {table}
    USING (
        current_setting('app.is_platform_wide', true) = 'true'
        OR (
            COALESCE(current_setting('app.tenant_org_ids', true), '') <> ''
            AND organization_id = ANY(
                string_to_array(current_setting('app.tenant_org_ids', true), ',')::uuid[]
            )
        )
    )
""")
```

`FORCE ROW LEVEL SECURITY` est essentiel : la connexion applicative passe par le rôle Postgres
non-superutilisateur `edusphere_app` (créé en `0002`) — un superutilisateur contournerait toujours
RLS. **Exception notable, déjà connue et documentée dans les phases précédentes** : `organizations`
n'a aucune policy RLS (protection uniquement applicative via `ensure_permission`) — gap MEDIUM
préexistant, sans rapport avec cette phase.

**Recette confirmée pour une nouvelle table financière** : ajouter `school_id`+`organization_id`
(FK non-nullables, dénormalisées), lister la table dans un `TABLES_WITH_RLS` local à la migration,
répéter la boucle `ENABLE`/`FORCE`/`CREATE POLICY` ci-dessus, ajouter le `DROP POLICY IF EXISTS`
correspondant dans `downgrade()`, et ajouter les nouveaux codes de permission via un nouveau couple
`PHASE_N_PERMISSIONS`/`PHASE_N_ROLE_PERMISSIONS` dans `rbac/seed.py` — **sans jamais modifier les
dictionnaires des phases précédentes**. Note d'audit : `_org_scoped_columns()` (le helper qui
génère les deux colonnes FK) n'est **pas** partagé entre migrations — chaque fichier le redéfinit
localement ; une nouvelle migration de frais suivra la même convention (pas de refactor du partagé
introduit ici, ce serait hors périmètre).

## 8. Audit web

`apps/web/components/crud/ResourceCrudPanel.tsx` : composant CRUD générique (liste + édition en
ligne + création), piloté par un `fields: FieldSpec<T>[]` déclaratif et un flag `canManage`. Utilisé
pour les données de référence simples (ex. académique). Les écrans plus complexes (ex.
`students/page.tsx`) préfèrent une page sur-mesure plutôt que de forcer ce composant générique.

`apps/web/lib/<domaine>/client.ts` : chaque domaine expose un objet nommé avec des méthodes
`.list()/.get()/.create()/.update()` (et `.upload()/.download()` pour les ressources à fichiers),
construites sur `getJson<T>/postJson<T>/patchJson<T>/getBlobUrl` partagés
(`apps/web/lib/api/client.ts`). Modules existants : `academics, grades, report-cards, students,
users, attendance, auth, schools`.

## 9. Audit mobile

`apps/mobile/components/ScreenState.tsx` (`LoadingView`, `ErrorView`) + `apps/mobile/lib/api/
useAsyncData.ts` (état `loading|error|success` + `retry()`) forment le seul mécanisme d'état d'écran
du projet, réutilisé de façon uniforme sur au moins 3 écrans lus intégralement.

**Module parent** (`apps/api/app/modules/parent/`) : pas de `models.py` — accès contrôlé uniquement
par le lien `Guardian.user_id` (`service.get_child`), jamais par RBAC (`PARENT` n'a aucune
permission). Toute discordance élève/parent renvoie **404, jamais 403** (anti-énumération
explicite : *"un parent ne doit jamais pouvoir distinguer 'cet élève n'existe pas' de 'cet élève
n'est pas le mien'"*). Endpoints existants : enfants, résumé de présence, notes, bulletins publiés
(jamais les brouillons), téléchargement PDF de bulletin.

Côté mobile, `app/(parent)/index.tsx` liste les enfants (sélecteur = simple liste + navigation par
URL, pas d'état global "enfant actif"), `children/[studentId].tsx` est un écran à onglets
(Présence/Notes/Bulletins) lisant `studentId` en paramètre d'URL. Un onglet "Frais" s'insère
naturellement comme 4ᵉ onglet dans cet écran existant.

## 10. Candidats de phase

- **A. School Fees & Billing** — proposé par la commande, confirmé prioritaire par 6 Discovery
  antérieures et le README.
- **B. Communications école → parents** — jamais mentionné comme prioritaire dans les Discovery
  précédentes ; `EmailProvider` déjà prêt mais aucune demande métier documentée.
- **C. Admissions / inscriptions** — explicitement écarté à basse priorité dans
  `PHASE_8_DISCOVERY.md` et `PHASE_9_DISCOVERY.md`.
- **D. Emploi du temps** — évalué et reporté à plusieurs reprises (`PHASE_10_DISCOVERY.md:212-214`,
  `PHASE_11_DISCOVERY.md:69`), complexité de contraintes non négligeable.
- **E. Autre découverte** — deux dettes MEDIUM connues (rate limiting incomplet sur
  register/refresh/verify-by-code, absence de garde-fou sur correction de notes après publication,
  voir `PILOT_READINESS.md`) : ce sont des tâches de durcissement, pas de nouveaux domaines métier —
  non comparables sur la même échelle, mentionnées ici pour mémoire mais non scorées en §11.

## 11. Scoring

Échelle 1 (faible) à 5 (fort) par critère.

| Critère | A. Fees & Billing | B. Communications | C. Admissions | D. Emploi du temps |
|---|---|---|---|---|
| Valeur pilote | 5 | 4 | 3 | 3 |
| Impact commercial | 5 | 3 | 2 | 2 |
| Urgence (historique projet) | 5 | 2 | 1 | 1 |
| Faibles dépendances | 4 | 4 | 3 | 3 |
| Faible complexité | 3 | 4 | 3 | 2 |
| Faible risque technique | 3 | 4 | 4 | 4 |
| Réutilisation de l'existant | 5 | 4 | 3 | 3 |
| Impact parent mobile | 5 | 3 | 2 | 2 |
| Impact futur Mobile Money | 5 | 1 | 1 | 1 |
| **Total /45** | **40** | **29** | **22** | **21** |

**A domine nettement** sur les axes qui comptent le plus pour un pilote (urgence, impact commercial,
impact parent, enabler Mobile Money futur) malgré une complexité et un risque technique légèrement
supérieurs — justifiés et maîtrisables (voir §19/§20).

## 12. Recommandation

**School Fees & Billing retenu pour la Phase 19**, avec le périmètre volontairement réduit détaillé
ci-dessous (5 entités, paiement manuel uniquement, enregistrement via le web admin uniquement,
aucune intégration Mobile Money réelle).

## 13. Objectifs Phase 19

- Permettre à un administrateur/comptable d'école de définir des catégories et barèmes de frais, de
  les affecter aux élèves (par école, classe ou niveau), d'enregistrer des paiements manuels
  (espèces, virement, autre), de suivre les soldes, et de générer des reçus PDF.
- Permettre au parent de consulter (lecture seule) le total dû, le total payé, le solde, l'historique
  des paiements et les reçus de son enfant.
- Construire une abstraction `PaymentProvider` (sur le modèle de `StorageProvider`/`EmailProvider`)
  avec une seule implémentation `ManualPaymentProvider`, pour qu'un futur fournisseur (TMoney, Flooz)
  puisse être branché sans toucher au cœur financier — **sans l'implémenter réellement**.
- Explicitement exclu : Mobile Money réel, paiement en ligne, webhook fournisseur, comptabilité
  générale, paie.

## 14. Modèle métier proposé

La commande de Phase 19 propose comme hypothèse 7 entités (`FeeCategory, FeeStructure, StudentFee,
Invoice, Payment, PaymentAllocation, Receipt`). Après analyse, **2 sont retranchées** :

- **Pas d'`Invoice` séparée** : à ce stade MVP, une facture groupant plusieurs frais en un document
  n'apporte rien qu'une simple liste de `StudentFee` (chacune avec son propre `due_date` et statut)
  n'offre déjà à l'écran "situation financière de l'élève". Ajouter une entité de regroupement
  maintenant, sans besoin réel identifié, irait à l'encontre de la consigne anti-sur-ingénierie.
  `StudentFee` fait donc à la fois office de ligne de dette et de mini-facture.
- **Pas de `Receipt` séparée** : un reçu est toujours 1:1 avec un `Payment` complété, jamais
  brouillon, jamais réémis indépendamment — contrairement à `ReportCard` qui a un vrai cycle
  brouillon/publié. Les champs de reçu (`receipt_number`, `pdf_path`) sont donc portés directement
  par `Payment`, évitant une jointure systématique pour l'accès le plus fréquent ("le reçu de ce
  paiement").

**Modèle retenu (5 tables)** : `FeeCategory`, `FeeSchedule` (renommage de "FeeStructure", plus
parlant), `StudentFee`, `Payment` (porte les champs de reçu), `PaymentAllocation`.

## 15. Règles métier

**Frais** : un `FeeSchedule` définit un montant pour une portée (toute l'école, une classe, ou un
niveau) et une période (année académique). L'affectation aux élèves se fait par une action explicite
("générer les frais pour la portée X, période Y"), jamais automatiquement à l'inscription — pour
éviter un effet de bord silencieux en cours d'année. `is_optional` distingue une affectation en
masse (frais obligatoire) d'une sélection élève par élève (frais optionnel, ex. cantine à la carte).
Pas de remises/exonérations en entité séparée au MVP (non demandées explicitement) : un ajustement
ponctuel du `amount_due` d'une `StudentFee` couvre le cas rare, avec une note obligatoire. Pas
d'échéancier automatique : un besoin de "3 tranches" se modélise par 3 `FeeSchedule` distincts
("Tranche 1/2/3"), réutilisant le modèle existant plutôt que d'ajouter une machinerie d'échéancier.

**Facturation** : pas de document "facture" formel au MVP (voir §14) — `StudentFee` porte
`amount_due`, `due_date`, et un statut dérivé (`PENDING/PARTIALLY_PAID/PAID/CANCELLED`) calculé à
partir des `PaymentAllocation` qui la référencent.

**Paiements** : méthodes au MVP : `CASH, BANK_TRANSFER, OTHER` (pas de valeur "MOBILE_MONEY" tant
qu'aucun fournisseur n'est réellement branché — l'ajouter maintenant laisserait croire à tort que
c'est disponible). Champs obligatoires : `amount > 0` (contrainte DB), `method`, `paid_at`,
`recorded_by` (utilisateur qui saisit), `status` (`COMPLETED` par défaut, `CANCELLED` pour
correction), `reference` libre optionnelle. **Idempotence** : un `idempotency_key` fourni par le
formulaire client, unique par `(school_id, idempotency_key)` — un double clic renvoie
l'enregistrement existant au lieu d'en créer un second (motif nouveau dans ce dépôt, aucun précédent
d'idempotency-key trouvé ailleurs — signalé comme tel plutôt que présenté comme une convention
déjà établie). **Correction** : un paiement `COMPLETED` n'est **jamais** modifié en place (montant,
méthode, date) — seule une annulation est permise (`CANCELLED`, `cancelled_at`, `cancelled_by`,
motif obligatoire), qui neutralise ses allocations sans les supprimer ; toute correction réelle
passe par un nouveau paiement. La somme des `PaymentAllocation` d'un paiement ne peut excéder son
`amount` ; la somme des allocations sur une `StudentFee` ne peut excéder son `amount_due` — un
dépassement est rejeté avec une erreur de validation claire, pas plafonné silencieusement ni
transformé en crédit (le crédit/trop-perçu est explicitement hors périmètre).

**Reçus** : numéro, date, élève, payeur (texte libre — le payeur n'est pas toujours le tuteur
enregistré), montant, méthode, référence, école, solde restant au moment du paiement. **Pas de QR de
vérification au MVP** (le mécanisme de `report_cards` existe et est réutilisable plus tard si un vrai
besoin de vérification tiers apparaît — un enjeu moindre pour un reçu que pour un bulletin
contesté). Génération synchrone à l'enregistrement du paiement (pas de cycle brouillon/publication,
contrairement aux bulletins), en réutilisant `xhtml2pdf` + le sandbox Jinja2 déjà en place, et le
singleton `storage` (`receipts/{school_id}/{payment_id}.pdf`).

## 16. Modèle de données

Toutes les tables portent `school_id`+`organization_id` (FK non-nullables, dénormalisées, RLS FORCE)
selon la convention confirmée en §7, ainsi que `created_at`/`updated_at`. Suppression : **aucune
suppression physique** sur `Payment`/`PaymentAllocation` (annulation uniquement, historique
financier) ; `FeeCategory`/`FeeSchedule`/`StudentFee` suppressibles uniquement si aucun paiement n'y
est rattaché (contrainte applicative, pas de `ON DELETE CASCADE` sur ces liens).

- **`FeeCategory`** — `id, school_id, organization_id, name, created_at, updated_at`. Unique
  `(school_id, name)`. Suppression autorisée si aucun `FeeSchedule` associé.
- **`FeeSchedule`** — `id, school_id, organization_id, fee_category_id (FK), academic_year_id (FK),
  name, amount (Numeric(12,2)), currency (String(3), hérite de `School.currency` à la création),
  scope_type (enum: SCHOOL/CLASS/LEVEL), scope_class_id (FK nullable), scope_education_level_id (FK
  nullable), is_optional (bool), due_date (Date, nullable — échéance par défaut des `StudentFee`
  générées). Contrainte : `scope_class_id`/`scope_education_level_id` cohérents avec `scope_type`
  (un seul rempli selon le cas, `CHECK` applicatif). Index sur `(school_id, academic_year_id)`.
- **`StudentFee`** — `id, school_id, organization_id, student_id (FK), fee_schedule_id (FK),
  amount_due (Numeric(12,2)), due_date (Date, nullable), status (PENDING/PARTIALLY_PAID/PAID/
  CANCELLED, dérivé mais persisté pour requêtage), note (Text, nullable — justification d'un
  ajustement manuel), created_at, updated_at. Unique `(student_id, fee_schedule_id)` (une seule
  ligne de dette par élève et par barème — un ajustement se fait sur `amount_due`, pas par
  duplication).
- **`Payment`** — `id, school_id, organization_id, student_id (FK), idempotency_key (String,
  unique par `(school_id, idempotency_key)`), amount (Numeric(12,2)), method (CASH/BANK_TRANSFER/
  OTHER), paid_at (Date), reference (String, nullable), recorded_by (FK users), status (COMPLETED/
  CANCELLED), cancelled_at/cancelled_by/cancellation_reason (nullable), receipt_number (String,
  unique par école, séquentiel), pdf_path (String, nullable jusqu'à génération). Immutable une fois
  `COMPLETED` sauf transition vers `CANCELLED`.
- **`PaymentAllocation`** — `id, school_id, organization_id, payment_id (FK), student_fee_id (FK),
  amount (Numeric(12,2))`. Unique `(payment_id, student_fee_id)` (une seule ligne d'allocation par
  paire). Contrainte applicative : somme des allocations ≤ `payment.amount` et ≤
  `student_fee.amount_due`.

## 17. API proposée

Toutes les routes suivent le motif `ensure_permission(db, current_user, "<code>",
organization_id=..., school_id=...)` déjà utilisé partout ailleurs.

| Méthode | Route | Permission | Comportement |
|---|---|---|---|
| GET | `/schools/{school_id}/fee-categories` | `fees.read` | Liste |
| POST | `/schools/{school_id}/fee-categories` | `fees.manage` | Création |
| GET | `/schools/{school_id}/fee-schedules` | `fees.read` | Liste, filtrable par année/portée |
| POST | `/schools/{school_id}/fee-schedules` | `fees.manage` | Création |
| POST | `/schools/{school_id}/fee-schedules/{id}/generate` | `fees.manage` | Génère les `StudentFee` pour la portée |
| GET | `/students/{student_id}/financial-summary` | `fees.read` | Total dû/payé/solde + liste des `StudentFee` |
| PATCH | `/student-fees/{id}` | `fees.manage` | Ajustement `amount_due`/`note` uniquement |
| POST | `/payments` | `payments.manage` | Enregistre un paiement (idempotent via `idempotency_key`) + allocations |
| POST | `/payments/{id}/cancel` | `payments.manage` | Annulation (motif requis) |
| GET | `/schools/{school_id}/payments` | `payments.read` | Ledger, filtrable |
| GET | `/payments/{id}/receipt.pdf` | `payments.read` | Téléchargement du reçu |
| GET | `/schools/{school_id}/fees/summary` | `fees.read` | Analytics agrégées (§27) |
| GET | `/parent/children/{id}/fees` | (lien Guardian, pas RBAC) | Solde + échéances (lecture seule) |
| GET | `/parent/children/{id}/payments/{payment_id}/receipt.pdf` | (lien Guardian) | Reçu, re-vérifié `payment.student_id == student.id` |

## 18. RBAC proposé

Nouvelles permissions (convention `{domaine}.read`/`{domaine}.manage`, ajoutées via un nouveau
couple `PHASE19_PERMISSIONS`/`PHASE19_ROLE_PERMISSIONS`, sans toucher aux dictionnaires existants) :
`fees.read, fees.manage, payments.read, payments.manage`.

| Rôle | fees.read | fees.manage | payments.read | payments.manage |
|---|---|---|---|---|
| SCHOOL_ADMIN | ✅ | ✅ | ✅ | ✅ |
| DIRECTOR | ✅ | ✅ | ✅ | ✅ |
| ACCOUNTANT | ✅ | ❌ | ✅ | ✅ |
| TEACHER / STAFF | ❌ | ❌ | ❌ | ❌ |
| PARENT | via lien Guardian, pas RBAC | — | — | — |

`ACCOUNTANT` obtient enfin des permissions réelles : lecture des barèmes + gestion des paiements,
mais **pas** la configuration des barèmes (décision de configuration réservée à
SCHOOL_ADMIN/DIRECTOR — point à confirmer, voir §34).

## 19. Sécurité

- **IDOR** : chaque route re-valide que la ressource ciblée appartient bien à l'école/organisation
  résolue via `ensure_permission`, jamais un `school_id`/`payment_id` de requête pris tel quel
  (identique au motif déjà utilisé partout).
- **Cross-school/cross-org** : RLS (§7) + vérification applicative, testé selon le motif de
  `test_tenant_isolation.py` (voir §28).
- **Manipulation des montants** : tous les montants en `Numeric`, jamais `float` (aucune colonne
  monétaire n'existe encore dans le dépôt — première introduction de ce motif, signalé
  explicitement). Aucun total ni solde n'est accepté depuis le client — toujours recalculé côté
  serveur.
- **Modification d'un paiement existant** : bloquée au niveau service dès `status=COMPLETED` ; aucun
  endpoint PATCH n'existe sur `amount`/`method`/`paid_at` (immutabilité par absence de surface API,
  pas seulement par contrôle runtime).
- **Falsification d'une référence** : `reference` est une métadonnée saisie par le personnel, non
  vérifiée contre une banque — limite acceptée et documentée (système manuel/cash par nature),
  jusqu'à une vraie intégration de fournisseur de paiement.
- **Accès parent à un autre enfant / téléchargement de reçu d'un autre élève** : réutilisation
  exacte du motif `_get_child_or_404` (404, jamais 403) et de la re-vérification
  `payment.student_id == student.id` avant tout streaming de PDF, comme pour les bulletins.
- **Énumération** : clés primaires UUID (convention déjà uniforme du projet) ; `receipt_number`
  n'est jamais utilisé comme clé de recherche, uniquement affiché.

## 20. Idempotence et concurrence

- Double-clic/double-soumission : `idempotency_key` unique par `(school_id, idempotency_key)` —
  une resoumission renvoie l'enregistrement existant.
- Deux comptables simultanés : contrainte unique DB + transaction async standard (déjà le motif
  `db: AsyncSession` du projet) empêchent une double insertion sur la même clé.
- Même référence bancaire réutilisée : `reference` n'est **pas** unique (des paiements cash peuvent
  légitimement partager une référence vide/identique) — seule `idempotency_key` l'est.
- Paiement partiellement affecté : état normal, pas de traitement spécial.
- Montant dépassant le solde : rejeté à l'affectation (§15), jamais plafonné ni transformé en
  crédit.

## 21. Parent mobile

Lecture seule uniquement — aucune saisie de paiement côté parent (conforme à la contrainte de la
commande). S'insère comme 4ᵉ onglet ("Frais") dans l'écran existant
`apps/mobile/app/(parent)/children/[studentId].tsx`, avec un nouveau client
`apps/mobile/lib/parent/fees.ts` suivant le motif `getJson<T>` existant, et le motif
`useAsyncData`+`ScreenState` (Loading/Error). Contenu : total dû, total payé, solde, échéances,
historique des paiements, reçus téléchargeables (réutilisant le motif `downloadReportCardPdf` déjà
implémenté pour les bulletins). Un état "vide" (aucun frais encore configuré) est un ajout net —
aucun écran existant n'en avait explicitement besoin jusqu'ici, signalé comme petite nouveauté à
faible risque.

## 22. Web admin

3 écrans, pas plus :

1. **Configuration des frais** (`/fees`) — catégories + barèmes, via `ResourceCrudPanel` (motif
   directement applicable, comme pour les données de référence académiques).
2. **Situation financière d'un élève** — extension de `students/[id]/page.tsx` avec un nouvel
   onglet/panneau (liste des `StudentFee`, solde, formulaire d'enregistrement de paiement,
   annulation) — page sur-mesure comme `students/page.tsx`, pas `ResourceCrudPanel` (trop
   spécifique).
3. **Ledger des paiements** (`/payments`) — liste filtrable à l'échelle de l'école, avec un bandeau
   de statistiques (§27) intégré plutôt qu'un 4ᵉ écran séparé.

Nouveau client `apps/web/lib/fees/client.ts` suivant exactement la convention existante
(`getJson/postJson/patchJson/getBlobUrl`).

## 23. Reçus

Génération PDF synchrone à l'enregistrement du paiement, réutilisant intégralement le pipeline de
`report_cards/service.py` : `xhtml2pdf.pisa.CreatePDF` + template HTML rendu via
`jinja2.sandbox.ImmutableSandboxedEnvironment` (déjà durci contre le SSTI), stocké via le singleton
`storage` (`receipts/{school_id}/{payment_id}.pdf`), téléchargé via un endpoint authentifié et
scopé, jamais une URL publique/signée. Pas de QR (voir §15) — champ `verification_code` non repris
au MVP, réutilisable plus tard sans changement de schéma majeur si besoin.

## 24. Future architecture Mobile Money

`PaymentProvider(ABC)` dans un nouveau `apps/api/app/core/payment.py`, calqué exactement sur
`StorageProvider`/`EmailProvider` (interface abstraite, factory `get_payment_provider(provider:
str, ...)`, singleton module-level). **Une seule implémentation au MVP** : `ManualPaymentProvider`,
qui ne fait qu'enregistrer la transaction en base (aucun appel réseau, aucun SDK) — le paiement
manuel passe par cette abstraction comme le ferait un futur fournisseur réel, sans qu'aucune
intégration externe existe. Un futur `TMoneyProvider`/`FloozProvider` s'ajouterait en implémentant
la même interface et en changeant `settings.payment_provider`, sans modifier `Payment`,
`PaymentAllocation`, ni la logique de solde — exactement comme un futur fournisseur de stockage
cloud s'ajouterait sans toucher au code appelant `storage.upload(...)`.

## 25. Offline

Confirmation de la recommandation initiale de la commande : **aucune création offline de données
financières**. Justification renforcée par l'audit : aucun mécanisme de file d'attente
d'écriture locale ni de résolution de conflit n'existe nulle part dans `apps/mobile` (la Phase 12
n'a durci que la résilience réseau des écrans de lecture) ; et surtout, l'enregistrement de
paiement est proposé **uniquement via le web admin** (§13/§22) — aucun écran mobile de saisie de
paiement n'est prévu au MVP, ce qui rend la question de l'offline non pertinente pour cette phase
plutôt que de construire un support offline pour ensuite le désactiver.

## 26. Notifications

Réutilisation du motif `send_email_best_effort` déjà utilisé par `report_cards` (envoi après
commit, jamais bloquant). Proposé au MVP : un email "reçu de paiement" au(x) tuteur(s) à
l'enregistrement, contenant un lien vers la vue parent (web/mobile) plutôt qu'une pièce jointe PDF —
`EmailProvider.send(to, subject, body)` n'a pas de paramètre pièce-jointe aujourd'hui, et changer
cette interface serait hors périmètre de cette phase (point à confirmer, voir §34). Les rappels
d'échéance sont **explicitement hors périmètre** : aucun ordonnanceur de tâches n'existe dans
l'API (le Planificateur de tâches Windows des Phases 15/17 est un outil d'exploitation, pas un
mécanisme applicatif) — les ajouter nécessiterait une nouvelle brique d'infrastructure.

## 27. Analytics

Minimal, agrégats SQL simples exposés par `GET /schools/{school_id}/fees/summary` : total facturé
(somme `StudentFee.amount_due`), total encaissé (somme des allocations sur paiements `COMPLETED`),
total restant, taux de recouvrement, liste des impayés (`StudentFee` non soldée et échéance
dépassée). Affiché comme bandeau sur l'écran Ledger (§22), pas comme écran séparé — pas de BI.

## 28. Tests

Plan calqué directement sur les conventions confirmées en §7/§9 de l'audit :

- **Unit** : calculs de solde/statut dérivé, validation des contraintes d'allocation (somme ≤
  montant), précision `Numeric` (pas d'erreur d'arrondi `float`).
- **Integration** : création barème → génération `StudentFee` → paiement → allocation → reçu →
  recalcul de solde, bout en bout.
- **Security** : motif exact de `test_tenant_isolation.py` — assertions HTTP 403/404 cross-école et
  cross-organisation, vérification que les données de la victime restent inchangées après tentative
  d'écriture cross-tenant, **et** un test bas niveau reproduisant
  `test_row_level_security_hides_school_row_even_bypassing_app_check` mais sur `payments`/
  `student_fees` (session brute + `apply_tenant_context` + contrôle positif/négatif).
- **Concurrency** : deux requêtes quasi simultanées avec la même `idempotency_key` → une seule ligne
  créée ; deux allocations concurrentes proches de la limite d'un `amount_due`.
- **Regression** : les 183 tests existants doivent rester verts, plus les nouveaux.

## 29. Risques

- Nouveauté du typage monétaire (`Numeric`) et de l'idempotence par clé — aucun précédent direct
  dans ce dépôt, risque d'erreur d'implémentation si non testé rigoureusement (couvert par §28).
- Sensibilité intrinsèque des données financières — cohérent avec le constat déjà fait en Phase 13
  (*"la finance touchant par nature des données plus sensibles que tout ce qui existe aujourd'hui"*).
- Risque de dérive de périmètre vers une facturation/comptabilité complète — mitigé par le
  découpage strict en §31.

## 30. Dépendances

Aucune nouvelle dépendance externe : `xhtml2pdf`, `jinja2`, `qrcode` (non utilisé ici) sont déjà
présents pour `report_cards` ; `Numeric`/`Decimal` sont dans la bibliothèque standard/SQLAlchemy
déjà utilisée. Dépend uniquement de `students`, `schools`, `academics` (années académiques,
classes, niveaux) déjà en place.

## 31. Hors périmètre

Mobile Money réel (TMoney, Flooz, Stripe, API bancaire, webhook fournisseur), comptabilité générale,
paie, fiscalité, rapprochement bancaire avancé, multi-devise complexe (une devise par école,
`School.currency` existant suffit), IA financière, paiement offline, abonnement SaaS d'EduSphere
envers l'école elle-même (à distinguer explicitement de cette fonctionnalité, qui concerne l'école
facturant ses élèves), marketplace, BI avancée, document "facture" formel regroupant plusieurs
frais, rappels d'échéance automatisés (nécessite un ordonnanceur non prouvé), saisie de paiement
depuis mobile (web uniquement au MVP), remises/exonérations en entité dédiée, échéanciers
automatisés, vérification par QR code des reçus.

## 32. Critères GO/NO-GO

**GO** : aucun conflit avec l'existant (confirmé, zéro code financier préexistant), périmètre
strictement additif (aucune migration ne modifie les tables académiques/élèves/écoles existantes,
uniquement de nouvelles FK), réutilisation extensive des conventions prouvées (RLS, RBAC, providers,
génération PDF, `ResourceCrudPanel`, `ScreenState`/`useAsyncData`), aucune nouvelle dépendance ni
infrastructure requise. Aucun critère de HOLD (secret détecté, mauvais repository, régression,
fichier sensible) ne s'applique — sans objet pour une Discovery.

## 33. Plan d'implémentation proposé

1. Migration `0009_fees.py` : 5 tables + RLS + seed RBAC (`fees.read/manage`,
   `payments.read/manage`) sur SCHOOL_ADMIN/DIRECTOR/ACCOUNTANT (§18).
2. Module backend `app/modules/fees/` (models, schemas, service, router) — `service.py` présent dès
   le départ (logique de solde/allocation/idempotence non triviale).
3. `app/core/payment.py` : `PaymentProvider`/`ManualPaymentProvider`/factory/singleton.
4. Génération de reçu PDF (réutilisation du pipeline `report_cards`).
5. Web : 3 écrans (§22) + `lib/fees/client.ts`.
6. Mobile : onglet "Frais" parent en lecture seule (§21).
7. Notification email best-effort à l'enregistrement du paiement.
8. Suite de tests complète (§28), régression des 183 tests existants.
9. Documentation : mise à jour de `docs/architecture/overview.md` + nouveau document dédié frais.

## 34. Questions nécessitant décision humaine

1. La suppression d'`Invoice` et `Receipt` comme entités séparées (§14) est-elle acceptable, ou
   souhaitez-vous un document "facture" formel regroupant plusieurs frais dès cette phase ?
2. La liste de méthodes de paiement (`CASH, BANK_TRANSFER, OTHER`) suffit-elle au pilote, ou
   d'autres valeurs texte (chèque, dépôt agent) doivent-elles être ajoutées dès maintenant (sans
   impact fonctionnel, aucune n'étant un fournisseur "live") ?
3. Le partage de permissions proposé (`ACCOUNTANT` gère les paiements mais pas la configuration des
   barèmes, réservée à SCHOOL_ADMIN/DIRECTOR) correspond-il à la pratique réelle des écoles visées ?
4. L'email de reçu doit-il se contenter d'un lien vers la vue parent (pas de pièce jointe, pas de
   changement d'interface `EmailProvider`), ou une évolution de `EmailProvider` pour supporter les
   pièces jointes est-elle acceptée dans le périmètre d'une phase ultérieure ?
5. L'enregistrement de paiement uniquement via le web admin (aucun écran mobile de saisie) est-il
   acceptable pour le pilote, sachant que la collecte cash se fait parfois hors bureau ?
6. Les rappels d'échéance automatisés, différés faute d'ordonnanceur applicatif prouvé, doivent-ils
   être planifiés comme une phase de suivi explicite ?

---

# PHASE 19 DISCOVERY VERDICT

**GO WITH NOTES**

School Fees & Billing est confirmé, par un audit réel et non par supposition, comme le candidat le
plus prioritaire et le plus sûr à construire ensuite : aucune fonctionnalité financière n'existe
(vérifié par grep exhaustif), le besoin est documenté de façon répétée et cohérente depuis six
phases, les blocages précédemment cités sont résolus, et le modèle proposé (5 entités, pas 7)
réutilise à un niveau inhabituellement élevé les conventions déjà éprouvées du dépôt (RLS, RBAC,
`StorageProvider`/`EmailProvider`, pipeline PDF de `report_cards`, `ResourceCrudPanel`,
`ScreenState`/`useAsyncData`). Aucun blocage technique, aucune dépendance manquante, aucun conflit
avec l'architecture existante.

Le "WITH NOTES" reflète les 6 points de la §34 : ce sont des décisions de produit/périmètre, pas des
inconnues techniques — elles doivent être tranchées avant le lancement de l'implémentation, mais
n'empêchent pas de considérer la Discovery elle-même comme aboutie.

Aucune implémentation n'a été commencée. Aucun autre fichier que celui-ci n'a été modifié.
