import uuid

from pydantic import BaseModel

# Le module `parent` réutilise directement les schémas Out déjà existants pour les notes
# (StudentAveragesOut, grades) et les bulletins (ReportCardOut, report_cards) et la fiche élève
# (StudentOut, students) — voir router.py. Un seul schéma propre est nécessaire : la présence,
# car le mobile enseignant/admin exige toujours une période académique explicite
# (attendance.schemas.AttendanceStudentSummaryOut), alors que le mobile parent n'a volontairement
# aucun sélecteur de période (périmètre minimal validé) et doit pouvoir afficher un agrégat
# toutes périodes confondues — d'où `academic_term_id` optionnel ci-dessous.


class ParentAttendanceSummaryOut(BaseModel):
    student_id: uuid.UUID
    academic_term_id: uuid.UUID | None
    total_sessions: int
    present_count: int
    absent_count: int
    late_count: int
    justified_absence_count: int
    attendance_rate: float | None
