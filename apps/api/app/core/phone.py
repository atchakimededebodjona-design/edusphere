"""Normalisation de numéro de téléphone (PR #16 — canal SMS des rappels de frais en retard).

`Guardian.phone` (students/models.py) est un `String(32)` libre, jamais validé jusqu'ici — un
tuteur peut l'avoir saisi dans n'importe quel format (local, avec ou sans indicatif, espaces,
tirets...). Un simple regex local au Togo serait insuffisant et fragile dès qu'une organisation
d'un autre pays utilise la plateforme (`Organization.country_code` existe précisément pour ça,
voir organizations/models.py) — ce module s'appuie donc sur `phonenumbers` (portage Python de la
bibliothèque libphonenumber de Google, déjà la référence de facto pour ce problème, pure Python,
aucune dépendance transitive lourde) plutôt que de réinventer une validation régionale.

Aucune fonction ici ne lève jamais : un numéro absent/invalide retourne `None`, jamais une
exception — un seul tuteur mal renseigné ne doit jamais faire échouer tout le lot de rappels
(voir fees/overdue_reminders.py, qui boucle sur potentiellement des milliers de tuteurs)."""

import phonenumbers


def normalize_phone_to_e164(raw: str | None, default_region: str) -> str | None:
    """Retourne la représentation E.164 (ex. "+22890123456") d'un numéro, ou `None` s'il est
    absent, vide, ou invalide après analyse.

    `default_region` : code pays ISO alpha-2 (ex. "TG") utilisé UNIQUEMENT pour interpréter un
    numéro saisi sans indicatif international explicite (`phonenumbers` l'ignore si `raw`
    commence déjà par "+") — toujours `Organization.country_code` de l'organisation du frais
    concerné, jamais une valeur figée en dur (voir fees/overdue_reminders.py), pour rester
    correct si une organisation d'un autre pays que le Togo utilise un jour la plateforme.

    Jamais utilisé comme clé d'idempotence (voir fee_overdue_sms_reminders, dont la contrainte
    unique porte sur `guardian_id`, jamais sur le numéro lui-même) : un même tuteur qui corrige
    son numéro entre deux exécutions du job reste le même destinataire pour la cadence J0/J7/J30,
    jamais un "nouveau" destinataire."""
    if not raw:
        return None
    candidate = raw.strip()
    if not candidate:
        return None
    try:
        parsed = phonenumbers.parse(candidate, default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
