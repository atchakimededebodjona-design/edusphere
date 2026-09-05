import base64
import io
import uuid
from datetime import datetime, timezone

import qrcode
from jinja2 import select_autoescape
from jinja2.sandbox import ImmutableSandboxedEnvironment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from xhtml2pdf import pisa

from app.core.config import settings
from app.core.email import send_email_best_effort
from app.core.security import generate_opaque_token
from app.core.storage import storage
from app.core.tenancy import set_platform_wide_context
from app.modules.academics.models import AcademicTerm, ClassSubject, SchoolClass, Subject
from app.modules.grades.models import StudentSubjectAverage, StudentTermAverage
from app.modules.report_cards.models import ReportCard, ReportCardTemplate
from app.modules.schools.models import School
from app.modules.students.models import Guardian, Student, StudentEnrollment, StudentGuardian

# SandboxedEnvironment (Phase 7.2 — correction SSTI) : le contenu d'un ReportCardTemplate est
# entièrement contrôlé par SCHOOL_ADMIN/DIRECTOR (school_id/organization_id-scopé, mais pas
# du code de confiance plateforme) et rendu comme template Jinja2, pas seulement comme données.
# Un Environment standard donne accès à l'intégralité du graphe d'objets Python via les attributs
# dunder (__class__, __globals__, __mro__...) — confirmé exploitable par une PoC non destructive
# avant cette correction. SandboxedEnvironment bloque l'accès aux attributs "unsafe" (préfixés
# `_`) par une liste blanche (pas une blacklist de mots-clés) ; ImmutableSandboxedEnvironment
# ajoute l'interdiction de muter les objets passés en contexte. Aucune variable métier légitime
# ({{ student.first_name }}, {% for s in subjects %}, etc.) n'accède à un attribut dunder — le
# rendu des bulletins existants n'est pas affecté (vérifié après correction).
_jinja_env = ImmutableSandboxedEnvironment(autoescape=select_autoescape(["html"]))


def render_template(html_content: str, context: dict) -> str:
    template = _jinja_env.from_string(html_content)
    return template.render(**context)


def html_to_pdf(html: str) -> bytes:
    buffer = io.BytesIO()
    result = pisa.CreatePDF(src=html, dest=buffer)
    if result.err:
        raise RuntimeError("Failed to render report card PDF from template")
    return buffer.getvalue()


def _qr_data_uri(data: str) -> str:
    img = qrcode.make(data)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


async def _build_context(
    db: AsyncSession,
    school: School,
    student: Student,
    school_class: SchoolClass,
    term: AcademicTerm,
    general_average: float | None,
    general_rank: int | None,
    verification_code: str,
) -> dict:
    logo_data_uri = None
    if school.logo_path:
        content = await storage.download(school.logo_path)
        logo_data_uri = f"data:image/png;base64,{base64.b64encode(content).decode('ascii')}"

    result = await db.execute(
        select(StudentSubjectAverage, ClassSubject, Subject)
        .join(ClassSubject, ClassSubject.id == StudentSubjectAverage.class_subject_id)
        .join(Subject, Subject.id == ClassSubject.subject_id)
        .where(StudentSubjectAverage.student_id == student.id, StudentSubjectAverage.academic_term_id == term.id)
        .order_by(Subject.name)
    )
    subjects = [
        {
            "name": subject.name,
            "coefficient": float(class_subject.coefficient),
            "average": float(average.average) if average.average is not None else None,
            "rank": average.rank,
            "appreciation": average.appreciation,
        }
        for average, class_subject, subject in result.all()
    ]

    verify_url = f"{settings.public_web_base_url}/verify/{verification_code}"

    return {
        "school": {"name": school.name, "logo_data_uri": logo_data_uri},
        "student": {
            "first_name": student.first_name,
            "last_name": student.last_name,
            "matricule": student.matricule,
        },
        "school_class": {"name": school_class.name},
        "academic_term": {"name": term.name},
        "subjects": subjects,
        "general_average": general_average,
        "general_rank": general_rank,
        "qr_code_data_uri": _qr_data_uri(verify_url),
        "generated_at": datetime.now(timezone.utc),
    }


