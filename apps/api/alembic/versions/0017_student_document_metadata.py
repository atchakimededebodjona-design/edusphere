"""student document metadata (mime_type, file_size)

Ajoute deux colonnes nullables à `student_documents` : `mime_type` (type MIME réellement détecté
à l'upload, pas seulement déclaré par le navigateur — voir students/service.py::validate_document_upload)
et `file_size` (taille en octets). Nullable : les documents déjà uploadés avant cette migration
n'ont pas cette information et ne doivent pas être recalculés ici ; le téléchargement retombe sur
`mimetypes.guess_type` pour ces lignes anciennes (voir students/router.py::download_student_document).

Additive et non destructive : aucune autre colonne ni table touchée, RLS déjà en place sur
`student_documents` reste inchangée.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("student_documents", sa.Column("mime_type", sa.String(128), nullable=True))
    op.add_column("student_documents", sa.Column("file_size", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("student_documents", "file_size")
    op.drop_column("student_documents", "mime_type")
