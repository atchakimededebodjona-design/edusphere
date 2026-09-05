import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from html import escape as html_escape

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import send_email_best_effort
from app.core.payment import payment_provider
from app.core.storage import storage
from app.modules.academics.models import SchoolClass
from app.modules.fees.models import FeeSchedule, Payment, PaymentAllocation, StudentFee
from app.modules.fees.schemas import (
    FeeScheduleGenerateResult,
    FinancialSummaryOut,
    FeesSummaryOut,
    PaymentCreate,
    StudentFeeBalanceOut,
    StudentFeeOut,
)
from app.modules.report_cards.service import html_to_pdf
from app.modules.schools.models import School
from app.modules.students.models import Guardian, Student, StudentEnrollment, StudentGuardian

# --- Génération des obligations financières ------------------------------------------------


async def generate_student_fees(db: AsyncSession, schedule: FeeSchedule) -> FeeScheduleGenerateResult:
    """Affecte `schedule` à chaque élève actif dans sa portée (école/classe/niveau), pour son
    année académique — jamais automatiquement à l'inscription, uniquement sur cette action
    explicite (voir PHASE_19_DISCOVERY.md §15). Idempotent : un élève déjà affecté (contrainte
    unique student_id+fee_schedule_id) n'est jamais dupliqué."""
    enrollment_stmt = select(StudentEnrollment.student_id).where(
        StudentEnrollment.academic_year_id == schedule.academic_year_id,
        StudentEnrollment.status == "ACTIVE",
    )
    if schedule.scope_type == "CLASS":
        enrollment_stmt = enrollment_stmt.where(StudentEnrollment.class_id == schedule.scope_class_id)
    elif schedule.scope_type == "LEVEL":
        enrollment_stmt = enrollment_stmt.join(SchoolClass, SchoolClass.id == StudentEnrollment.class_id).where(
            SchoolClass.education_level_id == schedule.scope_education_level_id
        )

    result = await db.execute(enrollment_stmt)
    target_student_ids = {row[0] for row in result.all()}

    existing_result = await db.execute(select(StudentFee.student_id).where(StudentFee.fee_schedule_id == schedule.id))
    already_assigned = {row[0] for row in existing_result.all()}

    to_create = target_student_ids - already_assigned
    for student_id in to_create:
        db.add(
            StudentFee(
                id=uuid.uuid4(),
                school_id=schedule.school_id,
                organization_id=schedule.organization_id,
                student_id=student_id,
                fee_schedule_id=schedule.id,
                amount_due=schedule.amount,
                due_date=schedule.due_date,
                status="PENDING",
            )
        )

    await db.flush()
    await db.commit()
    return FeeScheduleGenerateResult(
        created_count=len(to_create), skipped_existing_count=len(target_student_ids & already_assigned)
    )


# --- Soldes ---------------------------------------------------------------------------------


async def _allocations_by_fee(db: AsyncSession, fee_ids: list[uuid.UUID]) -> dict[uuid.UUID, Decimal]:
    """Somme groupée en une seule requête (pas de N+1, voir consigne Phase 19 §26) des
    allocations actives (paiement non annulé) par `StudentFee`."""
    if not fee_ids:
        return {}
    result = await db.execute(
        select(PaymentAllocation.student_fee_id, func.sum(PaymentAllocation.amount))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(PaymentAllocation.student_fee_id.in_(fee_ids), Payment.status == "COMPLETED")
        .group_by(PaymentAllocation.student_fee_id)
    )
    return {row[0]: Decimal(row[1]) for row in result.all()}


async def _sum_active_allocations(db: AsyncSession, student_fee_id: uuid.UUID) -> Decimal:
    by_fee = await _allocations_by_fee(db, [student_fee_id])
    return by_fee.get(student_fee_id, Decimal("0"))


