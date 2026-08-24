"""Importe tous les modèles ORM pour que Base.metadata les connaisse (Alembic autogenerate)."""

from app.modules.auth.models import PasswordResetToken, UserSession  # noqa: F401
from app.modules.organizations.models import Organization  # noqa: F401
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole  # noqa: F401
from app.modules.schools.models import School  # noqa: F401
from app.modules.users.models import User  # noqa: F401
