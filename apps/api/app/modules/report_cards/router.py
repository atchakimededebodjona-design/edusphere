import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CurrentUser, DbSession, ensure_permission
from app.core.rate_limit import ensure_report_card_verify_not_rate_limited, register_report_card_verify_attempt
from app.core.storage import storage
from app.modules.academics.models import AcademicTerm, SchoolClass
from app.modules.report_cards import service
from app.modules.report_cards.models import ReportCard, ReportCardTemplate
from app.modules.report_cards.schemas import (
    ReportCardGenerateRequest,
    ReportCardOut,
    ReportCardTemplateCreate,
    ReportCardTemplateOut,
    ReportCardVerifyOut,
)
from app.modules.schools.models import School
from app.modules.students.models import Student

router = APIRouter()


# --- Helpers -----------------------------------------------------------------
async def _get_school_or_404(db: AsyncSession, school_id: uuid.UUID) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    return school


async def _get_class_or_404(db: AsyncSession, class_id: uuid.UUID) -> SchoolClass:
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    return school_class


async def _get_report_card_or_404(db: AsyncSession, report_card_id: uuid.UUID) -> ReportCard:
    report_card = await db.get(ReportCard, report_card_id)
    if report_card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report card not found")
    return report_card


# --- Templates -----------------------------------------------------------------
@router.get("/report-card-templates", response_model=list[ReportCardTemplateOut])
async def list_templates(
    db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)
) -> list[ReportCardTemplate]:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(
        db, current_user, "report_cards.read", organization_id=school.organization_id, school_id=school.id
    )
    result = await db.execute(
        select(ReportCardTemplate).where(ReportCardTemplate.school_id == school_id).order_by(ReportCardTemplate.name)
    )
    return list(result.scalars().all())


@router.post("/report-card-templates", response_model=ReportCardTemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: ReportCardTemplateCreate, db: DbSession, current_user: CurrentUser
) -> ReportCardTemplate:
    school = await _get_school_or_404(db, payload.school_id)
    await ensure_permission(
        db, current_user, "report_cards.manage", organization_id=school.organization_id, school_id=school.id
    )

    template = ReportCardTemplate(
        id=uuid.uuid4(),
        school_id=school.id,
        organization_id=school.organization_id,
        name=payload.name,
        html_content=payload.html_content,
        is_default=payload.is_default,
    )
    db.add(template)
    try:
        await db.flush()
        await db.refresh(template)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A template with this name already exists"
        ) from exc
    return template


# --- Report cards --------------------------------------------------------------
@router.post("/report-cards/generate", response_model=list[ReportCardOut])
async def generate_report_cards(
    payload: ReportCardGenerateRequest, db: DbSession, current_user: CurrentUser
) -> list[ReportCard]:
    school_class = await _get_class_or_404(db, payload.class_id)
    await ensure_permission(
        db,
        current_user,
        "report_cards.manage",
        organization_id=school_class.organization_id,
        school_id=school_class.school_id,
    )

    term = await db.get(AcademicTerm, payload.academic_term_id)
    if term is None or term.school_id != school_class.school_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Academic term does not belong to this school")

    template = await db.get(ReportCardTemplate, payload.template_id)
    if template is None or template.school_id != school_class.school_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Template does not belong to this school")

    return await service.generate_report_cards_for_class(db, school_class, term, template, current_user.id)


@router.get("/report-cards", response_model=list[ReportCardOut])
async def list_report_cards(
    db: DbSession,
    current_user: CurrentUser,
    class_id: uuid.UUID = Query(...),
    academic_term_id: uuid.UUID = Query(...),
) -> list[ReportCard]:
    school_class = await _get_class_or_404(db, class_id)
    await ensure_permission(
        db, current_user, "report_cards.read", organization_id=school_class.organization_id, school_id=school_class.school_id
    )
    result = await db.execute(
        select(ReportCard).where(ReportCard.class_id == class_id, ReportCard.academic_term_id == academic_term_id)
    )
    return list(result.scalars().all())


