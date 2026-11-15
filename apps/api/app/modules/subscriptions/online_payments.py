"""Phase 29, lot B — paiement des factures d'abonnement par Mobile Money (PayGate Global).

Méthode DIRECTE de PayGate (cadrage §4.3 et §5.5 ; guide d'intégration du tableau de bord marchand,
lu le 2026-11-15) : seul le serveur parle à PayGate, la clé API ne quitte jamais le serveur.

Déroulement :
1. **Lancement** (`initiate_online_payment`, utilisateur `subscriptions.pay`) : contrôles sous le
   verrou de l'école puis de la facture (même ordre que le lot A), tentative `INITIATED` créée et
   VALIDÉE en base AVANT tout appel réseau — une panne pendant l'appel laisse une trace que le
   rapprochement retrouve par son `identifier`.
2. **Appel `/api/v1/pay`** hors transaction et hors verrou. La tentative passe en `PENDING` (demande
   acceptée, ou issue inconnue) ou en `FAILED` (refus définitif : aucune transaction n'existe).
3. **Confirmation uniquement par la vérification d'état** (`check_payment`, `/api/v2/status` par
   `identifier`), déclenchée par le rafraîchissement de l'écran, par la notification de PayGate
   (non signée : simple déclencheur) ou par la tâche de rapprochement. Le résultat est appliqué sous
   le verrou de l'école, puis de la facture, puis de la tentative relue `FOR UPDATE` : une
   notification et la tâche simultanées ne créent jamais deux périodes (et l'index unique « un seul
   SUCCEEDED par facture » reste la seconde ligne de défense).

Montant : fixé par le serveur (total de la facture), jamais par le navigateur. Le guide officiel ne
renvoie pas le montant dans la vérification d'état ; s'il est présent et différent, la tentative
passe en `ANOMALY` (cadrage §5.8).

Coupe-circuit `SUBSCRIPTION_ONLINE_PAYMENT_ENABLED` : inactif, aucun lancement et aucun appel à
PayGate (les tentatives en cours reprennent à la réactivation).
"""

import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.online_payment import StatusResult, get_online_payment_provider
from app.core.tenancy import apply_tenant_context, set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.audit import service as audit_service
from app.modules.notifications.service import create_notifications
from app.modules.schools.models import School
from app.modules.subscriptions.models import (
    INVOICE_STATUS_ISSUED,
    IN_PROGRESS_PAYMENT_STATUSES,
    PAYMENT_CODE_LOCAL_TIMEOUT,
    PAYMENT_PROVIDER_PAYGATE,
    PAYMENT_STATUS_ANOMALY,
    PAYMENT_STATUS_EXPIRED,
    PAYMENT_STATUS_FAILED,
    PAYMENT_STATUS_INITIATED,
    PAYMENT_STATUS_PENDING,
    PAYMENT_STATUS_SUCCEEDED,
    SUBSCRIPTION_CURRENCY,
    PaymentProviderCallback,
    SubscriptionInvoice,
    SubscriptionPayment,
)
from app.modules.subscriptions.reminders import reminder_recipient_ids
from app.modules.subscriptions.schemas import OnlinePaymentInput
from app.modules.subscriptions.service import (
    _commit,
    _conflict,
    _ensure_payable,
    _lock_invoice,
    _mark_paid_and_create_period,
    get_invoice_or_404,
    get_school_or_404,
    lock_school_subscription,
    utc_now,
)
from app.modules.users.models import User

logger = logging.getLogger(__name__)

# Une tentative close localement faute de réponse est encore vérifiée pendant cette durée (succès
# tardif) ; la tâche de rapprochement fait sa dernière vérification à J+1 (cadrage §5.5, étape 9).
LATE_CHECK_WINDOW = timedelta(days=7)
LATE_CHECK_AFTER = timedelta(days=1)
# La tâche ne vérifie pas une tentative tout juste créée : son lancement est peut-être en cours.
RECONCILE_MIN_AGE = timedelta(minutes=1)


def _new_online_identifier() -> str:
    """Identifiant transmis à PayGate : aléatoire (80 bits), non devinable, jamais l'id de la
    facture ; court et alphanumérique, faute de règle publiée par PayGate sur sa longueur."""
    return f"EL{secrets.token_hex(10).upper()}"


