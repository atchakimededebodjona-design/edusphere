# PHASE 6 — ATTENDANCE / ASSIDUITÉ

Document de référence pour l'exécution de la Phase 6 par l'agent (Antigravity / Claude Code).
Prérequis : Phases 0 à 5 livrées et stables.

**Emplacement de ce document** : placé ici, à `docs/phases/PHASE_6_ATTENDANCE_PLAN.md`, sur
instruction explicite. Ce point mérite d'être signalé : la convention **réellement observée** dans
le repository jusqu'ici est un fichier `PHASE_N_....md` à la racine
(`PHASE_1_AUTH_MULTITENANCY_PLAN.md`) — il n'existait pas de dossier `docs/phases/` avant ce
document. Le fichier créé à la racine lors du cadrage initial
(`PHASE_1_AUTH_MULTITENANCY_PLAN.md`-style, `PHASE_6_ATTENDANCE_PLAN.md`) a été supprimé pour éviter
deux copies divergentes du même plan. Si ce nouvel emplacement doit devenir la convention pour les
phases suivantes, ce sera à confirmer/documenter (par exemple dans `README.md`) au moment voulu —
non fait ici, aucun autre fichier n'a été touché.

**Statut** : plan v2, intégrant les décisions validées avec ajustements. **Aucun code n'a été
écrit. Aucun autre fichier n'a été modifié.**

---

## 1. Contexte

EduSphere est une plateforme SaaS scolaire multi-tenant. Les Phases 0 à 5 ont livré : bootstrap,
auth + multi-tenancy (RBAC, RLS), administration scolaire (`academics`), élèves (`students`),
notes/moyennes/classement (`grades`), bulletins PDF + gestion utilisateurs (`report_cards`,
`users`). La Phase 6 ajoute le domaine métier **Présence / Assiduité**.

Ce document est un cadrage **technique et fonctionnel uniquement**. Il intègre les décisions
validées par l'utilisateur (avec ajustements) sur la base du cadrage v1. Les changements par
rapport à la v1 sont signalés explicitement dans chaque section concernée.

---

## 2. État actuel du repository (constaté par inspection directe)

Inchangé depuis le cadrage v1 — rappel des points structurants :

- Migrations Alembic existantes : `0001` à `0006`. Prochaine migration : `0007`.
- Modules API : `auth`, `organizations`, `schools`, `rbac`, `academics`, `students`, `grades`,
  `report_cards`, `users` — structure fixe `models.py`/`schemas.py`/`router.py`(+`service.py`).
- Montage des routers **à plat** sous `/api/v1` (pas de sous-préfixe par module, sauf
  `auth`/`organizations`/`schools`/`users`) — confirmé sur `grades`, `academics`, `students`,
  `report_cards`.
- `rbac/seed.py` : source unique du catalogue RBAC, blocs `PHASEn_*` strictement additifs, toujours
  exactement 2 permissions par module (`.read`/`.manage`).
- `ensure_permission()` + `is_teacher_only()` + `TeacherAssignment` : seul mécanisme d'autorisation
  fine existant (utilisé par `grades`, réutilisé ici).
- `Guardian` n'est relié à aucun `users.id` — aucun chemin technique parent → enfant aujourd'hui.
- `packages/*` toujours vides, `infrastructure/` toujours placeholders — non concernés.

---

## 3. Objectifs

Inchangé — cf. v1 section 3 : enseignants (appel, présence/absence/retard, motif optionnel),
administration (consultation, recherche, filtres, statistiques, corrections selon permissions),
portail parent hors périmètre mais architecture compatible, mobile enseignant intégré sans refonte.

---

## 4. Périmètre

- Modèle de données présence, **scopé par classe entière** (changement validé — voir section 6 et
  8), et non par classe+matière comme dans le cadrage v1.
- API idempotente (upsert), scopée école/organisation, RLS activé.
- RBAC : 2 permissions (`attendance.read`/`attendance.manage`), scoping enseignant réutilisant
  `TeacherAssignment` sans modification du module `academics`.