@router.get("/report-cards/{report_card_id}", response_model=ReportCardOut)
async def get_report_card(report_card_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> ReportCard:
    report_card = await _get_report_card_or_404(db, report_card_id)
    await ensure_permission(
        db, current_user, "report_cards.read", organization_id=report_card.organization_id, school_id=report_card.school_id
    )
    return report_card


@router.get("/report-cards/{report_card_id}/pdf")
async def download_report_card_pdf(report_card_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> Response:
    report_card = await _get_report_card_or_404(db, report_card_id)
    await ensure_permission(
        db, current_user, "report_cards.read", organization_id=report_card.organization_id, school_id=report_card.school_id
    )

    student = await db.get(Student, report_card.student_id)
    filename = f"bulletin_{student.matricule if student else report_card.id}.pdf"

    content = await storage.download(report_card.pdf_path)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/report-cards/{report_card_id}/publish", response_model=ReportCardOut)
async def publish_report_card(report_card_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> ReportCard:
    report_card = await _get_report_card_or_404(db, report_card_id)
    await ensure_permission(
        db, current_user, "report_cards.manage", organization_id=report_card.organization_id, school_id=report_card.school_id
    )

    # Phase 11 — évite un envoi dupliqué si /publish est appelé plusieurs fois sur un bulletin
    # déjà publié (double-clic, nouvel appel accidentel) : réutilise published_at déjà existant
    # comme signal, sans nouvelle table de suivi. Une régénération (generate_report_cards_for_class)
    # remet published_at à None avant republication : ce cas redevient donc un "premier" envoi,
    # ce qui est le comportement voulu (le contenu a changé).
    was_already_published = report_card.published_at is not None

    report_card.status = "PUBLISHED"
    report_card.published_at = datetime.now(timezone.utc)
    await db.flush()
    await db.refresh(report_card)

    # Lecture des destinataires AVANT le commit — le contexte RLS (SET LOCAL) est lié à la
    # transaction courante et ne verrait plus rien après (voir
    # report_cards/service.py::prepare_report_card_published_notifications).
    notifications: list[tuple[str, str, str]] = []
    if not was_already_published:
        notifications = await service.prepare_report_card_published_notifications(db, report_card)

    await db.commit()

    # Envoi réel (pur réseau, best-effort) APRÈS le commit : la publication est déjà durablement
    # enregistrée, un échec d'envoi ne peut plus jamais l'affecter.
    if notifications:
        await service.send_report_card_published_notifications(notifications)

    return report_card


@router.get("/report-cards/verify/{code}", response_model=ReportCardVerifyOut)
async def verify_report_card(code: str, request: Request, db: DbSession) -> ReportCardVerifyOut:
    """Endpoint public (pas d'authentification) — scanné depuis le QR code du bulletin papier.

    Phase 20 — rate limiting par IP (voir app/core/rate_limit.py) : le code a 384 bits d'entropie,
    le brute-force reste infaisable, mais rien ne protégeait auparavant contre un scraping
    automatisé à haut débit de cet endpoint public.
    """
    ip = request.client.host if request.client else None
    await ensure_report_card_verify_not_rate_limited(ip)
    await register_report_card_verify_attempt(ip)

    report_card = await service.get_report_card_by_verification_code(db, code)
    if report_card is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown verification code")

    student = await db.get(Student, report_card.student_id)
    school_class = await db.get(SchoolClass, report_card.class_id)
    term = await db.get(AcademicTerm, report_card.academic_term_id)
    school = await db.get(School, report_card.school_id)
    assert student is not None and school_class is not None and term is not None and school is not None

    return ReportCardVerifyOut(
        school_name=school.name,
        student_full_name=f"{student.first_name} {student.last_name}",
        class_name=school_class.name,
        academic_term_name=term.name,
        general_average=report_card.general_average,
        general_rank=report_card.general_rank,
        status=report_card.status,  # type: ignore[arg-type]
        generated_at=report_card.generated_at,
    )