def _pending_timeout() -> timedelta:
    return timedelta(minutes=settings.paygate_pending_timeout_minutes)


async def _restore_context(db: AsyncSession, user_id: uuid.UUID | None) -> None:
    """Le contexte RLS (`set_config(..., is_local=true)`) disparaît à chaque fin de transaction."""
    if user_id is None:
        await set_platform_wide_context(db)
    else:
        await apply_tenant_context(db, user_id)


async def _select_payment(db: AsyncSession, payment_id: uuid.UUID, *, for_update: bool = False) -> SubscriptionPayment | None:
    query = select(SubscriptionPayment).where(SubscriptionPayment.id == payment_id).execution_options(populate_existing=True)
    if for_update:
        query = query.with_for_update()
    return (await db.execute(query)).scalar_one_or_none()


async def get_payment_or_404(db: AsyncSession, payment_id: uuid.UUID) -> SubscriptionPayment:
    payment = await _select_payment(db, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription payment not found")
    return payment


async def _payment_in_progress(db: AsyncSession, invoice_id: uuid.UUID) -> SubscriptionPayment | None:
    return (
        await db.execute(
            select(SubscriptionPayment).where(
                SubscriptionPayment.invoice_id == invoice_id,
                SubscriptionPayment.status.in_(IN_PROGRESS_PAYMENT_STATUSES),
            )
        )
    ).scalar_one_or_none()


async def _tx_reference_taken(db: AsyncSession, tx_reference: str, payment_id: uuid.UUID) -> bool:
    return (
        await db.execute(
            select(SubscriptionPayment.id).where(
                SubscriptionPayment.tx_reference == tx_reference, SubscriptionPayment.id != payment_id
            )
        )
    ).first() is not None


def is_checkable(payment: SubscriptionPayment, now: datetime) -> bool:
    """Tentative PayGate encore en cours, ou close localement faute de réponse depuis moins de
    7 jours (recherche d'un succès tardif)."""
    if payment.provider != PAYMENT_PROVIDER_PAYGATE:
        return False
    if payment.status in IN_PROGRESS_PAYMENT_STATUSES:
        return True
    return (
        payment.status == PAYMENT_STATUS_EXPIRED
        and payment.provider_status_code == PAYMENT_CODE_LOCAL_TIMEOUT
        and payment.created_at > now - LATE_CHECK_WINDOW
    )


# --- Lancement ---------------------------------------------------------------------------------
async def initiate_online_payment(
    db: AsyncSession, invoice_id: uuid.UUID, user: User, payload: OnlinePaymentInput
) -> SubscriptionPayment:
    if not settings.subscription_online_payment_enabled:
        raise _conflict("Online payment is not available")
    user_id = user.id
    loaded = await get_invoice_or_404(db, invoice_id)
    await lock_school_subscription(db, loaded.school_id)
    invoice = await _lock_invoice(db, invoice_id)
    now = utc_now()

    # Idempotence : même clé + même réseau + même numéro = même demande (double clic, nouvel essai
    # réseau) ; même clé avec d'autres données = conflit explicite (règle de c85348b).
    existing = (
        await db.execute(
            select(SubscriptionPayment).where(
                SubscriptionPayment.invoice_id == invoice.id,
                SubscriptionPayment.idempotency_key == payload.idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        same = (
            existing.provider == PAYMENT_PROVIDER_PAYGATE
            and existing.method == payload.network
            and existing.payer_phone_last4 == payload.phone_number[-4:]
        )
        if same:
            return existing
        raise _conflict("Idempotency key already used for a different payment")

    _ensure_payable(invoice, now)
    assert invoice.total_amount is not None  # facture ISSUED : montant toujours défini (CHECK 0027)
    total = Decimal(invoice.total_amount)
    if total > settings.paygate_max_amount:
        raise _conflict("Invoice amount exceeds the online payment limit; a manual payment is required")

    # Une seule tentative en cours par facture (index unique partiel) : elle est renvoyée au lieu
    # d'en créer une seconde (cadrage §5.5, étape 2).
    in_progress = await _payment_in_progress(db, invoice.id)
    if in_progress is not None:
        return in_progress

    payment = SubscriptionPayment(
        id=uuid.uuid4(),
        invoice_id=invoice.id,
        school_id=invoice.school_id,
        organization_id=invoice.organization_id,
        provider=PAYMENT_PROVIDER_PAYGATE,
        method=payload.network,
        status=PAYMENT_STATUS_INITIATED,
        amount=total,
        currency=SUBSCRIPTION_CURRENCY,
        identifier=_new_online_identifier(),
        idempotency_key=payload.idempotency_key,
        payer_phone_last4=payload.phone_number[-4:],
        initiated_by=user_id,
    )
    db.add(payment)
    await db.flush()
    await audit_service.record_audit_event(
        db,
        school_id=invoice.school_id,
        organization_id=invoice.organization_id,
        actor_user_id=user_id,
        action=audit_service.ACTION_SUBSCRIPTION_PAYMENT_ONLINE_INITIATED,
        entity_type=audit_service.ENTITY_SUBSCRIPTION_PAYMENT,
        entity_id=payment.id,
        summary=(
            f"Paiement Mobile Money ({payload.network}) demandé pour la facture {invoice.number} : "
            f"{total} {SUBSCRIPTION_CURRENCY}, numéro se terminant par {payload.phone_number[-4:]}"
        ),
        metadata={"invoice_number": invoice.number, "network": payload.network, "amount": str(total)},
    )
    payment_id, identifier, number = payment.id, payment.identifier, invoice.number
    await _commit(db, user_id)

    result = await get_online_payment_provider().initiate(
        identifier=identifier,
        amount=int(total),
        phone_number=payload.phone_number,
        network=payload.network,
        description=f"Abonnement EduLinkage {number}",
    )

    locked = await _select_payment(db, payment_id, for_update=True)
    assert locked is not None
    # Une vérification concurrente (notification, écran) a pu faire avancer la tentative entre-temps :
    # on ne réécrit jamais un état déjà tranché.
    if locked.status == PAYMENT_STATUS_INITIATED:
        locked.provider_status_code = result.code[:16]
        if result.accepted is False:
            locked.status = PAYMENT_STATUS_FAILED
            await _audit_closed(db, locked, number, "refus du fournisseur à la demande de paiement")
        else:
            locked.status = PAYMENT_STATUS_PENDING
            if result.tx_reference and not await _tx_reference_taken(db, result.tx_reference, locked.id):
                locked.tx_reference = result.tx_reference
    await _commit(db, user_id)
    refreshed = await _select_payment(db, payment_id)
    assert refreshed is not None
    return refreshed


# --- Vérification d'état et application ----------------------------------------------------------
async def _audit_closed(db: AsyncSession, payment: SubscriptionPayment, number: str | None, reason: str) -> None:
    await audit_service.record_audit_event(
        db,
        school_id=payment.school_id,
        organization_id=payment.organization_id,
        actor_user_id=None,
        action=audit_service.ACTION_SUBSCRIPTION_PAYMENT_FAILED,
        entity_type=audit_service.ENTITY_SUBSCRIPTION_PAYMENT,
        entity_id=payment.id,
        summary=f"Paiement Mobile Money de la facture {number} non abouti ({payment.status}) : {reason}",
        metadata={"invoice_number": number, "status": payment.status, "provider_code": payment.provider_status_code},
    )


async def _mark_anomaly(
    db: AsyncSession, payment: SubscriptionPayment, invoice: SubscriptionInvoice, result: StatusResult, reason: str
) -> None:
    payment.status = PAYMENT_STATUS_ANOMALY
    payment.provider_status_code = result.code[:16]
    logger.warning(
        "Paiement d'abonnement en anomalie (%s) : tentative %s, facture %s — à traiter par la plateforme.",
        reason,
        payment.id,
        invoice.number,
    )
    await audit_service.record_audit_event(
        db,
        school_id=payment.school_id,
        organization_id=payment.organization_id,
        actor_user_id=None,
        action=audit_service.ACTION_SUBSCRIPTION_PAYMENT_ANOMALY,
        entity_type=audit_service.ENTITY_SUBSCRIPTION_PAYMENT,
        entity_id=payment.id,
        summary=(
            f"Paiement Mobile Money réussi chez le fournisseur mais non appliqué à la facture {invoice.number} "
            f"({reason}) : remboursement ou régularisation manuelle depuis le tableau de bord PayGate."
        ),
        metadata={
            "invoice_number": invoice.number,
            "reason": reason,
            "invoice_status": invoice.status,
            "expected_amount": str(payment.amount),
            "provider_amount": str(result.amount) if result.amount is not None else None,
            "tx_reference": payment.tx_reference,
        },
    )


async def _confirm(
    db: AsyncSession, payment: SubscriptionPayment, invoice: SubscriptionInvoice, school: School, now: datetime
) -> None:
    payment.status = PAYMENT_STATUS_SUCCEEDED
    payment.confirmed_at = now
    await db.flush()
    period = await _mark_paid_and_create_period(db, school, invoice, payment, now)
    await audit_service.record_audit_event(
        db,
        school_id=invoice.school_id,
        organization_id=invoice.organization_id,
        actor_user_id=None,
        action=audit_service.ACTION_SUBSCRIPTION_PAYMENT_CONFIRMED,
        entity_type=audit_service.ENTITY_SUBSCRIPTION_PAYMENT,
        entity_id=payment.id,
        summary=(
            f"Paiement Mobile Money ({payment.method}) confirmé pour la facture {invoice.number} : {payment.amount} "
            f"{SUBSCRIPTION_CURRENCY}, abonnement du {period.starts_on.isoformat()} au {period.ends_on.isoformat()}"
        ),
        metadata={
            "invoice_number": invoice.number,
            "method": payment.method,
            "amount": str(payment.amount),
            "tx_reference": payment.tx_reference,
            "payment_reference": payment.payment_reference,
            "period_starts_on": period.starts_on.isoformat(),
            "period_ends_on": period.ends_on.isoformat(),
        },
    )
    recipients = await reminder_recipient_ids(db, school)
    await create_notifications(
        db,
        organization_id=school.organization_id,
        school_id=school.id,
        recipient_user_ids=recipients,
        type_="SUBSCRIPTION_PAYMENT_CONFIRMED",
        title=f"Abonnement EduLinkage payé : facture {invoice.number}",
        body=(
            f"Le paiement Mobile Money de la facture {invoice.number} ({payment.amount} {SUBSCRIPTION_CURRENCY}) est "
            f"confirmé. L'abonnement de {school.name} couvre la période du {period.starts_on.strftime('%d/%m/%Y')} "
            f"au {period.ends_on.strftime('%d/%m/%Y')}. Le reçu est disponible sur la page Abonnement."
        ),
    )


async def _has_succeeded_payment(db: AsyncSession, invoice_id: uuid.UUID) -> bool:
    return (
        await db.execute(
            select(SubscriptionPayment.id).where(
                SubscriptionPayment.invoice_id == invoice_id, SubscriptionPayment.status == PAYMENT_STATUS_SUCCEEDED
            )
        )
    ).first() is not None


async def _apply_status(
    db: AsyncSession,
    payment: SubscriptionPayment,
    invoice: SubscriptionInvoice,
    school: School,
    result: StatusResult,
    now: datetime,
) -> None:
    payment.last_checked_at = now
    if result.tx_reference and payment.tx_reference is None and not await _tx_reference_taken(db, result.tx_reference, payment.id):
        payment.tx_reference = result.tx_reference
    if result.payment_reference:
        payment.payment_reference = result.payment_reference

    if result.state == "SUCCEEDED":
        if result.amount is not None and result.amount != Decimal(payment.amount):
            await _mark_anomaly(db, payment, invoice, result, "montant différent du total de la facture")
            return
        # La facture n'est confirmée que si elle attend encore son paiement. Une facture émise dont
        # la validité est dépassée PENDANT la tentative reste payable : la tâche quotidienne ne
        # l'expire pas tant qu'une tentative est en cours (service.expire_stale_invoices_for_school).
        if invoice.status == INVOICE_STATUS_ISSUED and not await _has_succeeded_payment(db, invoice.id):
            payment.provider_status_code = result.code[:16]
            await _confirm(db, payment, invoice, school, now)
            return
        await _mark_anomaly(db, payment, invoice, result, f"facture {invoice.status}, double paiement possible")
        return

    if result.state in ("EXPIRED", "CANCELLED"):
        payment.status = PAYMENT_STATUS_EXPIRED if result.state == "EXPIRED" else PAYMENT_STATUS_FAILED
        payment.provider_status_code = result.code[:16]
        await _audit_closed(db, payment, invoice.number, "expiré ou annulé chez le fournisseur")
        return

    # En cours ou inconnu : rien n'est tranché. Au-delà du délai, la tentative est close localement
    # pour libérer la facture ; elle sera revérifiée (succès tardif) jusqu'à J+7.
    if payment.status not in IN_PROGRESS_PAYMENT_STATUSES:
        return
    if result.state == "PENDING":
        payment.status = PAYMENT_STATUS_PENDING
        payment.provider_status_code = result.code[:16]
    if payment.created_at <= now - _pending_timeout():
        payment.status = PAYMENT_STATUS_EXPIRED
        payment.provider_status_code = PAYMENT_CODE_LOCAL_TIMEOUT
        await _audit_closed(db, payment, invoice.number, "aucune confirmation dans le délai")


async def check_payment(
    db: AsyncSession,
    payment_id: uuid.UUID,
    *,
    user_id: uuid.UUID | None = None,
    now: datetime | None = None,
    min_interval_seconds: int = 0,
) -> SubscriptionPayment | None:
    """Vérifie une tentative auprès du fournisseur et applique le résultat.

    La tentative est d'abord lue dans le contexte courant de la session : celui de l'utilisateur
    (écran ; `user_id` fourni, droits déjà vérifiés par la route) ou le contexte système (tâche,
    notification ; `user_id` None). L'application est TOUJOURS une opération système (acteur
    système dans l'audit ; période, notifications aux administrateurs et directeurs de l'école) :
    elle se fait en contexte platform-wide, puis le contexte de l'appelant est restauré. Aucune
    transaction ni aucun verrou n'est tenu pendant l'appel réseau."""
    now = now or utc_now()
    payment = await _select_payment(db, payment_id)
    if payment is None or not is_checkable(payment, now) or not settings.subscription_online_payment_enabled:
        return payment
    if (
        min_interval_seconds
        and payment.last_checked_at is not None
        and payment.last_checked_at > now - timedelta(seconds=min_interval_seconds)
    ):
        return payment
    identifier, school_id, invoice_id = payment.identifier, payment.school_id, payment.invoice_id
    await db.commit()

    result = await get_online_payment_provider().check_status(identifier=identifier)

    # Opération système (voir docstring) : l'autorisation réelle reste la lecture ci-dessus, faite
    # dans le contexte de l'appelant, et la sélection explicite de CETTE tentative.
    await set_platform_wide_context(db)
    await lock_school_subscription(db, school_id)
    invoice = await _lock_invoice(db, invoice_id)
    locked = await _select_payment(db, payment_id, for_update=True)
    assert locked is not None
    if is_checkable(locked, now):
        school = await get_school_or_404(db, school_id)
        await _apply_status(db, locked, invoice, school, result, now)
    await db.commit()
    await _restore_context(db, user_id)
    return await _select_payment(db, payment_id)


# --- Notification de PayGate ---------------------------------------------------------------------
def _short(value: object, max_length: int) -> str | None:
    if value is None or isinstance(value, (bool, dict, list)):
        return None
    text = str(value).strip()
    return text[:max_length] if text else None


async def record_paygate_callback(db: AsyncSession, payload: dict[str, Any] | None, source_ip: str | None) -> uuid.UUID | None:
    """Enregistre la notification (journal minimal) et renvoie l'id de la tentative à vérifier, ou
    None. Ne révèle rien à l'appelant : l'endpoint répond toujours la même chose."""
    await set_platform_wide_context(db)
    identifier = _short(payload.get("identifier"), 64) if payload else None
    callback = PaymentProviderCallback(
        id=uuid.uuid4(),
        provider=PAYMENT_PROVIDER_PAYGATE,
        identifier=identifier,
        tx_reference=_short(payload.get("tx_reference"), 128) if payload else None,
        declared_amount=_short(payload.get("amount"), 32) if payload else None,
        source_ip=(source_ip or "")[:64] or None,
        result="INVALID",
    )
    payment_id: uuid.UUID | None = None
    if identifier is not None:
        payment = (
            await db.execute(
                select(SubscriptionPayment).where(
                    SubscriptionPayment.identifier == identifier,
                    SubscriptionPayment.provider == PAYMENT_PROVIDER_PAYGATE,
                )
            )
        ).scalar_one_or_none()
        if payment is None:
            callback.result = "UNKNOWN_IDENTIFIER"
        elif not is_checkable(payment, utc_now()):
            callback.result = "NOT_IN_PROGRESS"
            callback.payment_id = payment.id
        else:
            callback.result = "CHECK_SCHEDULED"
            callback.payment_id = payment.id
            payment_id = payment.id
    db.add(callback)
    await db.commit()
    return payment_id


async def check_payment_in_new_session(payment_id: uuid.UUID) -> None:
    """Tâche d'arrière-plan lancée après la réponse à PayGate (sa propre session : celle de la
    requête est déjà fermée). Une erreur est journalisée, jamais propagée : la tâche de
    rapprochement reprendra la tentative."""
    async with AsyncSessionLocal() as db:
        try:
            await set_platform_wide_context(db)
            await check_payment(db, payment_id)
        except Exception:
            await db.rollback()
            logger.exception("Vérification de paiement après notification PayGate en échec (tentative %s).", payment_id)


# --- Rapprochement périodique ----------------------------------------------------------------------
@dataclass
class ReconcileResult:
    enabled: bool = True
    checked: int = 0
    errors: int = 0
    by_status: dict[str, int] = field(default_factory=dict)


async def reconcile_online_payments(db: AsyncSession, now: datetime | None = None) -> ReconcileResult:
    """Vérifie les tentatives en cours (notification perdue, écran fermé) et fait la dernière
    vérification à J+1 des tentatives closes localement. Une transaction par tentative : une erreur
    sur l'une n'empêche pas les autres."""
    if not settings.subscription_online_payment_enabled:
        return ReconcileResult(enabled=False)
    now = now or utc_now()
    result = ReconcileResult()
    await set_platform_wide_context(db)
    late_checks = and_(
        SubscriptionPayment.status == PAYMENT_STATUS_EXPIRED,
        SubscriptionPayment.provider_status_code == PAYMENT_CODE_LOCAL_TIMEOUT,
        SubscriptionPayment.created_at <= now - LATE_CHECK_AFTER,
        SubscriptionPayment.created_at > now - LATE_CHECK_WINDOW,
        or_(
            SubscriptionPayment.last_checked_at.is_(None),
            SubscriptionPayment.last_checked_at < SubscriptionPayment.created_at + LATE_CHECK_AFTER,
        ),
    )
    in_progress = and_(
        SubscriptionPayment.status.in_(IN_PROGRESS_PAYMENT_STATUSES),
        SubscriptionPayment.created_at <= now - RECONCILE_MIN_AGE,
    )
    payment_ids = [
        row[0]
        for row in (
            await db.execute(
                select(SubscriptionPayment.id)
                .where(SubscriptionPayment.provider == PAYMENT_PROVIDER_PAYGATE, or_(in_progress, late_checks))
                .order_by(SubscriptionPayment.created_at)
            )
        ).all()
    ]
    await db.commit()
    for payment_id in payment_ids:
        try:
            await set_platform_wide_context(db)
            payment = await check_payment(db, payment_id, now=now)
        except Exception:
            await db.rollback()
            result.errors += 1
            logger.exception("Rapprochement : vérification de la tentative %s en échec.", payment_id)
            continue
        result.checked += 1
        if payment is not None:
            result.by_status[payment.status] = result.by_status.get(payment.status, 0) + 1
    return result