- Vérification explicite École **et** Classe pour chaque élève à chaque écriture (renforcement
  validé par rapport à v1 et par rapport à ce que fait `grades` aujourd'hui).
- Web : écran de saisie (grille classe × élèves, sans sélection de matière), historique, filtres,
  statistiques.
- Mobile : action "Faire l'appel" au niveau de l'écran classe existant.
- Statistiques simples : présents, absents, retards, absences justifiées, taux de présence — par
  élève et par classe.
- Documentation des points d'extension futurs (notifications, portail parent) sans les construire.

---

## 5. Hors périmètre

Inchangé et confirmé par la validation : portail Parent (aucune relation `Guardian → User`),
notifications complètes, mode offline complet, statistiques avancées/évolution dans le temps,
géolocalisation, biométrie, reconnaissance faciale, QR code d'appel, RFID, reconnaissance vocale, IA
prédictive d'absentéisme, refonte mobile/microservices, catalogue configurable de motifs
(`AttendanceReason` en tant que table), calendrier des jours fériés, `campus`/`partners`/`country`
avancé.

**Confirmé explicitement** : pas de notion de "professeur principal" / homeroom — l'autorisation
enseignant reste basée uniquement sur `TeacherAssignment` (voir section 6).

---

## 6. Analyse des modules existants

*(Reprend l'analyse détaillée de la v1 — `academics`, `students`, `rbac`, `users`/`auth`, `grades` —
non reproduite intégralement ici pour éviter la redondance ; seul le point qui change est détaillé
ci-dessous.)*

### Point clé qui change avec la décision "session scopée par classe entière"

`TeacherAssignment` lie un `User` (TEACHER) à un `ClassSubject`, **pas** directement à une
`SchoolClass`. Il n'existe **aucune** notion de professeur principal au niveau `SchoolClass`, et il
n'en sera **pas créé** (décision validée).

Le repository a déjà résolu exactement ce problème ailleurs : `academics/router.py::list_classes`
détermine si un enseignant peut voir une classe entière en vérifiant s'il a **au moins une**
`TeacherAssignment` sur **n'importe quel** `ClassSubject` appartenant à cette classe :

```python
stmt = select(SchoolClass).where(SchoolClass.school_id == school_id)
if await is_teacher_only(db, current_user, school.organization_id, school.id):
    stmt = (
        stmt.join(ClassSubject, ClassSubject.class_id == SchoolClass.id)
        .join(TeacherAssignment, TeacherAssignment.class_subject_id == ClassSubject.id)
        .where(TeacherAssignment.user_id == current_user.id)
        .distinct()
    )
```

**C'est exactement la règle à réutiliser pour l'autorisation d'appel** : un enseignant peut
créer/modifier une session de présence pour une `SchoolClass` s'il a au moins une
`TeacherAssignment` sur un `ClassSubject` de cette classe. Aucune modification d'`academics` n'est
nécessaire — la requête ci-dessus est copiée telle quelle dans le nouveau module `attendance`
(section 9/11), sous forme d'un test d'existence (`EXISTS`) plutôt que d'un filtre de liste.

---

## 7. Architecture proposée

Nouveau module `apps/api/app/modules/attendance/` (`models.py`, `schemas.py`, `service.py`,
`router.py`), monté à plat sous `/api/v1`, tag `"attendance"` — inchangé par rapport à la v1.

**Changement structurel validé** : `AttendanceSession` référence `class_id` (→ `classes.id`,
`SchoolClass`) au lieu de `class_subject_id`. Une session = un appel pour une classe entière, à une
date donnée, dans une période académique donnée.

Pas de table de cache pour les statistiques (confirmé, section 16) — agrégation directe sur
`attendance_records`, comme en v1, pour les mêmes raisons (les statistiques d'assiduité sont des
comptages simples, pas un calcul pondéré coûteux comme les moyennes de `grades`).

---

## 8. Modèle de données

### Entités — décisions validées

| Entité | Décision | Détail |
|---|---|---|
| `AttendanceSession` | **Conservée, scopée par `class_id`** (changement v1 → v2) | Un appel pour une `SchoolClass` entière, à une `session_date`, dans un `academic_term_id`. |
| `AttendanceRecord` | **Conservée** | Une ligne par élève par session. |
| `AttendanceStatus` | **Rejetée en tant que table** (confirmé) | `status: String(16)` + `Literal["PRESENT", "ABSENT", "LATE"]` côté schémas. |
| `AttendanceReason` | **Rejetée en tant que table** (confirmé) | `justified: Boolean` + `reason: String(500) nullable`. |

### `attendance_sessions`

| Colonne | Type | Contrainte |
|---|---|---|
| `id` | UUID PK | |
| `school_id` | UUID FK `schools.id` CASCADE | NOT NULL, index |
| `organization_id` | UUID FK `organizations.id` CASCADE | NOT NULL, index (dénormalisé) |
| `class_id` | UUID FK `classes.id` CASCADE | NOT NULL, index — **remplace `class_subject_id` de la v1** |
| `academic_term_id` | UUID FK `academic_terms.id` CASCADE | NOT NULL, index |
| `session_date` | Date | NOT NULL |
| `taken_by` | UUID FK `users.id` SET NULL | nullable (audit) |
| `locked_at` | DateTime(timezone=True) | nullable |
| `locked_by` | UUID FK `users.id` SET NULL | nullable |
| `created_at` / `updated_at` | DateTime(timezone=True) | server_default now() |

Pas de `UniqueConstraint` sur `(class_id, session_date)` — plusieurs sessions le même jour restent
autorisées (ex. appel matin + après-midi), règle inchangée depuis la v1.

### `attendance_records`

| Colonne | Type | Contrainte |
|---|---|---|
| `id` | UUID PK | |
| `school_id` / `organization_id` | UUID FK (dénormalisés) | NOT NULL, index |
| `session_id` | UUID FK `attendance_sessions.id` CASCADE | NOT NULL, index |
| `student_id` | UUID FK `students.id` CASCADE | NOT NULL, index |
| `status` | String(16) | NOT NULL — `PRESENT` / `ABSENT` / `LATE` |
| `justified` | Boolean | NOT NULL, default `false` |
| `reason` | String(500) | nullable |
| `recorded_by` | UUID FK `users.id` SET NULL | nullable (audit — qui a saisi/corrigé cette ligne) |
| `created_at` / `updated_at` | DateTime(timezone=True) | server_default now() |

`UniqueConstraint("session_id", "student_id", name="uq_attendance_record")` — **confirmé et
explicitement requis** (décision validée point 4).

Les 5 champs explicitement mandatés (`session_id`, `student_id`, `status`, `justified`, `reason`)
sont tous présents. `recorded_by`/`created_at`/`updated_at` sont des ajouts de convention (audit,
horodatage), cohérents avec chaque autre table du repository, non exclus par la validation.

### Relations (inchangées sauf la ligne Classe)

- **School / Organization** : dénormalisées, comme partout.
- **Classe** : **directe** désormais (`AttendanceSession.class_id → classes.id`), alors qu'en v1
  elle était indirecte via `class_subject_id`. Simplification directe issue de la décision validée.
- **Student** : directe sur `AttendanceRecord.student_id`.
- **AcademicYear** : indirecte, via `academic_term_id → academic_terms.academic_year_id`.
- **Teacher/User** : `taken_by`/`locked_by`/`recorded_by` (audit) ; autorisation via
  `TeacherAssignment` réutilisé tel quel (section 6), pas de nouvelle table de lien.
- **Subject** : **plus de lien direct ou indirect** sur la session elle-même (changement v1 → v2 —
  la présence n'est plus rattachée à une matière).
- **Date** : `session_date` sur la session.
- **Période académique** : `academic_term_id` explicite sur la session.

### Index

`ix_attendance_sessions_{school_id,organization_id,class_id,academic_term_id}`,
`ix_attendance_records_{school_id,organization_id,session_id,student_id}`.

---

## 9. Règles métier

| Question | Règle retenue | Changement vs v1 |
|---|---|---|
| Qu'est-ce qu'une session d'appel ? | Un enregistrement de présence pour une **classe entière** (`class_id`), à une date donnée, dans une période académique donnée. | **Changé** : classe entière, plus classe+matière. |
| Qui peut créer une session ? | `attendance.manage` scopé organisation/école ; si TEACHER-only, doit avoir au moins une `TeacherAssignment` sur un `ClassSubject` de cette classe (règle de `list_classes`, section 6). | **Changé** : vérifie l'appartenance à la classe via n'importe quelle matière affectée, pas une matière précise. |
| Qui peut modifier une présence ? | Même règle, et la session ne doit pas être verrouillée si l'appelant est TEACHER-only. Un SCHOOL_ADMIN/DIRECTOR peut modifier même verrouillé. | Inchangé (v1). |
| Peut-on modifier après validation ? | Oui pour l'administration, non pour un enseignant seul une fois `locked_at` renseigné. Verrouillage = `attendance.manage` réservé aux rôles non TEACHER-only. | Inchangé (v1), non contredit par la validation. |
| Comment gérer les retards ? | `status = "LATE"`, `justified`/`reason` optionnels. | Inchangé. |
| Absences justifiées / sans motif | `justified` + `reason` nullable, `reason = NULL` valide. | Inchangé. |
| Comment éviter les doublons ? | `UniqueConstraint(session_id, student_id)`. | Inchangé, **confirmé explicitement**. |
| **Idempotence de l'API** | `POST /attendance-records` est un **upsert** : soumettre deux fois la même entrée `(session_id, student_id)` aboutit au même état final, sans erreur. Choix explicitement motivé par la compatibilité avec un futur mode offline (une resoumission après reconnexion ne doit pas échouer ni dupliquer). | **Tranché** (question ouverte n°6 de la v1, close par la validation point 4). |
| Élève inscrit après une session | Roster calculé dynamiquement depuis `StudentEnrollment` actif au moment de la saisie ; sessions passées non complétées rétroactivement. | Inchangé. |
| Élève change de classe | Les `AttendanceRecord` déjà créés restent liés à leur session/classe d'origine, fait historique immuable. | Inchangé. |
| Jours sans cours / période académique | `session_date` doit tomber dans `[academic_term.start_date, academic_term.end_date]`, et `academic_term.academic_year_id` doit correspondre à l'`academic_year_id` de la classe (`session.class_id → classes.academic_year_id`), sinon `400`. | Inchangé dans le principe, précisé : contrôle de cohérence classe↔période ajouté (nécessaire maintenant que la session est directement liée à une classe). |
| **Date future** | **Séparée explicitement de la règle ci-dessus, sur demande.** Question non tranchée par la validation — reste ouverte, voir section 23, point 1. | **Nouveau point, isolé de la validation de période sur demande explicite.** |
| Plusieurs sessions le même jour | Autorisé nativement, aucune contrainte d'unicité sur `(class_id, session_date)`. | Inchangé. |
| Données historiques | Aucune politique de purge/archivage. | Inchangé. |
| **Vérification élève ↔ périmètre** | Avant toute écriture d'un `AttendanceRecord` : (1) `student.school_id == session.school_id` ; **(2) l'élève doit avoir une `StudentEnrollment` active pour `session.class_id`** — pas seulement la bonne école. | **Renforcé par la validation** (point 9) — v1 ne vérifiait que l'école, pas la classe. Voir section 11. |

---

## 10. RBAC

Inchangé et confirmé — exactement 2 permissions, aucune permission `.validate` séparée :

```python
PHASE6_PERMISSIONS = {
    "attendance.read": "Consulter les présences, absences et retards",
    "attendance.manage": "Faire l'appel et corriger les présences (un enseignant reste limité aux classes où il a une affectation)",
}

PHASE6_ROLE_PERMISSIONS = {
    "SUPER_ADMIN": ["attendance.read", "attendance.manage"],
    "PLATFORM_SUPPORT": ["attendance.read"],
    "SCHOOL_ADMIN": ["attendance.read", "attendance.manage"],
    "DIRECTOR": ["attendance.read", "attendance.manage"],
    "TEACHER": ["attendance.read", "attendance.manage"],
    "STAFF": ["attendance.read"],
}
```

Mapping identique à `PHASE4_ROLE_PERMISSIONS` (`grades`). `ACCOUNTANT`/`PARENT`/`STUDENT` : aucune
permission en Phase 6.

---

## 11. Multi-tenancy et RLS

- `attendance_sessions`/`attendance_records` : `school_id` + `organization_id` dénormalisés, RLS
  activée et forcée, policy **textuellement identique** à celle de `grades` (`0005`) :

```sql
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
```

- Aucun nouveau `GRANT` requis pour `edusphere_app` (`ALTER DEFAULT PRIVILEGES` déjà posé en `0002`
  couvre toute nouvelle table).
- **Contrôle applicatif primaire** : `ensure_permission()` sur chaque endpoint, comme partout.
- **Renforcement validé (point 9), plus strict que `grades`** : avant toute écriture d'un
  `AttendanceRecord`, le service vérifie **explicitement, en plus de RLS et des permissions** :
  1. `student.school_id == session.school_id` (école) ;
  2. il existe une `StudentEnrollment` avec `student_id`, `class_id == session.class_id`,
     `status == "ACTIVE"` (classe) — **pas seulement l'école, comme demandé explicitement**.
  Si l'une des deux conditions échoue → `404 Not Found` ("Student not found in this class"), avant
  toute écriture. C'est une vérification **au niveau service**, indépendante de RLS et des
  permissions — troisième filet, spécifique à `attendance`, qui n'existe pas dans `grades`
  aujourd'hui (lacune identifiée en v1, non reproduite ici, conformément à la validation).

---

## 12. API

Convention réelle du repository : montage à plat sous `/api/v1`, sans sous-préfixe. Endpoints
adaptés au scoping par classe (changement vs v1) :

| Méthode | Route | Description | Permission |
|---|---|---|---|
| GET | `/api/v1/attendance-sessions?class_id=&academic_term_id=&date_from=&date_to=` | Liste des sessions | `attendance.read` |
| POST | `/api/v1/attendance-sessions` | Crée une session (`class_id`, `academic_term_id`, `session_date`) | `attendance.manage` (+ scoping enseignant §6) |
| GET | `/api/v1/attendance-sessions/{id}` | Détail | `attendance.read` |
| PATCH | `/api/v1/attendance-sessions/{id}` | Verrouiller/déverrouiller | `attendance.manage`, réservé rôles non TEACHER-only |
| GET | `/api/v1/attendance-records?session_id=` | Présences d'une session | `attendance.read` |
| POST | `/api/v1/attendance-records` | Soumission en masse, **upsert idempotent** (§9) | `attendance.manage` (+ scoping + check École/Classe §11) |
| PATCH | `/api/v1/attendance-records/{id}` | Correction d'une ligne | `attendance.manage` (+ verrouillage) |
| GET | `/api/v1/students/{student_id}/attendance-summary?academic_term_id=` | Statistiques élève (§16) | `attendance.read` |
| GET | `/api/v1/classes/{class_id}/attendance-statistics?academic_term_id=` | Statistiques classe (§16) | `attendance.read` |

```python
class AttendanceRecordEntry(BaseModel):
    student_id: uuid.UUID
    status: Literal["PRESENT", "ABSENT", "LATE"]
    justified: bool = False
    reason: str | None = None

class AttendanceRecordsBulkCreate(BaseModel):
    session_id: uuid.UUID
    records: list[AttendanceRecordEntry] = Field(min_length=1)
```

---

## 13. Web

**Changement vs v1** : plus de sélecteur "Matière" — le flux devient École → Classe → Période →
Date (au lieu de École → Classe → Matière → Période).

- `apps/web/app/(app)/attendance/page.tsx` : sélection classe → période → date.
- `AttendanceSessionPanel.tsx` : grille élève × statut (présent/absent/retard) + case justifié +
  motif, soumission en masse. Roster chargé via `studentsClient.list(schoolId, { classId })` —
  identique au patron `GradeBookPanel`, mais sans l'étape matière.
- Historique/filtres (date, classe, élève) + statistiques (section 16).

Client `apps/web/lib/attendance/client.ts`, calqué sur `apps/web/lib/grades/client.ts`.

**Fichier existant à modifier** : `apps/web/components/app-shell/Nav.tsx` — entrée
`{ href: "/attendance", label: "Présences", permission: "attendance.read" }`.

---

## 14. Mobile

**Changement vs v1** : la session étant scopée par classe et non par matière, le point d'entrée
naturel n'est plus un lien par matière dans `classes/[classId].tsx`, mais **une seule action au
niveau de l'écran classe**, visible dès lors que l'enseignant a au moins une affectation dans cette
classe (condition déjà calculée par l'écran existant : `mySubjects.length > 0`).

- Nouveau : `apps/mobile/app/(teacher)/attendance/[classId].tsx` — liste des élèves du roster avec
  boutons de statut par élève (présent/absent/retard), case justifié + motif, date du jour par
  défaut, soumission en masse (upsert idempotent, cohérent avec §9).
- Nouveau client `apps/mobile/lib/attendance/client.ts`, calqué sur `apps/mobile/lib/grades/client.ts`.

**Fichier existant à modifier** : `apps/mobile/app/(teacher)/classes/[classId].tsx` — ajout d'un
bouton "Faire l'appel" (visible si `mySubjects.length > 0`), navigant vers
`/attendance/[classId]`, **à côté de**, sans remplacer, la liste "Mes matières" existante qui reste
le point d'entrée des évaluations.

**Mode offline** : non implémenté (confirmé exclu, point 8). La conception idempotente de
`POST /attendance-records` (upsert par `(session_id, student_id)`, confirmée point 4) rend une
future file d'attente offline possible sans changement de contrat API — point d'architecture
documenté, rien construit.

---

## 15. Notifications futures

Inchangé (v1) — aucun système de notification n'existe dans le repository, rien n'est construit.
Points d'extension documentés uniquement :

| Événement | Déclenché depuis | Donnée utile |
|---|---|---|
| `student.absent` | `attendance/service.py`, après commit d'un `AttendanceRecord` `status == "ABSENT"` | `student_id`, `session_id`, `session_date`, `justified` |
| `student.late` | idem, `status == "LATE"` | idem |
| `attendance.updated` | idem, sur toute correction | `record_id`, ancien/nouveau statut |

---

## 16. Statistiques

**Confirmé et précisé (point 7 de la validation)** — calculées à la volée, deux endpoints (§12) :

**Par élève** (`GET /students/{id}/attendance-summary?academic_term_id=`) :

```json
{
  "student_id": "...",
  "academic_term_id": "...",
  "total_sessions": 42,
  "present_count": 38,
  "absent_count": 3,
  "late_count": 1,
  "justified_absence_count": 2,
  "attendance_rate": 0.93
}
```

**Par classe** (`GET /classes/{id}/attendance-statistics?academic_term_id=`) : mêmes agrégats,
ventilés par élève de la classe + un total classe. Endpoint confirmé cohérent avec l'architecture
(agrégation SQL directe, pas de nouvelle table).

**Définition retenue pour `attendance_rate`** (à valider explicitement, non spécifiée par
l'utilisateur) : `(present_count + late_count) / total_sessions` — un retard compte comme une
présence pour le taux (l'élève était là), mais reste comptabilisé séparément dans `late_count`.
Alternative possible : ne compter que `present_count / total_sessions` (un retard ne compte pas).
**Signalé explicitement en section 23** pour confirmation, car ce n'est ni dans le prompt initial ni
dans la validation.

Évolution dans le temps / tendances : **hors périmètre** (confirmé, point 8).

---

## 17. Migrations

Une seule migration, `apps/api/alembic/versions/0007_attendance.py`, `down_revision = "0006"`,
patron identique à `0005_grades.py` :

1. `create_table("attendance_sessions", ...)` avec `class_id` (pas `class_subject_id`) + index.
2. `create_table("attendance_records", ...)` + index + `UniqueConstraint("session_id", "student_id")`.
3. Seed RBAC (`PHASE6_PERMISSIONS`/`PHASE6_ROLE_PERMISSIONS`) via le même patron SQL que `0005`.
4. RLS : boucle sur `["attendance_sessions", "attendance_records"]`.
5. `downgrade()` : miroir exact de `0005_grades.py::downgrade`.

Pas de modification de `0001`-`0006`. `rbac/seed.py` reçoit un ajout additif uniquement.

---

## 18. Tests

`apps/api/tests/test_attendance.py`, structure calquée sur `test_grades.py`. **Liste explicite
requise par la validation (point 10)**, toutes couvertes :

- Création correcte d'un enregistrement `PRESENT`.
- Création correcte d'un enregistrement `ABSENT`.
- Création correcte d'un enregistrement `LATE`.
- `justified = true`/`false` correctement persisté et renvoyé.
- `reason` correctement persisté, y compris `None` (absence sans motif valide).
- Doublon `session_id`+`student_id` : upsert idempotent (pas d'erreur, pas de duplication —
  vérifie qu'une seconde soumission identique laisse une seule ligne et le même état final,
  conformément à la règle d'idempotence §9).
- Permissions : un `STAFF` (lecture seule) qui tente `POST /attendance-records` → 403.
- `TeacherAssignment` : un TEACHER affecté à au moins une matière de la classe peut créer une
  session/y écrire ; un TEACHER sans aucune affectation dans la classe → 403 (patron
  `test_teacher_restricted_to_assigned_class_subject`, adapté à la vérification "au moins une
  matière de la classe" décrite section 6).
- Cross-tenant : école A ne peut ni lire ni écrire une session/ligne de l'école B, y compris IDs
  forgés (patron `test_tenant_isolation.py`), + vérification RLS directe en base.
- Élève d'une autre école inaccessible → 404 (vérifie §11 point 1).
- **Élève d'une autre classe de la même école inaccessible** → 404 (vérifie §11 point 2 —
  spécifique à la validation, absent du cadrage v1).
- Statistiques : résultat de `attendance-summary`/`attendance-statistics` correct sur un jeu de
  données connu (ex. 8 présents / 2 absents / 1 retard justifié → vérifie les 5 compteurs et le
  taux selon la formule §16).
- Dates hors période académique : `session_date` hors de `[start_date, end_date]` de
  l'`academic_term_id` fourni → 400.
- Verrouillage : TEACHER bloqué sur session verrouillée, SCHOOL_ADMIN/DIRECTOR non bloqué.
- Régression : suite complète `pytest` verte, aucun test existant cassé.

---

## 19. Sécurité

- RLS forcée, policy éprouvée (identique à `grades`/`students`/`academics`).
- Filtrage applicatif systématique (`ensure_permission`), primaire par rapport à RLS.
- **Vérification École + Classe explicite avant écriture** (renforcement validé, §11) — dépasse ce
  que fait `grades` aujourd'hui.
- Aucune donnée sensible nouvelle.
- Verrouillage des sessions : traçabilité via `recorded_by`/`taken_by`/`locked_by`.
- Aucun nouveau rôle Postgres, secret, ou variable d'environnement.

---

## 20. Risques

| Risque | Impact | Mitigation |
|---|---|---|
| La vérification "au moins une `TeacherAssignment` dans la classe" autorise un enseignant à faire l'appel même pour une matière où il n'enseigne pas dans cette classe | Un enseignant de maths peut techniquement faire l'appel "présence générale" d'une classe où il n'a qu'une heure/semaine | Accepté comme comportement voulu par la décision de scoper par classe entière (pas par matière) — c'est la contrepartie du choix validé, pas un bug |
| Verrouillage trop strict vs. corrections tardives légitimes | Frustration utilisateur | Déverrouillage toujours possible pour SCHOOL_ADMIN/DIRECTOR |
| Volumétrie (une ligne par élève par session) | Requêtes de stats plus lentes à grande échelle | Index prévus sur `session_id`/`student_id`/`school_id` |
| Policy RLS mal recopiée | Faille d'isolation tenant silencieuse | Copier-coller strict du texte déjà testé (`0005`) |
| Définition du `attendance_rate` non confirmée par l'utilisateur | Chiffre affiché ne correspond pas à l'attente métier | Formule explicitée §16, signalée en question ouverte §23 |
| Question "date future" non tranchée | Blocage d'implémentation si un enseignant doit pré-remplir une session à l'avance, ou au contraire données incohérentes si autorisé sans réflexion | Isolée explicitement comme décision à trancher avant migration, §23 |

---

## 21. Critères d'acceptation

Inchangé (v1) + ajouts liés aux renforcements validés :

- Migration `0007` s'applique proprement sur base vierge et sur base à `0006`.
- `pytest` vert, incluant `test_attendance.py`, sans régression.
- Isolation tenant vérifiée (applicatif + RLS direct) pour les deux nouvelles tables.
- Vérification École + Classe testée et vérifiée (pas seulement École).
- Un enseignant ne peut faire l'appel que pour une classe où il a au moins une affectation.
- Idempotence de `POST /attendance-records` testée explicitement (double soumission identique).
- `ruff check .`, `mypy app` verts. `docker compose up` + migrations sans erreur.
- Web : `lint`/`type-check`/`build` verts. Mobile : `type-check` vert, navigation existante non
  cassée (accès aux évaluations toujours fonctionnel depuis `classes/[classId].tsx`).
- Aucune modification de `0001`-`0006`, ni des blocs `rbac/seed.py` `PHASE1`-`PHASE5`, ni du modèle
  `academics` (confirmé, décision point 1).

---

## 22. Plan d'implémentation (une fois validé)

1. `rbac/seed.py` — ajout `PHASE6_PERMISSIONS`/`PHASE6_ROLE_PERMISSIONS`.
2. `modules/attendance/models.py` (`class_id`, pas `class_subject_id`).
3. `alembic/versions/0007_attendance.py`.
4. `modules/attendance/schemas.py`.
5. `modules/attendance/service.py` — upsert idempotent + validations (période, École+Classe élève).
6. `modules/attendance/router.py` — autorisation enseignant via requête `EXISTS TeacherAssignment`
   par classe (§6).
7. `main.py` — enregistrement du router.
8. `tests/test_attendance.py` (liste complète §18).
9. Web : `lib/attendance/client.ts`, `app/(app)/attendance/*`, entrée `Nav.tsx`.
10. Mobile : `lib/attendance/client.ts`, `app/(teacher)/attendance/[classId].tsx`, bouton dans
    `classes/[classId].tsx`.
11. Suite complète : `pytest`, `ruff`, `mypy`, lint/type-check/build web, type-check mobile.
12. Rapport de phase (format Phase 1).

---

## 23. Questions / décisions nécessitant validation

Les points 1 à 4, 6 et 7 du cadrage v1 sont **tranchés** par la validation (scoping classe,
pas d'`attendance.validate`, `reason` texte libre, période académique contrainte, portail parent
documenté seulement, statistiques par classe incluses). Il reste :

1. **Date future** (explicitement isolée par la demande de validation, point 5) : une session
   peut-elle être créée avec `session_date` postérieure à la date du jour ? Les écoles utilisent
   parfois `School.timezone` (champ déjà existant depuis Phase 1) pour définir "aujourd'hui" —
   l'utiliser correctement ajouterait de la complexité de conversion de fuseau. **Recommandé pour
   cette phase : ne pas bloquer les dates futures** (pas de contrôle "date ≤ aujourd'hui"), pour
   rester simple ; seule la contrainte d'appartenance à la période académique (§9) s'applique. À
   confirmer.
2. **Formule du taux de présence** (`attendance_rate`) : `(present + late) / total` (retard compte
   comme présence, recommandé) vs. `present / total` (retard ne compte pas). Non spécifiée par la
   validation — à confirmer avant implémentation des endpoints de statistiques (§16).
3. **Comportement de `PATCH /attendance-sessions/{id}` pour le verrouillage** : un simple champ
   `locked: bool` dans le payload (recommandé, cohérent avec les `PATCH` existants type
   `AssessmentResultUpdate`), ou une route dédiée (`POST /attendance-sessions/{id}/lock`) ? Détail
   d'implémentation mineur, sans impact sur le modèle de données — proposé par défaut : champ dans
   le `PATCH` existant, à confirmer seulement si préférence contraire.

---

**Ne rien implémenter avant confirmation des 3 points ci-dessus (mineurs comparés à la v1 — les
décisions structurantes sont déjà validées).**
