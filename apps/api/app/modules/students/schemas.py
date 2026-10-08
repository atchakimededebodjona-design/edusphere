import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Sex = Literal["M", "F"]
StudentStatus = Literal["ACTIVE", "INACTIVE", "GRADUATED", "WITHDRAWN", "TRANSFERRED"]
EnrollmentStatus = Literal["ACTIVE", "WITHDRAWN", "TRANSFERRED", "COMPLETED"]
GuardianRelationship = Literal["father", "mother", "guardian", "other"]
# TRANSFERRED existe pour cohérence avec le concept déjà présent (EnrollmentStatus) mais n'est
# jamais produit par la réinscription/promotion en masse elle-même (voir service.py::bulk_promote_students).
PromotionType = Literal["PROMOTED", "REPEATED", "TRANSFERRED"]
ExitType = Literal["GRADUATED", "TRANSFERRED", "WITHDRAWN", "OTHER"]


# --- Students ------------------------------------------------------------------
class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    matricule: str
    first_name: str
    last_name: str
    date_of_birth: date
    sex: Sex
    place_of_birth: str | None
    address: str | None
    status: StudentStatus
    photo_path: str | None
    created_at: datetime
    updated_at: datetime
    # Renseignés UNIQUEMENT par GET /students (liste), pour l'année scolaire marquée "courante" de
    # l'école — voir router.py::list_students. None ailleurs (fiche élève, création, bulk statut) :
    # ces endpoints n'ont pas besoin de cette info, jamais recalculée pour eux inutilement.
    # Défauts explicites : un ORM Student sans cet attribut assigné sérialise simplement à null,
    # jamais une erreur de validation.
    current_class_id: uuid.UUID | None = None
    current_class_name: str | None = None


class StudentCreate(BaseModel):
    school_id: uuid.UUID
    matricule: str = Field(min_length=1, max_length=64)
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    date_of_birth: date
    sex: Sex
    place_of_birth: str | None = None
    address: str | None = None


class StudentUpdate(BaseModel):
    matricule: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    sex: Sex | None = None
    place_of_birth: str | None = None
    address: str | None = None
    status: StudentStatus | None = None
    status_change_reason: str | None = None


# --- Modification en masse (statut uniquement) ---------------------------------
# Les champs individuels (matricule, prénom, nom, date de naissance, sexe) ne sont délibérément
# pas proposés ici : une modification en masse n'a de sens que pour un champ partagé entre
# plusieurs élèves, comme le statut après un import.
class StudentBulkStatusUpdate(BaseModel):
    student_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    status: StudentStatus
    status_change_reason: str | None = Field(default=None, max_length=500)


class StudentBulkUpdateOut(BaseModel):
    updated_count: int
    unchanged_count: int
    students: list[StudentOut]


# --- Affectation en masse à une classe ------------------------------------------
class StudentBulkEnrollmentCreate(BaseModel):
    student_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    academic_year_id: uuid.UUID
    class_id: uuid.UUID
    enrollment_date: date


class StudentBulkEnrollmentOut(BaseModel):
    target_class_id: uuid.UUID
    target_class_name: str
    academic_year_id: uuid.UUID
    capacity: int | None
    active_enrollment_count: int
    # None si la classe n'a pas de capacité définie (aucune limite).
    available_places: int | None
    selected_count: int
    created_count: int
    reassigned_count: int
    unchanged_count: int
    students: list[StudentOut]


# --- Guardians -----------------------------------------------------------------
class GuardianOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    full_name: str
    relationship_type: GuardianRelationship
    phone: str | None
    email: str | None
    address: str | None
    is_emergency_contact: bool
    user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class GuardianCreate(BaseModel):
    school_id: uuid.UUID
    full_name: str = Field(min_length=1, max_length=255)
    relationship_type: GuardianRelationship
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    is_emergency_contact: bool = False


class GuardianUpdate(BaseModel):
    full_name: str | None = None
    relationship_type: GuardianRelationship | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    is_emergency_contact: bool | None = None
    # Lie (ou délie, si None explicite) ce Guardian à un compte utilisateur de rôle PARENT —
    # validation complète (existence, école, rôle, doublon) faite dans le router (Phase 7).
    user_id: uuid.UUID | None = None


class StudentGuardianOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    guardian_id: uuid.UUID
    is_primary_contact: bool
    created_at: datetime


class StudentGuardianCreate(BaseModel):
    guardian_id: uuid.UUID
    is_primary_contact: bool = False


# --- Enrollments ---------------------------------------------------------------
class StudentEnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    class_id: uuid.UUID
    academic_year_id: uuid.UUID
    enrollment_date: date
    status: EnrollmentStatus
    promotion_type: PromotionType | None = None
    created_at: datetime
    updated_at: datetime


class StudentEnrollmentCreate(BaseModel):
    class_id: uuid.UUID
    enrollment_date: date


class StudentEnrollmentUpdate(BaseModel):
    status: EnrollmentStatus


# --- Réinscription / promotion en masse -----------------------------------------
class ClassMapping(BaseModel):
    source_class_id: uuid.UUID
    target_class_id: uuid.UUID


# Une classe source déclarée en sortie d'établissement (ex. une classe terminale, CM2 dans une
# école qui s'arrête là) — jamais une classe fictive créée pour autant. Une classe source ne doit
# JAMAIS apparaître à la fois dans class_mappings ET exit_dispositions (validé par le service).
class StudentExitDisposition(BaseModel):
    source_class_id: uuid.UUID
    exit_type: ExitType
    reason: str | None = Field(default=None, max_length=500)


class StudentBulkPromotionCreate(BaseModel):
    source_academic_year_id: uuid.UUID
    target_academic_year_id: uuid.UUID
    # Une classe source peut avoir une correspondance (class_mappings) OU être déclarée en sortie
    # (exit_dispositions) — ni l'un ni l'autre n'est requis seul : une école qui ne fait QUE
    # déclarer des sorties (toutes ses classes sont terminales) a class_mappings vide, légitime.
    class_mappings: list[ClassMapping] = Field(default_factory=list, max_length=200)
    exit_dispositions: list[StudentExitDisposition] = Field(default_factory=list, max_length=200)
    student_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    enrollment_date: date


class TargetClassPreview(BaseModel):
    target_class_id: uuid.UUID
    target_class_name: str
    capacity: int | None
    active_enrollment_count: int
    incoming_count: int
    # None si la classe n'a pas de capacité définie (aucune limite).
    available_places: int | None


class StudentBulkPromotionOut(BaseModel):
    source_academic_year_id: uuid.UUID
    target_academic_year_id: uuid.UUID
    selected_count: int
    promoted_count: int
    repeated_count: int
    already_enrolled_count: int
    # Conservé pour compatibilité : total des élèves dont la classe source n'a aucune
    # correspondance dans class_mappings, QU'ILS AIENT ou non une disposition de sortie —
    # équivaut toujours à exit_count + unprocessed_no_target_class_count.
    no_target_class_count: int
    exit_count: int
    # Sous-ensemble de no_target_class_count : ni classe cible, ni disposition de sortie déclarée
    # — ces élèves doivent être explicitement traités avant de pouvoir confirmer (voir
    # service.py::bulk_promote_students, bloquant sur l'appel réel si non vide).
    unprocessed_no_target_class_count: int
    exit_counts_by_type: dict[str, int]
    class_previews: list[TargetClassPreview]
    # Erreurs métier bloquantes (capacité insuffisante, élèves non traités...) — non vide implique
    # qu'AUCUNE mutation n'a eu lieu, dry_run ou non (voir service.py::bulk_promote_students).
    blocking_errors: list[str]
    students: list[StudentOut]


class StudentExitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    academic_year_id: uuid.UUID
    exit_type: ExitType
    reason: str | None
    exit_date: date
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


# --- Documents -------------------------------------------------------------------
class StudentDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    document_type: str
    file_path: str
    original_filename: str
    mime_type: str | None
    file_size: int | None
    uploaded_by: uuid.UUID | None
    created_at: datetime


# --- Import CSV/Excel -------------------------------------------------------------
class StudentImportRowError(BaseModel):
    row: int
    reason: str


class StudentImportReport(BaseModel):
    total_rows: int
    created: int
    duplicates_skipped: int
    errors: list[StudentImportRowError]
