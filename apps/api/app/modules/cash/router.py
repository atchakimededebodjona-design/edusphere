"""Caisse scolaire, lot 3 — API des sessions de caisse (`/cash/*`).

Autorisation (toujours résolue pour l'ÉCOLE concernée, `get_scoped_permission_codes`) :
- `cash.register.read`   : consulter SA caisse (session dont on est le caissier) ;
- `cash.register.manage` : ouvrir SA caisse, y saisir mouvements/comptages, la clôturer ;
- `cash.register.review` : superviser TOUTES les caisses de l'école (lecture, et mêmes actions
  qu'un caissier sur une session ouverte — ex. clôture en son absence) + rapports.
L'école est d'abord chargée sous RLS (404 pour une autre organisation), puis chaque requête filtre
explicitement `school_id` : RLS (organisation) n'est jamais la seule protection d'une école.
"""

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.core.permissions import CurrentUser, DbSession, get_scoped_permission_codes
from app.modules.cash import service
from app.modules.cash.denominations import denominations_for
from app.modules.cash.models import CASH_VARIANCE_REASONS, CashSession
from app.modules.cash.schemas import (
    CashCountCreate,
    CashCountOut,
    CashDailyReportOut,
    CashierReportOut,
    CashMovementCreate,
    CashMovementOut,
    CashRegisterContextOut,
    CashSessionClose,
    CashSessionDetailOut,
    CashSessionOpen,
    CashSessionStatus,
    CashSessionSummaryOut,
    PaymentMethodReportOut,
)
from app.modules.schools.models import School
from app.modules.users.models import User

router = APIRouter()

READ = "cash.register.read"
MANAGE = "cash.register.manage"
REVIEW = "cash.register.review"
MAX_REPORT_DAYS = 366


async def _school_or_404(db: DbSession, school_id: uuid.UUID) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    return school


async def _permissions(db: DbSession, user: User, school: School) -> set[str]:
    return await get_scoped_permission_codes(db, user, organization_id=school.organization_id, school_id=school.id)


def _require(permissions: set[str], code: str) -> None:
    if code not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")


async def _session_context(
    db: DbSession, user: User, session_id: uuid.UUID, *, manage: bool
) -> tuple[CashSession, School]:
    """Session + école, après contrôle d'accès : le caissier propriétaire (read/manage), ou un
    superviseur (`cash.register.review`) de la même école. Jamais une session d'une autre école."""
    session = await db.get(CashSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cash session not found")
    school = await _school_or_404(db, session.school_id)
    permissions = await _permissions(db, user, school)
    if REVIEW in permissions:
        return session, school
    if session.cashier_user_id == user.id and (MANAGE if manage else READ) in permissions:
        return session, school
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")


def _date_range(school: School, date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = service.school_today(school)
    start = date_from or date_to or today
    end = date_to or date_from or today
    if end < start:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="date_to must not be before date_from")
    if end - start > timedelta(days=MAX_REPORT_DAYS):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Date range is too long")
    return start, end


# --- Ma caisse ------------------------------------------------------------------------------------
@router.get("/cash/sessions/current", response_model=CashRegisterContextOut)
async def get_current_session(db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)) -> CashRegisterContextOut:
    school = await _school_or_404(db, school_id)
    _require(await _permissions(db, current_user, school), READ)
    session = await service.get_open_session(db, school.id, current_user.id)
    return CashRegisterContextOut(
        school_id=school.id,
        currency=school.currency,
        timezone=school.timezone,
        business_date=service.school_today(school),
        denominations=list(denominations_for(school.currency)),
        variance_reasons=list(CASH_VARIANCE_REASONS),
        current=await service.session_detail(db, school, session) if session is not None else None,
    )


@router.post("/cash/sessions/open", response_model=CashSessionDetailOut, status_code=status.HTTP_201_CREATED)
async def open_cash_session(payload: CashSessionOpen, db: DbSession, current_user: CurrentUser) -> CashSessionDetailOut:
    school = await _school_or_404(db, payload.school_id)
    _require(await _permissions(db, current_user, school), MANAGE)
    session = await service.open_session(db, school, current_user.id, payload.opening_amount)
    return await service.session_detail(db, school, session)