async def compute_financial_summary(db: AsyncSession, student: Student) -> FinancialSummaryOut:
    result = await db.execute(
        select(StudentFee, FeeSchedule.name)
        .join(FeeSchedule, FeeSchedule.id == StudentFee.fee_schedule_id)
        .where(StudentFee.student_id == student.id, StudentFee.status != "CANCELLED")
        .order_by(StudentFee.due_date.asc().nulls_last())
    )
    rows = result.all()
    paid_by_fee = await _allocations_by_fee(db, [row[0].id for row in rows])

    fee_outs: list[StudentFeeBalanceOut] = []
    total_due = Decimal("0")
    total_paid = Decimal("0")
    for student_fee, schedule_name in rows:
        paid = paid_by_fee.get(student_fee.id, Decimal("0"))
        total_due += student_fee.amount_due
        total_paid += paid
        fee_outs.append(
            StudentFeeBalanceOut(
                **StudentFeeOut.model_validate(student_fee).model_dump(),
                fee_schedule_name=schedule_name,
                amount_paid=paid,
                balance=student_fee.amount_due - paid,
            )
        )

    return FinancialSummaryOut(
        student_id=student.id, total_due=total_due, total_paid=total_paid, balance=total_due - total_paid, fees=fee_outs
    )


async def compute_fees_summary(
    db: AsyncSession, school_id: uuid.UUID, academic_year_id: uuid.UUID | None
) -> FeesSummaryOut:
    stmt = (
        select(StudentFee)
        .join(FeeSchedule, FeeSchedule.id == StudentFee.fee_schedule_id)
        .where(StudentFee.school_id == school_id, StudentFee.status != "CANCELLED")
    )
    if academic_year_id is not None:
        stmt = stmt.where(FeeSchedule.academic_year_id == academic_year_id)
    result = await db.execute(stmt)
    fees = list(result.scalars().all())

    paid_by_fee = await _allocations_by_fee(db, [fee.id for fee in fees])
    total_due = sum((fee.amount_due for fee in fees), start=Decimal("0"))
    total_paid = sum((paid_by_fee.get(fee.id, Decimal("0")) for fee in fees), start=Decimal("0"))
    today = date.today()
    overdue_count = sum(
        1 for fee in fees if fee.status != "PAID" and fee.due_date is not None and fee.due_date < today
    )

    return FeesSummaryOut(total_due=total_due, total_paid=total_paid, balance=total_due - total_paid, overdue_count=overdue_count)


async def _refresh_student_fee_status(db: AsyncSession, student_fee: StudentFee) -> None:
    paid = await _sum_active_allocations(db, student_fee.id)
    if paid <= 0:
        student_fee.status = "PENDING"
    elif paid < student_fee.amount_due:
        student_fee.status = "PARTIALLY_PAID"
    else:
        student_fee.status = "PAID"
    await db.flush()


# --- Paiements --------------------------------------------------------------------------------


