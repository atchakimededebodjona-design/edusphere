import type { UserWithRoles } from "@/lib/users/client";

/** Enseignants pouvant être affectés à une classe de `schoolId` : compte actif, rôle TEACHER
 * rattaché à cette école. Ce filtre n'est qu'un confort d'affichage : le backend
 * (academics/router.py::_ensure_school_teacher) refuse de toute façon tout autre cas. */
export function filterSchoolTeachers(users: UserWithRoles[], schoolId: string): UserWithRoles[] {
  return users.filter(
    (entry) =>
      entry.user.is_active &&
      entry.roles.some((role) => role.role_code === "TEACHER" && role.school_id === schoolId),
  );
}
