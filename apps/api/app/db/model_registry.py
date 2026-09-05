"""Importe tous les modèles ORM pour que Base.metadata les connaisse (Alembic autogenerate)."""

from app.modules.academics.models import (  # noqa: F401
    AcademicTerm,
    AcademicYear,
    ClassSubject,
    EducationLevel,
    Room,
    SchoolClass,
    Subject,
    TeacherAssignment,
)
from app.modules.attendance.models import AttendanceRecord, AttendanceSession  # noqa: F401
from app.modules.auth.models import PasswordResetToken, UserSession  # noqa: F401
from app.modules.grades.models import (  # noqa: F401
    Assessment,
    AssessmentResult,
    AssessmentType,
    StudentSubjectAverage,
    StudentTermAverage,
)
from app.modules.organizations.models import Organization  # noqa: F401
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole  # noqa: F401
from app.modules.report_cards.models import ReportCard, ReportCardTemplate  # noqa: F401
from app.modules.schools.models import School  # noqa: F401
from app.modules.students.models import (  # noqa: F401
    Guardian,
    Student,
    StudentDocument,
    StudentEnrollment,
    StudentGuardian,
    StudentStatusHistory,
)
from app.modules.users.models import User  # noqa: F401
