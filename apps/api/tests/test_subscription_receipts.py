"""Reçu d'abonnement : mentions légales et détail HT, TVA, TTC (décisions du 2026-11-15).

Tests sans base de données : le reçu est construit à partir d'objets déjà chargés. L'accès au reçu
(facture payée seulement, école et plateforme, refus des autres) est couvert par
test_subscriptions_lot_c.py.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.core.config import settings
from app.modules.report_cards.service import html_to_pdf
from app.modules.schools.models import School
from app.modules.subscriptions import pricing
from app.modules.subscriptions.models import SchoolSubscriptionPeriod, SubscriptionInvoice, SubscriptionPayment
from app.modules.subscriptions.service import _issuer_html, _receipt_html, receipt_amounts

NBSP = " "


def _invoice(
    *,
    tier: int | None,
    base: str | None,
    supplement: str | None,
    total: str,
    vat_rate: str | None,
    student_count: int = 180,
) -> SubscriptionInvoice:
    return SubscriptionInvoice(
        id=uuid.uuid4(),
        school_id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        number="EL-2026-000042",
        status="PAID",
        period_months=3,
        student_count=student_count,
        tier=tier,
        base_amount=Decimal(base) if base is not None else None,
        supplement_amount=Decimal(supplement) if supplement is not None else None,
        total_amount=Decimal(total),
        vat_rate=Decimal(vat_rate) if vat_rate is not None else None,
        currency="XOF",
        issued_at=datetime(2026, 11, 20, 9, 0, tzinfo=timezone.utc),
    )


def _receipt(invoice: SubscriptionInvoice, **payment_fields: object) -> str:
    school = School(id=invoice.school_id, organization_id=invoice.organization_id, name="Collège <Les Palmiers>", address="Kara")
    fields: dict = {
        "provider": "PAYGATE",
        "method": "TMONEY",
        "status": "SUCCEEDED",
        "tx_reference": "8387643",
        "payment_reference": "20632528894",
    }
    fields.update(payment_fields)
    payment = SubscriptionPayment(
        id=uuid.uuid4(),
        invoice_id=invoice.id,
        school_id=invoice.school_id,
        organization_id=invoice.organization_id,
        amount=invoice.total_amount,
        currency="XOF",
        identifier="EL-TEST",
        confirmed_at=datetime(2026, 11, 21, 10, 30, tzinfo=timezone.utc),
        **fields,
    )
    period = SchoolSubscriptionPeriod(
        id=uuid.uuid4(),
        school_id=invoice.school_id,
        organization_id=invoice.organization_id,
        kind="PAID",
        invoice_id=invoice.id,
        starts_on=date(2027, 2, 13),
        ends_on=date(2027, 5, 12),
    )
    return _receipt_html(school, invoice, payment, period)


@pytest.fixture
def company(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        "billing_trade_name": "EduLinkage",
        "billing_legal_name": "ENTREPRISE <TEST>",
        "billing_legal_form": "Entreprise individuelle",
        "billing_address": "Rue du Marché, Kara",
        "billing_nif": "1000000000",
        "billing_rccm": "TG-LOM 2020 A 00000",
        "billing_tax_regime": "",
        "billing_phone": "+228 90 00 00 00",
        "billing_email": "",
    }.items():
        monkeypatch.setattr(settings, name, value)


def test_amounts_excluding_vat_from_the_grid_amounts() -> None:
    # Grille TTC en production : 35 400 + 11 800 (101 à 250 élèves) = 47 200 TTC.
    invoice = _invoice(tier=1, base="35400", supplement="11800", total="47200", vat_rate="18.00")
    lines, total_excl_vat, vat, total = receipt_amounts(invoice)
    assert [amount for _, amount in lines] == [Decimal(30000), Decimal(10000)]
    assert (total_excl_vat, vat, total) == (Decimal(40000), Decimal(7200), Decimal(47200))
    # Même HT que la base de la commission des partenaires.
    assert total_excl_vat == pricing.amount_excl_vat(Decimal(47200), Decimal(18))


def test_rounding_is_absorbed_by_the_last_line() -> None:
    invoice = _invoice(tier=1, base="35401", supplement="11799", total="47200", vat_rate="18")
    lines, total_excl_vat, vat, total = receipt_amounts(invoice)
    assert [amount for _, amount in lines] == [Decimal(30001), Decimal(9999)]
    assert sum(amount for _, amount in lines) == total_excl_vat == Decimal(40000)
    assert total_excl_vat + vat == total


def test_invoice_without_frozen_vat_rate_shows_no_vat() -> None:
    # Facture antérieure à la TVA (EL-2026-000001, 100 FCFA, tranche 0).
    invoice = _invoice(tier=0, base="100", supplement="0", total="100", vat_rate=None, student_count=15)
    lines, total_excl_vat, vat, total = receipt_amounts(invoice)
    assert len(lines) == 1  # pas de ligne « supplément » à 0
    assert (total_excl_vat, vat, total) == (Decimal(100), Decimal(0), Decimal(100))
    html = _receipt(invoice)
    assert "TVA" not in html and "Total HT" not in html
    assert "Montant (FCFA)" in html


def test_quote_and_progressive_labels() -> None:
    quote = _invoice(tier=None, base=None, supplement=None, total="500000", vat_rate="18", student_count=2600)
    [(label, amount)] = receipt_amounts(quote)[0]
    assert "devis" in label and amount == pricing.amount_excl_vat(Decimal(500000), Decimal(18))

    step = _invoice(tier=pricing.STEP_TIER, base="35400", supplement="141600", total="177000", vat_rate="18", student_count=1300)
    labels = [label for label, _ in receipt_amounts(step)[0]]
    assert labels[1] == "Supplément au-delà de 1 000 élèves (2 paliers de 250 élèves)"

    tier_one = _invoice(tier=1, base="35400", supplement="11800", total="47200", vat_rate="18")
    assert receipt_amounts(tier_one)[0][1][0] == "Supplément d'effectif (101 à 250 élèves)"


def test_receipt_shows_company_identity_vat_detail_and_legal_note(company: None) -> None:
    invoice = _invoice(tier=1, base="35400", supplement="11800", total="47200", vat_rate="18.00")
    html = _receipt(invoice)
    # Identité de l'entreprise, échappée ; un champ vide (e-mail) n'est pas imprimé.
    assert "ENTREPRISE &lt;TEST&gt;" in html and "<TEST>" not in html
    for expected in ("Entreprise individuelle", "Rue du Marché, Kara", "NIF : 1000000000", "RCCM : TG-LOM 2020 A 00000"):
        assert expected in html
    assert "Tél. : +228 90 00 00 00" in html and "E-mail" not in html
    # Client, échappé.
    assert "Collège &lt;Les Palmiers&gt;" in html
    # Détail HT, TVA et TTC.
    assert "Montant HT (FCFA)" in html
    assert f"30{NBSP}000" in html and f"10{NBSP}000" in html
    assert "Total HT" in html and f"40{NBSP}000" in html
    assert "TVA 18 %" in html and f"7{NBSP}200" in html
    assert "Total TTC" in html and f"Montant payé : 47{NBSP}200 FCFA" in html
    # Paiement et mention.
    assert "T-Money (Mobile Money)" in html
    assert "transaction 8387643" in html and "référence opérateur 20632528894" in html
    assert "émise le 20/11/2026" in html and "du 13/02/2027 au 12/05/2027" in html
    assert "Il ne tient pas lieu de" in html and "facture normalisée : celle-ci est délivrée séparément." in html


def test_receipt_without_company_settings_prints_no_empty_mentions(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "billing_legal_name",
        "billing_legal_form",
        "billing_address",
        "billing_nif",
        "billing_rccm",
        "billing_tax_regime",
        "billing_phone",
        "billing_email",
    ):
        monkeypatch.setattr(settings, name, "")
    html = _receipt(
        _invoice(tier=1, base="35400", supplement="11800", total="47200", vat_rate="18"),
        provider="MANUAL",
        method="CASH",
        reference="REC-1",
        tx_reference=None,
        payment_reference=None,
    )
    for absent in ("NIF", "RCCM", "Régime fiscal", "Tél.", "E-mail"):
        assert absent not in html
    assert "EduLinkage — Reçu de paiement d'abonnement" in html
    assert "par espèces" in html and "Référence : REC-1." in html


def test_receipt_of_a_tpu_company_without_vat(company: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # Décision du 2026-11-15 : entreprise à la TPU, aucune TVA ; la grille porte les prix HT.
    monkeypatch.setattr(settings, "billing_tax_regime", "TPU")
    html = _receipt(_invoice(tier=1, base="30000", supplement="10000", total="40000", vat_rate=None))
    # Une mention par ligne : une étiquette n'est jamais séparée de sa valeur par le retour à la ligne.
    assert "NIF : 1000000000<br/>RCCM : TG-LOM 2020 A 00000<br/>Régime fiscal : TPU<br/>Tél. : +228 90 00 00 00" in html
    assert "TVA" not in html and "HT" not in html and "TTC" not in html
    assert "Montant (FCFA)" in html and f"Montant payé : 40{NBSP}000 FCFA" in html


def test_receipt_contacts_each_on_their_own_line(company: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "billing_phone", "+228 90 00 00 00 / +228 91 11 11 11")
    monkeypatch.setattr(settings, "billing_email", "contact@example.com")
    html = _receipt(_invoice(tier=1, base="30000", supplement="10000", total="40000", vat_rate=None))
    assert "<br/>Tél. : +228 90 00 00 00 / +228 91 11 11 11<br/>E-mail : contact@example.com</td>" in html
    assert " — " not in _issuer_html()  # plus de mentions regroupées sur une même ligne


def test_receipt_renders_as_pdf(company: None) -> None:
    html = _receipt(_invoice(tier=1, base="35400", supplement="11800", total="47200", vat_rate="18"))
    assert html_to_pdf(html).startswith(b"%PDF")
