from pydantic import BaseModel


class PlatformDashboardOut(BaseModel):
    organization_count: int
    school_count: int
    user_count: int
    student_count: int
