"""Régression — démarrage standalone du job (Sprint 1.2 post-incident production).

`docker compose exec -T api python -m app.jobs.overdue_fee_reminders` a levé en production
`NoReferencedTableError` sur `notifications.recipient_user_id -> users.id` : la chaîne d'imports
du job (`app.jobs.overdue_fee_reminders` -> `app.modules.fees.overdue_reminders` -> ...) n'importe
jamais `app.modules.users.models`, donc la table `users` n'existait pas dans `Base.metadata` de ce
process. Une requête de LECTURE simple (ex. l'éligibilité des frais) ne déclenche jamais la
résolution de cette FK — seul un `flush()` qui doit réellement INSERER une nouvelle
`Notification` (tri topologique des tables par dépendances de FK, dans SQLAlchemy) la déclenche,
ce que `tests/test_overdue_fee_reminders.py` ne pouvait pas reproduire : ces tests appellent
`send_overdue_fee_reminders` directement dans le process pytest, dont `tests/conftest.py` importe
déjà `app.main` (qui importe transitivement tous les modèles via ses routers, dont `users`) avant
qu'aucun test ne s'exécute — `Base.metadata` y est donc toujours complet, contrairement à un vrai
`python -m app.jobs.overdue_fee_reminders` lancé dans un process neuf.

Seul un lancement du module dans un VRAI sous-process (`subprocess.run`, pas un import direct)
reproduit fidèlement l'incident.

Sprint 1.3 (canal email) ajoute un second modèle ORM (`FeeOverdueEmailReminder`) dont le `flush`
peut être touché par le même incident s'il n'est pas, lui aussi, enregistré dans
`app/db/model_registry.py` — ce test crée donc, en plus du tuteur avec compte, un tuteur SANS
compte utilisateur mais avec email, pour que le sous-processus exerce réellement les DEUX chemins
de `flush` (notifications in-app + suivi email) et pas seulement le premier."""

import os
import subprocess
import sys
from pathlib import Path

from httpx import AsyncClient

from tests.test_overdue_fee_reminders import PAST_DUE_DATE, _create_student_fee, _link_parent, _list_fee_overdue_notifications, _setup_student
from tests.test_overdue_fee_reminders_email import _create_guardian_with_email

API_ROOT = Path(__file__).resolve().parent.parent
EMAILS_DIR = API_ROOT / "emails"


def _existing_email_files() -> set[Path]:
    return set(EMAILS_DIR.glob("*.txt")) if EMAILS_DIR.exists() else set()


async def test_standalone_job_process_creates_notification_without_crashing(client: AsyncClient) -> None:
    env = await _setup_student(client, "overduestandalone")
    parent = await _link_parent(client, env, "parent.overduestandalone")
    guardian = await _create_guardian_with_email(client, env, "guardian.overduestandalone")
    await _create_student_fee(client, env, PAST_DUE_DATE)

    emails_before = _existing_email_files()

    result = subprocess.run(
        [sys.executable, "-m", "app.jobs.overdue_fee_reminders"],
        cwd=API_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"

    items = await _list_fee_overdue_notifications(client, parent["headers"])
    assert len(items) == 1

    # EMAIL_PROVIDER=local dans cet environnement (voir .env) — le sous-processus écrit réellement
    # un fichier sous EMAILS_DIR, non monkeypatché (impossible dans un process séparé) : on ne
    # compare donc qu'un avant/après pour tolérer d'éventuels fichiers déjà présents.
    new_files = _existing_email_files() - emails_before
    assert any(guardian["email"] in f.read_text(encoding="utf-8") for f in new_files)