async def record_payment(
    db: AsyncSession, student: Student, payload: PaymentCreate, recorded_by: uuid.UUID
) -> tuple[Payment, list[tuple[str, str, str]]]:
    """Enregistre un paiement manuel et ses allocations, dans une seule transaction verrouillée.

    Idempotence : une resoumission avec la même `idempotency_key` renvoie le paiement déjà créé
    (double-clic/double-soumission, voir PHASE_19_DISCOVERY.md §20) au lieu d'en créer un second.

    Concurrence : les `StudentFee` ciblées sont verrouillées (`SELECT ... FOR UPDATE`, triées par
    id pour éviter tout deadlock entre deux paiements multi-frais concurrents) avant de lire le
    montant déjà alloué — deux administrateurs enregistrant un paiement sur la même obligation au
    même instant sont ainsi sérialisés par Postgres, jamais une simple lecture non protégée.
    """
    existing = await db.execute(
        select(Payment).where(Payment.school_id == student.school_id, Payment.idempotency_key == payload.idempotency_key)
    )
    existing_payment = existing.scalar_one_or_none()
    if existing_payment is not None:
        return existing_payment, []

    allocation_total = sum((a.amount for a in payload.allocations), start=Decimal("0"))
    if allocation_total != payload.amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The sum of allocations must exactly equal the payment amount",
        )

    allocation_amounts: dict[uuid.UUID, Decimal] = {}
    for alloc in payload.allocations:
        allocation_amounts[alloc.student_fee_id] = allocation_amounts.get(alloc.student_fee_id, Decimal("0")) + alloc.amount

    fee_ids = sorted(allocation_amounts.keys(), key=str)
    lock_result = await db.execute(select(StudentFee).where(StudentFee.id.in_(fee_ids)).with_for_update())
    student_fees_by_id = {row.id: row for row in lock_result.scalars().all()}

    if len(student_fees_by_id) != len(fee_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more fees were not found")

    for fee_id in fee_ids:
        fee = student_fees_by_id[fee_id]
        if fee.student_id != student.id or fee.school_id != student.school_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more fees were not found")
        if fee.status == "CANCELLED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=f"Fee {fee_id} is cancelled and cannot receive payments"
            )

    for fee_id, amount in allocation_amounts.items():
        fee = student_fees_by_id[fee_id]
        already_paid = await _sum_active_allocations(db, fee_id)
        if already_paid + amount > fee.amount_due:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Payment allocation exceeds the remaining balance for fee {fee_id}",
            )

    # Acte l'enregistrement via l'abstraction PaymentProvider (Phase 19 — voir app/core/payment.py) :
    # aucun appel réseau pour l'implémentation MANUAL, mais tout paiement passe par ce chemin dès
    # maintenant pour qu'un futur fournisseur réel s'y substitue sans changer ce module.
    await payment_provider.record(payload.amount, payload.method, payload.reference)

    payment_id = uuid.uuid4()
    payment = Payment(
        id=payment_id,
        school_id=student.school_id,
        organization_id=student.organization_id,
        student_id=student.id,
        idempotency_key=payload.idempotency_key,
        amount=payload.amount,
        method=payload.method,
        paid_at=payload.paid_at,
        reference=payload.reference,
        payer_name=payload.payer_name,
        note=payload.note,
        recorded_by=recorded_by,
        status="COMPLETED",
        receipt_number=f"RCPT-{payment_id.hex[:10].upper()}",
    )
    db.add(payment)

    for fee_id, amount in allocation_amounts.items():
        db.add(
            PaymentAllocation(
                id=uuid.uuid4(),
                school_id=student.school_id,
                organization_id=student.organization_id,
                payment_id=payment_id,
                student_fee_id=fee_id,
                amount=amount,
            )
        )

    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        # Un autre paiement avec la même idempotency_key a gagné la course entre le contrôle
        # ci-dessus et ce flush (double soumission réellement concurrente) : on renvoie son
        # résultat, jamais une erreur, pour rester idempotent.
        retry = await db.execute(
            select(Payment).where(
                Payment.school_id == student.school_id, Payment.idempotency_key == payload.idempotency_key
            )
        )
        winner = retry.scalar_one_or_none()
        if winner is not None:
            return winner, []
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Could not record payment") from exc

    for fee_id in allocation_amounts:
        await _refresh_student_fee_status(db, student_fees_by_id[fee_id])

    schedule_rows = await db.execute(
        select(StudentFee.id, FeeSchedule.name)
        .join(FeeSchedule, FeeSchedule.id == StudentFee.fee_schedule_id)
        .where(StudentFee.id.in_(fee_ids))
    )
    schedule_names = {row[0]: row[1] for row in schedule_rows.all()}
    allocation_lines = [(schedule_names[fee_id], amount) for fee_id, amount in allocation_amounts.items()]

    balance_after = await compute_financial_summary(db, student)
    school = await db.get(School, student.school_id)
    assert school is not None

    pdf_bytes = html_to_pdf(_render_receipt_html(school, student, payment, allocation_lines, balance_after.balance))
    pdf_path = f"receipts/{student.school_id}/{payment_id.hex}.pdf"
    await storage.upload(pdf_path, pdf_bytes)
    payment.pdf_path = pdf_path
    await db.flush()

    # Lecture des destinataires AVANT le commit — le contexte RLS (SET LOCAL) est lié à la
    # transaction courante, comme documenté dans report_cards/service.py.
    notifications = await _prepare_payment_notifications(db, student, payment)

    await db.refresh(payment)
    await db.commit()
    return payment, notifications


