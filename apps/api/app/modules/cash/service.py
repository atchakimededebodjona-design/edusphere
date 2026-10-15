"""Caisse scolaire, lot 3 — logique métier des sessions de caisse.

Verrouillage (concurrence) :
- tout ce qui MODIFIE une session (mouvement, comptage, clôture) la verrouille `FOR UPDATE` ;
- un paiement CASH verrouille la session OPEN de son enregistreur `FOR SHARE`
  (`lock_open_session_for_payment`, appelée par fees/service.py::record_payment dans SA transaction).
Une clôture et un paiement concurrents sont donc sérialisés par Postgres : jamais un paiement
rattaché à une session déjà close, jamais une clôture calculée sans un paiement déjà validé.

Solde théorique : voir `expected_amount_sql` (règle unique, documentée aussi dans cash/models.py).
Journée métier : toujours dans le fuseau `School.timezone` (`school_today`, `day_bounds_utc`).
"""

import csv
import io
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, Select, case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import apply_tenant_context
from app.modules.audit import service as audit_service
from app.modules.cash.denominations import denominations_for
from app.modules.cash.models import (
    CASH_MOVEMENT_FIXED_DIRECTIONS,
    CashCount,
    CashCountLine,
    CashMovement,
    CashSession,
)
from app.modules.cash.schemas import (
    CashCountCreate,
    CashCountLineOut,
    CashCountOut,
    CashierReportRowOut,
    CashMovementCreate,
    CashMovementOut,
    CashSessionClose,
    CashSessionDetailOut,
    CashSessionOut,
    CashSessionPaymentOut,
    CashSessionsAggregateOut,
    CashSessionSummaryOut,
    CashTotalsOut,
    PaymentMethodTotalOut,
)
from app.modules.fees.models import Payment
from app.modules.schools.models import School
from app.modules.students.models import Student
from app.modules.users.models import User

ZERO = Decimal("0")
CSV_MAX_ROWS = 10_000
SESSION_LIST_MAX_ROWS = 500