@router.get("/cash/sessions/{session_id}", response_model=CashSessionDetailOut)
async def get_cash_session(session_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> CashSessionDetailOut:
    session, school = await _session_context(db, current_user, session_id, manage=False)
    return await service.session_detail(db, school, session)


@router.post("/cash/sessions/{session_id}/movements", response_model=CashMovementOut, status_code=status.HTTP_201_CREATED)
async def create_cash_movement(
    session_id: uuid.UUID, payload: CashMovementCreate, db: DbSession, current_user: CurrentUser
) -> CashMovementOut:
    _, school = await _session_context(db, current_user, session_id, manage=True)
    movement = await service.add_movement(db, school, session_id, current_user.id, payload)
    return CashMovementOut.model_validate(movement)


@router.post("/cash/sessions/{session_id}/count", response_model=CashCountOut, status_code=status.HTTP_201_CREATED)
async def create_cash_count(
    session_id: uuid.UUID, payload: CashCountCreate, db: DbSession, current_user: CurrentUser
) -> CashCountOut:
    _, school = await _session_context(db, current_user, session_id, manage=True)
    count = await service.create_count(db, school, session_id, current_user.id, payload)
    return await service.count_out(db, count)


@router.post("/cash/sessions/{session_id}/close", response_model=CashSessionDetailOut)
async def close_cash_session(
    session_id: uuid.UUID, payload: CashSessionClose, db: DbSession, current_user: CurrentUser
) -> CashSessionDetailOut:
    _, school = await _session_context(db, current_user, session_id, manage=True)
    session = await service.close_session(db, school, session_id, current_user.id, payload)
    return await service.session_detail(db, school, session)


# --- Historique / supervision -----------------------------------------------------------------------
@router.get("/cash/sessions", response_model=list[CashSessionSummaryOut])
async def list_cash_sessions(
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Query(...),
    session_status: CashSessionStatus | None = Query(None, alias="status"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    cashier_user_id: uuid.UUID | None = Query(None),
) -> list[CashSessionSummaryOut]:
    """Superviseur : toutes les sessions de l'école. Sinon (`cash.register.read`) : uniquement les
    siennes, quel que soit le filtre demandé."""
    school = await _school_or_404(db, school_id)
    permissions = await _permissions(db, current_user, school)
    if REVIEW not in permissions:
        _require(permissions, READ)
        cashier_user_id = current_user.id
    filters = service.SessionFilters(
        date_from=date_from, date_to=date_to, status=session_status, cashier_user_id=cashier_user_id
    )
    return await service.list_sessions(db, school, filters)


# --- Rapports (superviseurs) ------------------------------------------------------------------------
async def _review_school(db: DbSession, user: User, school_id: uuid.UUID) -> School:
    school = await _school_or_404(db, school_id)
    _require(await _permissions(db, user, school), REVIEW)
    return school


@router.get("/cash/reports/daily", response_model=CashDailyReportOut)
async def cash_daily_report(
    db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...), day: date | None = Query(None)
) -> CashDailyReportOut:
    """Journée métier (fuseau de l'école) : sessions OUVERTES ce jour-là, et paiements de l'école
    (toutes méthodes) dont la date de paiement est ce jour."""
    school = await _review_school(db, current_user, school_id)
    target = day or service.school_today(school)
    filters = service.SessionFilters(date_from=target, date_to=target)
    return CashDailyReportOut(
        day=target,
        currency=school.currency,
        timezone=school.timezone,
        sessions=await service.aggregate_sessions(db, school, filters),
        payments_by_method=await service.payment_method_totals(db, school, target, target),
    )


@router.get("/cash/reports/cashiers", response_model=CashierReportOut)
async def cash_cashier_report(
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Query(...),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> CashierReportOut:
    school = await _review_school(db, current_user, school_id)
    start, end = _date_range(school, date_from, date_to)
    rows = await service.cashier_report(db, school, service.SessionFilters(date_from=start, date_to=end))
    return CashierReportOut(date_from=start, date_to=end, currency=school.currency, rows=rows)


@router.get("/cash/reports/methods", response_model=PaymentMethodReportOut)
async def cash_method_report(
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Query(...),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> PaymentMethodReportOut:
    school = await _review_school(db, current_user, school_id)
    start, end = _date_range(school, date_from, date_to)
    rows = await service.payment_method_totals(db, school, start, end)
    return PaymentMethodReportOut(date_from=start, date_to=end, currency=school.currency, rows=rows)


@router.get("/cash/reports/export.csv")
async def cash_sessions_csv(
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Query(...),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> Response:
    school = await _review_school(db, current_user, school_id)
    start, end = _date_range(school, date_from, date_to)
    rows = await service.list_sessions(
        db, school, service.SessionFilters(date_from=start, date_to=end), limit=service.CSV_MAX_ROWS
    )
    content = "﻿" + service.sessions_csv(school, rows)  # BOM : accents lisibles sous Excel
    filename = f"caisse_{start.isoformat()}_{end.isoformat()}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