async def generate_report_cards_for_class(
    db: AsyncSession,
    school_class: SchoolClass,
    term: AcademicTerm,
    template: ReportCardTemplate,
    generated_by: uuid.UUID,
) -> list[ReportCard]:
    """Génère (ou régénère) un bulletin PDF pour chaque élève inscrit et actif dans cette
    classe, pour cette période. Une régénération repasse le bulletin en DRAFT (une version déjà
    publiée doit être revalidée avant republication) et écrase le PDF précédent."""
    enrollment_result = await db.execute(
        select(StudentEnrollment).where(
            StudentEnrollment.class_id == school_class.id, StudentEnrollment.status == "ACTIVE"
        )
    )
    enrollments = list(enrollment_result.scalars().all())

    school = await db.get(School, school_class.school_id)
    assert school is not None

    report_cards: list[ReportCard] = []

    for enrollment in enrollments:
        student = await db.get(Student, enrollment.student_id)
        assert student is not None

        term_average_result = await db.execute(
            select(StudentTermAverage).where(
                StudentTermAverage.student_id == student.id, StudentTermAverage.academic_term_id == term.id
            )
        )
        term_average = term_average_result.scalar_one_or_none()
        general_average = float(term_average.average) if term_average and term_average.average is not None else None
        general_rank = term_average.rank if term_average else None

        existing_result = await db.execute(
            select(ReportCard).where(ReportCard.student_id == student.id, ReportCard.academic_term_id == term.id)
        )
        existing = existing_result.scalar_one_or_none()
        verification_code = existing.verification_code if existing else generate_opaque_token()

        context = await _build_context(
            db, school, student, school_class, term, general_average, general_rank, verification_code
        )
        html = render_template(template.html_content, context)
        pdf_bytes = html_to_pdf(html)

        pdf_path = f"report_cards/{student.id}/{term.id}/{uuid.uuid4().hex}.pdf"
        await storage.upload(pdf_path, pdf_bytes)

        if existing:
            existing.template_id = template.id
            existing.pdf_path = pdf_path
            existing.general_average = general_average
            existing.general_rank = general_rank
            existing.status = "DRAFT"
            existing.published_at = None
            existing.generated_at = datetime.now(timezone.utc)
            existing.generated_by = generated_by
            row = existing
        else:
            row = ReportCard(
                id=uuid.uuid4(),
                school_id=school_class.school_id,
                organization_id=school_class.organization_id,
                student_id=student.id,
                class_id=school_class.id,
                academic_term_id=term.id,
                template_id=template.id,
                status="DRAFT",
                verification_code=verification_code,
                pdf_path=pdf_path,
                general_average=general_average,
                general_rank=general_rank,
                generated_by=generated_by,
            )
            db.add(row)

        report_cards.append(row)

    await db.flush()
    for row in report_cards:
        await db.refresh(row)
    await db.commit()
    return report_cards


async def prepare_report_card_published_notifications(db: AsyncSession, report_card: ReportCard) -> list[tuple[str, str, str]]:
    """Notification email (Phase 11) — étape de LECTURE, à appeler AVANT le commit final de la
    publication (voir report_cards/router.py::publish_report_card), jamais après : le contexte
    RLS (SET LOCAL) est lié à la transaction courante et expire au commit — exactement le même
    piège déjà documenté ailleurs dans ce projet (ex. auth/service.py::register, "refresh() AVANT
    commit"). Après le commit, une nouvelle requête ici ne verrait plus aucune ligne.

    Retourne les emails prêts à envoyer `(destinataire, sujet, corps)` — l'envoi réel
    (`send_email_best_effort`, pur réseau, pas d'accès DB) peut ensuite se faire en toute
    sécurité APRÈS le commit, sans jamais risquer de bloquer ou faire échouer la publication.

    Contenu volontairement minimal — jamais de note, moyenne, classement ni appréciation dans
    l'email : le parent doit consulter le bulletin dans l'application, pas dans sa boîte mail
    (canal non chiffré de bout en bout, hors du contrôle d'EduSphere une fois envoyé).

    Tuteurs recherchés uniquement via `StudentGuardian.student_id` + `school_id` du bulletin
    (jamais de recherche globale de guardians) — cohérent avec l'isolation tenant déjà en place
    partout ailleurs dans ce module."""
    student = await db.get(Student, report_card.student_id)
    term = await db.get(AcademicTerm, report_card.academic_term_id)
    if student is None or term is None:
        return []

    result = await db.execute(
        select(Guardian.full_name, Guardian.email)
        .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
        .where(
            StudentGuardian.student_id == report_card.student_id,
            StudentGuardian.school_id == report_card.school_id,
            Guardian.email.isnot(None),
        )
    )

    subject = f"Bulletin disponible — {student.first_name} {student.last_name}"
    return [
        (
            email,
            subject,
            f"Bonjour {full_name},\n\n"
            f"Le bulletin de {student.first_name} {student.last_name} pour la période "
            f"{term.name} vient d'être publié.\n\n"
            "Connectez-vous à l'application mobile EduSphere pour le consulter.\n\n"
            "— EduSphere",
        )
        for full_name, email in result.all()
        if email is not None
    ]


async def send_report_card_published_notifications(notifications: list[tuple[str, str, str]]) -> None:
    """Étape d'ENVOI — pur réseau, aucun accès DB, à appeler APRÈS le commit (voir
    `prepare_report_card_published_notifications`). Best-effort : `send_email_best_effort` ne
    lève jamais, un échec d'envoi n'affecte donc jamais l'appelant."""
    for to, subject, body in notifications:
        await send_email_best_effort(to, subject, body)


async def get_report_card_by_verification_code(db: AsyncSession, code: str) -> ReportCard | None:
    """Endpoint public (pas d'utilisateur authentifié) : le code aléatoire non-devinable EST
    l'autorisation, comme un lien de partage — bypass RLS explicite et légitime."""
    await set_platform_wide_context(db)
    result = await db.execute(select(ReportCard).where(ReportCard.verification_code == code))
    return result.scalar_one_or_none()