async def cancel_payment(db: AsyncSession, payment: Payment, cancelled_by: uuid.UUID, reason: str) -> Payment:
    """Annule un paiement `COMPLETED` — ne le modifie ni ne le supprime jamais physiquement
    (intégrité de l'historique financier, voir PHASE_19_DISCOVERY.md §18). Une correction réelle
    passe par un nouveau paiement, jamais par une réécriture de celui-ci."""
    locked = await db.execute(select(Payment).where(Payment.id == payment.id).with_for_update())
    payment = locked.scalar_one()
    if payment.status != "COMPLETED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a completed payment can be cancelled")

    payment.status = "CANCELLED"
    payment.cancelled_at = datetime.now(timezone.utc)
    payment.cancelled_by = cancelled_by
    payment.cancellation_reason = reason
    await db.flush()

    allocations_result = await db.execute(select(PaymentAllocation).where(PaymentAllocation.payment_id == payment.id))
    fee_ids = sorted({row.student_fee_id for row in allocations_result.scalars().all()}, key=str)
    fees_result = await db.execute(select(StudentFee).where(StudentFee.id.in_(fee_ids)).with_for_update())
    for fee in fees_result.scalars().all():
        await _refresh_student_fee_status(db, fee)

    await db.refresh(payment)
    await db.commit()
    return payment


# --- Reçu (PDF) -------------------------------------------------------------------------------


def _render_receipt_html(
    school: School,
    student: Student,
    payment: Payment,
    allocation_lines: list[tuple[str, Decimal]],
    balance_after: Decimal,
) -> str:
    """Pas de moteur de template Jinja2 dédié ici (contrairement à report_cards) : le contenu
    n'est jamais fourni par un utilisateur, seulement des valeurs internes déjà validées — un
    simple gabarit HTML échappé (`html.escape`) suffit et évite une seconde surface de rendu à
    maintenir. `html_to_pdf` (report_cards/service.py) est réutilisé tel quel."""
    rows = "".join(
        f"<tr><td>{html_escape(name)}</td><td style='text-align:right'>{amount}</td></tr>"
        for name, amount in allocation_lines
    )
    return f"""
    <html>
      <body style="font-family: Helvetica, Arial, sans-serif; font-size: 12pt;">
        <h2>{html_escape(school.name)}</h2>
        <p><strong>Reçu n° {html_escape(payment.receipt_number)}</strong></p>
        <p>Élève : {html_escape(student.first_name)} {html_escape(student.last_name)} ({html_escape(student.matricule)})</p>
        <p>Date de paiement : {payment.paid_at.isoformat()}</p>
        <p>Méthode : {html_escape(payment.method)}</p>
        <p>Référence : {html_escape(payment.reference or '—')}</p>
        <p>Payeur : {html_escape(payment.payer_name or '—')}</p>
        <table border="1" cellpadding="4" cellspacing="0" style="border-collapse: collapse; width: 100%;">
          <thead><tr><th style="text-align:left">Frais</th><th style="text-align:right">Montant</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
        <p><strong>Montant total payé : {payment.amount} {school.currency}</strong></p>
        <p>Solde restant après ce paiement (tous frais confondus) : {balance_after} {school.currency}</p>
      </body>
    </html>
    """


# --- Notifications (best-effort, motif identique à report_cards) ------------------------------


async def _prepare_payment_notifications(db: AsyncSession, student: Student, payment: Payment) -> list[tuple[str, str, str]]:
    """Contenu volontairement minimal : jamais de lien cliquable vers le reçu — aucune vue web
    parent n'existe dans ce dépôt (parent = mobile uniquement) et aucun schéma de lien profond
    mobile n'est établi ; inventer l'un ou l'autre pour cette phase créerait une nouvelle surface
    non éprouvée. Le canal sécurisé réel est l'application mobile authentifiée elle-même — motif
    identique à la notification de publication de bulletin (report_cards/service.py)."""
    result = await db.execute(
        select(Guardian.full_name, Guardian.email)
        .join(StudentGuardian, StudentGuardian.guardian_id == Guardian.id)
        .where(
            StudentGuardian.student_id == student.id,
            StudentGuardian.school_id == student.school_id,
            Guardian.email.isnot(None),
        )
    )
    subject = f"Reçu de paiement — {student.first_name} {student.last_name}"
    return [
        (
            email,
            subject,
            f"Bonjour {full_name},\n\n"
            f"Un paiement de {payment.amount} a été enregistré pour {student.first_name} "
            f"{student.last_name} (reçu n° {payment.receipt_number}).\n\n"
            "Connectez-vous à l'application mobile EduSphere pour consulter le reçu et le solde "
            "à jour.\n\n"
            "— EduSphere",
        )
        for full_name, email in result.all()
        if email is not None
    ]


async def send_payment_notifications(notifications: list[tuple[str, str, str]]) -> None:
    for to, subject, body in notifications:
        await send_email_best_effort(to, subject, body)
