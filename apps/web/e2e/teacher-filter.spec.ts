import { expect, test } from "@playwright/test";
import { filterSchoolTeachers } from "../lib/academics/teachers";
import type { UserWithRoles } from "../lib/users/client";

// Test pur du filtre de la liste « Enseignant » (aucun navigateur n'est lancé : pas de fixture page).
// Les données reprennent la forme exacte de GET /api/v1/users?school_id=… (UserOut + rôles).

const SCHOOL_ID = "11111111-1111-4111-8111-111111111111";
const OTHER_SCHOOL_ID = "22222222-2222-4222-8222-222222222222";
const ORGANIZATION_ID = "33333333-3333-4333-8333-333333333333";

function entry(
  fullName: string,
  roles: UserWithRoles["roles"],
  overrides: Partial<UserWithRoles["user"]> = {},
): UserWithRoles {
  return {
    user: {
      id: `${fullName}-id`,
      email: `${fullName.toLowerCase().replace(/ /g, ".")}@edulinkage.example`,
      full_name: fullName,
      phone: null,
      is_active: true,
      is_platform_admin: false,
      created_at: "2026-09-01T00:00:00Z",
      ...overrides,
    },
    roles,
  };
}

const teacherOfSchool = { role_code: "TEACHER", organization_id: ORGANIZATION_ID, school_id: SCHOOL_ID };
const teacherOfOtherSchool = { role_code: "TEACHER", organization_id: ORGANIZATION_ID, school_id: OTHER_SCHOOL_ID };
const staffOfSchool = { role_code: "STAFF", organization_id: ORGANIZATION_ID, school_id: SCHOOL_ID };

test("filterSchoolTeachers : ne garde que les enseignants actifs, non platform admin, rattachés à l'école", () => {
  const users: UserWithRoles[] = [
    entry("Koffi", [teacherOfSchool]),
    entry("Platform Teacher", [teacherOfSchool], { is_platform_admin: true }),
    entry("Secretariat", [staffOfSchool]),
    entry("Inactif", [teacherOfSchool], { is_active: false }),
    entry("Autre Ecole", [teacherOfOtherSchool]),
  ];

  const visible = filterSchoolTeachers(users, SCHOOL_ID).map((u) => u.user.full_name);

  expect(visible).toEqual(["Koffi"]);
});

test("un TEACHER actif de la même école, non platform admin, est visible", () => {
  const visible = filterSchoolTeachers([entry("Akossiwa", [teacherOfSchool])], SCHOOL_ID);
  expect(visible).toHaveLength(1);
});

test("un compte platform admin portant le rôle TEACHER de l'école n'est pas proposé", () => {
  const visible = filterSchoolTeachers(
    [entry("Admin Plateforme", [teacherOfSchool], { is_platform_admin: true })],
    SCHOOL_ID,
  );
  expect(visible).toHaveLength(0);
});

test("un STAFF de l'école n'est pas proposé", () => {
  expect(filterSchoolTeachers([entry("Secretariat", [staffOfSchool])], SCHOOL_ID)).toHaveLength(0);
});

test("un TEACHER inactif n'est pas proposé", () => {
  expect(filterSchoolTeachers([entry("Inactif", [teacherOfSchool], { is_active: false })], SCHOOL_ID)).toHaveLength(0);
});

test("un TEACHER d'une autre école n'est pas proposé", () => {
  expect(filterSchoolTeachers([entry("Autre", [teacherOfOtherSchool])], SCHOOL_ID)).toHaveLength(0);
});