# --- Fuseau horaire de l'école ------------------------------------------------------------------
def school_zone(school: School) -> ZoneInfo:
    try:
        return ZoneInfo(school.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def school_today(school: School, now: datetime | None = None) -> date:
    """Journée métier de l'école — jamais `date.today()` (fuseau du serveur)."""
    return (now or datetime.now(timezone.utc)).astimezone(school_zone(school)).date()


def business_date(school: School, moment: datetime) -> date:
    return moment.astimezone(school_zone(school)).date()


def day_bounds_utc(school: School, date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """[début de `date_from`, début du lendemain de `date_to`[ en heure locale de l'école, en UTC."""
    zone = school_zone(school)
    start = datetime.combine(date_from, time.min, tzinfo=zone).astimezone(timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc)
    return start, end


# --- Agrégats SQL (source unique du solde théorique) -------------------------------------------
def _payments_by_session(school_id: uuid.UUID) -> Any:
    return (
        select(
            Payment.cash_session_id.label("session_id"),
            func.sum(Payment.amount).label("total"),
            func.count(Payment.id).label("count"),
        )
        .where(
            Payment.school_id == school_id,
            Payment.cash_session_id.is_not(None),
            Payment.method == "CASH",
            Payment.status == "COMPLETED",
        )
        .group_by(Payment.cash_session_id)
        .subquery("cash_payments")
    )


def _movements_by_session(school_id: uuid.UUID) -> Any:
    return (
        select(
            CashMovement.cash_session_id.label("session_id"),
            func.sum(case((CashMovement.direction == "IN", CashMovement.amount), else_=ZERO)).label("in_total"),
            func.sum(case((CashMovement.direction == "OUT", CashMovement.amount), else_=ZERO)).label("out_total"),
        )
        .where(CashMovement.school_id == school_id)
        .group_by(CashMovement.cash_session_id)
        .subquery("cash_movements_totals")
    )


@dataclass(frozen=True)
class _SessionAggregates:
    pay: Any
    mov: Any
    cash_total: Any
    cash_count: Any
    in_total: Any
    out_total: Any
    live_expected: Any
    current_expected: Any


def expected_amount_sql(opening: Any, cash_total: Any, in_total: Any, out_total: Any) -> Any:
    """RÈGLE UNIQUE du solde théorique :
    fonds initial + paiements CASH COMPLETED rattachés + mouvements IN − mouvements OUT
    (CASH_OUT, BANK_DEPOSIT et OTHER/OUT). Paiements annulés exclus par `_payments_by_session`."""
    return opening + cash_total + in_total - out_total


def _aggregates(school_id: uuid.UUID) -> _SessionAggregates:
    pay = _payments_by_session(school_id)
    mov = _movements_by_session(school_id)
    cash_total = func.coalesce(pay.c.total, ZERO)
    cash_count = func.coalesce(pay.c.count, 0)
    in_total = func.coalesce(mov.c.in_total, ZERO)
    out_total = func.coalesce(mov.c.out_total, ZERO)
    live_expected = expected_amount_sql(CashSession.opening_amount, cash_total, in_total, out_total)
    # Session close : théorique FIGÉ à la clôture (jamais recalculé) ; ouverte : calcul en direct.
    current_expected = case((CashSession.status == "CLOSED", CashSession.expected_amount), else_=live_expected)
    return _SessionAggregates(pay, mov, cash_total, cash_count, in_total, out_total, live_expected, current_expected)


def _with_aggregates(stmt: Select[Any], agg: _SessionAggregates) -> Select[Any]:
    return stmt.outerjoin(agg.pay, agg.pay.c.session_id == CashSession.id).outerjoin(
        agg.mov, agg.mov.c.session_id == CashSession.id
    )


async def session_totals(db: AsyncSession, session: CashSession) -> CashTotalsOut:
    agg = _aggregates(session.school_id)
    row = (
        await db.execute(
            _with_aggregates(
                select(agg.cash_total, agg.cash_count, agg.in_total, agg.out_total, agg.live_expected).select_from(
                    CashSession
                ),
                agg,
            ).where(CashSession.id == session.id)
        )
    ).one()
    return CashTotalsOut(
        opening_amount=session.opening_amount,
        cash_payments_total=row[0],
        cash_payments_count=row[1],
        movements_in_total=row[2],
        movements_out_total=row[3],
        expected_amount=row[4],
    )


# --- Lecture / verrouillage ----------------------------------------------------------------------
async def get_open_session(db: AsyncSession, school_id: uuid.UUID, user_id: uuid.UUID) -> CashSession | None:
    result = await db.execute(
        select(CashSession).where(
            CashSession.school_id == school_id, CashSession.cashier_user_id == user_id, CashSession.status == "OPEN"
        )
    )
    return result.scalar_one_or_none()


async def lock_open_session_for_payment(db: AsyncSession, school_id: uuid.UUID, user_id: uuid.UUID) -> CashSession | None:
    """Session OPEN de `user_id` dans l'école, verrouillée FOR SHARE jusqu'au commit du paiement."""
    result = await db.execute(
        select(CashSession)
        .where(CashSession.school_id == school_id, CashSession.cashier_user_id == user_id, CashSession.status == "OPEN")
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def lock_session_for_payment_cancellation(db: AsyncSession, session_id: uuid.UUID) -> CashSession:
    """Session d'un paiement en cours d'annulation, verrouillée FOR SHARE jusqu'au commit : même
    mode que l'enregistrement d'un paiement, incompatible avec le FOR UPDATE de `close_session`.
    Fermé par défaut : une session introuvable (ne devrait jamais arriver, FK RESTRICT) refuse."""
    result = await db.execute(
        select(CashSession)
        .where(CashSession.id == session_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cash session of this payment is not accessible")
    return session


async def lock_session(db: AsyncSession, session_id: uuid.UUID) -> CashSession:
    # populate_existing : l'objet a pu être chargé plus tôt dans la requête (contrôle d'accès) ; sans
    # cela, la carte d'identité renverrait l'état d'AVANT le verrou (ex. une clôture concurrente).
    result = await db.execute(
        select(CashSession).where(CashSession.id == session_id).with_for_update().execution_options(populate_existing=True)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cash session not found")
    return session


async def _commit(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Commit, puis contexte tenant ré-appliqué : `set_config(..., is_local=true)` ne vaut que pour
    la transaction (app/core/tenancy.py) — sans cela, toute relecture après commit (réponse de
    l'endpoint) serait filtrée par RLS."""
    await db.commit()
    await apply_tenant_context(db, user_id)


def _ensure_open(session: CashSession) -> None:
    if session.status != "OPEN":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cash session is closed")


async def _user_names(db: AsyncSession, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}
    rows = await db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids)))
    return {row[0]: row[1] for row in rows.all()}


def session_out(school: School, session: CashSession, cashier_name: str | None) -> CashSessionOut:
    return CashSessionOut.model_validate(
        {
            **{column: getattr(session, column) for column in CashSessionOut.model_fields if hasattr(session, column)},
            "cashier_name": cashier_name,
            "business_date": business_date(school, session.opened_at),
        }
    )


async def session_detail(db: AsyncSession, school: School, session: CashSession) -> CashSessionDetailOut:
    totals = await session_totals(db, session)
    payment_rows = await db.execute(
        select(Payment, Student.matricule, Student.first_name, Student.last_name)
        .join(Student, Student.id == Payment.student_id)
        .where(Payment.school_id == session.school_id, Payment.cash_session_id == session.id)
        .order_by(Payment.created_at.desc())
    )
    payments = [
        CashSessionPaymentOut.model_validate(
            {
                "id": payment.id,
                "receipt_number": payment.receipt_number,
                "amount": payment.amount,
                "method": payment.method,
                "status": payment.status,
                "paid_at": payment.paid_at,
                "created_at": payment.created_at,
                "student_id": payment.student_id,
                "student_matricule": matricule,
                "student_first_name": first_name,
                "student_last_name": last_name,
            }
        )
        for payment, matricule, first_name, last_name in payment_rows.all()
    ]
    movements = (
        await db.execute(
            select(CashMovement)
            .where(CashMovement.school_id == session.school_id, CashMovement.cash_session_id == session.id)
            .order_by(CashMovement.created_at.desc())
        )
    ).scalars().all()
    latest = await latest_count(db, session)
    names = await _user_names(db, {session.cashier_user_id})
    return CashSessionDetailOut.model_validate(
        {
            "session": session_out(school, session, names.get(session.cashier_user_id)),
            "totals": totals,
            "payments": payments,
            "movements": [CashMovementOut.model_validate(movement) for movement in movements],
            "latest_count": await count_out(db, latest) if latest is not None else None,
            "currency": school.currency,
        }
    )


async def latest_count(db: AsyncSession, session: CashSession) -> CashCount | None:
    result = await db.execute(
        select(CashCount)
        .where(CashCount.school_id == session.school_id, CashCount.cash_session_id == session.id)
        .order_by(CashCount.counted_at.desc(), CashCount.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def count_out(db: AsyncSession, count: CashCount) -> CashCountOut:
    lines = (
        await db.execute(
            select(CashCountLine)
            .where(CashCountLine.school_id == count.school_id, CashCountLine.cash_count_id == count.id)
            .order_by(CashCountLine.denomination.desc())
        )
    ).scalars().all()
    return CashCountOut(
        id=count.id,
        cash_session_id=count.cash_session_id,
        counted_by=count.counted_by,
        counted_at=count.counted_at,
        total_amount=count.total_amount,
        lines=[CashCountLineOut.model_validate(line) for line in lines],
    )


# --- Mutations -----------------------------------------------------------------------------------
async def open_session(db: AsyncSession, school: School, user_id: uuid.UUID, opening_amount: Decimal) -> CashSession:
    if await get_open_session(db, school.id, user_id) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A cash session is already open")
    session = CashSession(
        id=uuid.uuid4(),
        school_id=school.id,
        organization_id=school.organization_id,
        cashier_user_id=user_id,
        opened_by=user_id,
        opening_amount=opening_amount,
        status="OPEN",
    )
    db.add(session)
    try:
        await db.flush()
    except IntegrityError as exc:
        # Deux ouvertures concurrentes : l'index unique partiel `uq_cash_sessions_open_per_cashier`
        # ne laisse passer que la première.
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A cash session is already open") from exc
    await audit_service.record_audit_event(
        db,
        school_id=school.id,
        organization_id=school.organization_id,
        actor_user_id=user_id,
        action=audit_service.ACTION_CASH_SESSION_OPENED,
        entity_type=audit_service.ENTITY_CASH_SESSION,
        entity_id=session.id,
        summary=f"Caisse ouverte avec un fonds initial de {opening_amount} {school.currency}",
        metadata={"opening_amount": str(opening_amount)},
    )
    await _commit(db, user_id)
    await db.refresh(session)
    return session


async def add_movement(
    db: AsyncSession, school: School, session_id: uuid.UUID, user_id: uuid.UUID, payload: CashMovementCreate
) -> CashMovement:
    session = await lock_session(db, session_id)
    existing = (
        await db.execute(
            select(CashMovement).where(
                CashMovement.cash_session_id == session.id, CashMovement.idempotency_key == payload.idempotency_key
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing  # même opération renvoyée (double clic / retry) : jamais un doublon
    _ensure_open(session)

    direction = CASH_MOVEMENT_FIXED_DIRECTIONS.get(payload.type) or payload.direction
    assert direction is not None  # garanti par CashMovementCreate (OTHER exige une direction)
    if direction == "OUT":
        available = (await session_totals(db, session)).expected_amount
        if payload.amount > available:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Outgoing movement exceeds the cash available in the session",
            )

    movement = CashMovement(
        id=uuid.uuid4(),
        cash_session_id=session.id,
        school_id=session.school_id,
        organization_id=session.organization_id,
        type=payload.type,
        direction=direction,
        amount=payload.amount,
        reason=payload.reason.strip(),
        reference=(payload.reference or "").strip() or None,
        idempotency_key=payload.idempotency_key,
        created_by=user_id,
    )
    db.add(movement)
    await db.flush()
    await audit_service.record_audit_event(
        db,
        school_id=session.school_id,
        organization_id=session.organization_id,
        actor_user_id=user_id,
        action=audit_service.ACTION_CASH_MOVEMENT_CREATED,
        entity_type=audit_service.ENTITY_CASH_MOVEMENT,
        entity_id=movement.id,
        summary=f"Mouvement de caisse {payload.type} ({direction}) de {payload.amount} {school.currency} — {movement.reason}",
        metadata={
            "cash_session_id": str(session.id),
            "type": payload.type,
            "direction": direction,
            "amount": str(payload.amount),
            "reason": movement.reason,
        },
    )
    await _commit(db, user_id)
    await db.refresh(movement)
    return movement


async def create_count(
    db: AsyncSession, school: School, session_id: uuid.UUID, user_id: uuid.UUID, payload: CashCountCreate
) -> CashCount:
    session = await lock_session(db, session_id)
    _ensure_open(session)
    allowed = set(denominations_for(school.currency))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No denomination catalog for currency {school.currency}",
        )
    seen: set[Decimal] = set()
    for line in payload.lines:
        if line.denomination not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Unknown denomination {line.denomination}"
            )
        if line.denomination in seen:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Duplicate denomination {line.denomination}"
            )
        seen.add(line.denomination)

    # Total calculé ICI uniquement (jamais reçu du client).
    line_totals = [(line, line.denomination * line.quantity) for line in payload.lines]
    total = sum((value for _, value in line_totals), start=ZERO)
    count = CashCount(
        id=uuid.uuid4(),
        cash_session_id=session.id,
        school_id=session.school_id,
        organization_id=session.organization_id,
        counted_by=user_id,
        counted_at=datetime.now(timezone.utc),
        total_amount=total,
    )
    db.add(count)
    await db.flush()
    for line, line_total in line_totals:
        db.add(
            CashCountLine(
                id=uuid.uuid4(),
                cash_count_id=count.id,
                school_id=session.school_id,
                organization_id=session.organization_id,
                denomination=line.denomination,
                quantity=line.quantity,
                line_total=line_total,
            )
        )
    await db.flush()
    await audit_service.record_audit_event(
        db,
        school_id=session.school_id,
        organization_id=session.organization_id,
        actor_user_id=user_id,
        action=audit_service.ACTION_CASH_COUNT_CREATED,
        entity_type=audit_service.ENTITY_CASH_COUNT,
        entity_id=count.id,
        summary=f"Comptage de caisse : {total} {school.currency}",
        metadata={"cash_session_id": str(session.id), "total_amount": str(total)},
    )
    await _commit(db, user_id)
    await db.refresh(count)
    return count


async def close_session(
    db: AsyncSession, school: School, session_id: uuid.UUID, user_id: uuid.UUID, payload: CashSessionClose
) -> CashSession:
    session = await lock_session(db, session_id)
    _ensure_open(session)
    count = await latest_count(db, session)
    if count is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A cash count is required before closing")
    if count.id != payload.count_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A newer cash count exists, review it before closing")
    expected = (await session_totals(db, session)).expected_amount
    if expected != payload.expected_amount:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="The expected amount changed, review the session before closing"
        )
    variance = count.total_amount - expected
    reason: str | None = None
    note: str | None = None
    if variance != 0:
        note = (payload.variance_note or "").strip() or None
        if payload.variance_reason is None or note is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A variance reason and note are required when the count differs from the expected amount",
            )
        reason = payload.variance_reason

    session.status = "CLOSED"
    session.closed_at = datetime.now(timezone.utc)
    session.closed_by = user_id
    session.expected_amount = expected
    session.counted_amount = count.total_amount
    session.variance_amount = variance
    session.variance_reason = reason
    session.variance_note = note
    await db.flush()

    metadata = {
        "expected_amount": str(expected),
        "counted_amount": str(count.total_amount),
        "variance_amount": str(variance),
        "cash_count_id": str(count.id),
    }
    await audit_service.record_audit_event(
        db,
        school_id=session.school_id,
        organization_id=session.organization_id,
        actor_user_id=user_id,
        action=audit_service.ACTION_CASH_SESSION_CLOSED,
        entity_type=audit_service.ENTITY_CASH_SESSION,
        entity_id=session.id,
        summary=f"Caisse clôturée — théorique {expected}, compté {count.total_amount}, écart {variance} {school.currency}",
        metadata=metadata,
    )
    if variance != 0:
        await audit_service.record_audit_event(
            db,
            school_id=session.school_id,
            organization_id=session.organization_id,
            actor_user_id=user_id,
            action=audit_service.ACTION_CASH_VARIANCE_JUSTIFIED,
            entity_type=audit_service.ENTITY_CASH_SESSION,
            entity_id=session.id,
            summary=f"Écart de caisse de {variance} {school.currency} justifié ({reason}) : {note}",
            metadata={**metadata, "variance_reason": reason, "variance_note": note},
        )
    await _commit(db, user_id)
    await db.refresh(session)
    return session


# --- Supervision et rapports (agrégations SQL, jamais une liste tronquée) -------------------------
@dataclass(frozen=True)
class SessionFilters:
    date_from: date | None = None
    date_to: date | None = None
    status: str | None = None
    cashier_user_id: uuid.UUID | None = None


def _session_conditions(school: School, filters: SessionFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = [CashSession.school_id == school.id]
    if filters.status is not None:
        conditions.append(CashSession.status == filters.status)
    if filters.cashier_user_id is not None:
        conditions.append(CashSession.cashier_user_id == filters.cashier_user_id)
    if filters.date_from is not None:
        conditions.append(CashSession.opened_at >= day_bounds_utc(school, filters.date_from, filters.date_from)[0])
    if filters.date_to is not None:
        conditions.append(CashSession.opened_at < day_bounds_utc(school, filters.date_to, filters.date_to)[1])
    return conditions


async def list_sessions(
    db: AsyncSession, school: School, filters: SessionFilters, limit: int = SESSION_LIST_MAX_ROWS
) -> list[CashSessionSummaryOut]:
    agg = _aggregates(school.id)
    stmt = (
        _with_aggregates(
            select(CashSession, User.full_name, agg.cash_total, agg.cash_count, agg.in_total, agg.out_total, agg.current_expected)
            .select_from(CashSession)
            .outerjoin(User, User.id == CashSession.cashier_user_id),
            agg,
        )
        .where(*_session_conditions(school, filters))
        .order_by(CashSession.opened_at.desc(), CashSession.id.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).all()
    return [
        CashSessionSummaryOut.model_validate(
            {
                **session_out(school, session, cashier_name).model_dump(),
                "cash_payments_total": cash_total,
                "cash_payments_count": cash_count,
                "movements_in_total": in_total,
                "movements_out_total": out_total,
                "current_expected_amount": current_expected,
            }
        )
        for session, cashier_name, cash_total, cash_count, in_total, out_total, current_expected in rows
    ]


async def aggregate_sessions(db: AsyncSession, school: School, filters: SessionFilters) -> CashSessionsAggregateOut:
    agg = _aggregates(school.id)
    closed = CashSession.status == "CLOSED"
    stmt = _with_aggregates(
        select(
            func.count(CashSession.id),
            func.count(CashSession.id).filter(CashSession.status == "OPEN"),
            func.count(CashSession.id).filter(closed),
            func.coalesce(func.sum(CashSession.opening_amount), ZERO),
            func.coalesce(func.sum(agg.cash_total), ZERO),
            func.coalesce(func.sum(agg.in_total), ZERO),
            func.coalesce(func.sum(agg.out_total), ZERO),
            func.coalesce(func.sum(agg.current_expected), ZERO),
            func.coalesce(func.sum(CashSession.counted_amount).filter(closed), ZERO),
            func.coalesce(func.sum(CashSession.variance_amount).filter(closed), ZERO),
        ).select_from(CashSession),
        agg,
    ).where(*_session_conditions(school, filters))
    row = (await db.execute(stmt)).one()
    return CashSessionsAggregateOut(
        sessions_count=row[0],
        open_count=row[1],
        closed_count=row[2],
        opening_total=row[3],
        cash_payments_total=row[4],
        movements_in_total=row[5],
        movements_out_total=row[6],
        expected_total=row[7],
        counted_total=row[8],
        variance_total=row[9],
    )


async def cashier_report(db: AsyncSession, school: School, filters: SessionFilters) -> list[CashierReportRowOut]:
    agg = _aggregates(school.id)
    stmt = (
        _with_aggregates(
            select(
                CashSession.cashier_user_id,
                User.full_name,
                func.count(CashSession.id),
                func.count(CashSession.id).filter(CashSession.status == "OPEN"),
                func.coalesce(func.sum(agg.cash_total), ZERO),
                func.coalesce(func.sum(agg.cash_count), 0),
                func.coalesce(func.sum(agg.in_total), ZERO),
                func.coalesce(func.sum(agg.out_total), ZERO),
                func.coalesce(func.sum(CashSession.variance_amount).filter(CashSession.status == "CLOSED"), ZERO),
            )
            .select_from(CashSession)
            .outerjoin(User, User.id == CashSession.cashier_user_id),
            agg,
        )
        .where(*_session_conditions(school, filters))
        .group_by(CashSession.cashier_user_id, User.full_name)
        .order_by(User.full_name)
    )
    return [
        CashierReportRowOut(
            cashier_user_id=row[0],
            cashier_name=row[1],
            sessions_count=row[2],
            open_count=row[3],
            cash_payments_total=row[4],
            cash_payments_count=row[5],
            movements_in_total=row[6],
            movements_out_total=row[7],
            variance_total=row[8],
        )
        for row in (await db.execute(stmt)).all()
    ]


async def payment_method_totals(db: AsyncSession, school: School, date_from: date, date_to: date) -> list[PaymentMethodTotalOut]:
    """Tous les paiements de l'école (toutes méthodes, tous enregistreurs) par date de paiement
    (`paid_at`, déjà une date métier) — agrégation SQL, aucune limite de lignes."""
    completed = Payment.status == "COMPLETED"
    cancelled = Payment.status == "CANCELLED"
    stmt = (
        select(
            Payment.method,
            func.count(Payment.id).filter(completed),
            func.coalesce(func.sum(Payment.amount).filter(completed), ZERO),
            func.count(Payment.id).filter(cancelled),
            func.coalesce(func.sum(Payment.amount).filter(cancelled), ZERO),
        )
        .where(Payment.school_id == school.id, Payment.paid_at >= date_from, Payment.paid_at <= date_to)
        .group_by(Payment.method)
        .order_by(Payment.method)
    )
    return [
        PaymentMethodTotalOut.model_validate(
            {
                "method": row[0],
                "completed_count": row[1],
                "completed_total": row[2],
                "cancelled_count": row[3],
                "cancelled_total": row[4],
            }
        )
        for row in (await db.execute(stmt)).all()
    ]


_CSV_HEADER = [
    "session_id",
    "date_metier",
    "caissier",
    "statut",
    "ouverture",
    "cloture",
    "fonds_initial",
    "encaissements_especes",
    "nb_encaissements",
    "mouvements_entrees",
    "mouvements_sorties",
    "theorique",
    "physique",
    "ecart",
    "motif_ecart",
    "note_ecart",
]


def _csv_cell(value: object) -> str:
    text = "" if value is None else str(value)
    # Injection de formule (tableur) : une cellule commençant par = + - @ est neutralisée.
    if text and text[0] in "=+-@\t\r" and not _is_number(text):
        return "'" + text
    return text


def _is_number(text: str) -> bool:
    try:
        Decimal(text)
    except ArithmeticError:
        return False
    return True


def sessions_csv(school: School, rows: list[CashSessionSummaryOut]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(_CSV_HEADER)
    zone = school_zone(school)
    for row in rows:
        writer.writerow(
            [
                _csv_cell(value)
                for value in (
                    row.id,
                    row.business_date.isoformat(),
                    row.cashier_name,
                    row.status,
                    row.opened_at.astimezone(zone).strftime("%Y-%m-%d %H:%M"),
                    row.closed_at.astimezone(zone).strftime("%Y-%m-%d %H:%M") if row.closed_at else "",
                    row.opening_amount,
                    row.cash_payments_total,
                    row.cash_payments_count,
                    row.movements_in_total,
                    row.movements_out_total,
                    row.current_expected_amount,
                    row.counted_amount,
                    row.variance_amount,
                    row.variance_reason,
                    row.variance_note,
                )
            ]
        )
    return buffer.getvalue()
