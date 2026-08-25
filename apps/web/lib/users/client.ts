import { apiFetch } from "@/lib/api/client";

export type RoleCode =
  | "SCHOOL_ADMIN"
  | "DIRECTOR"
  | "ACCOUNTANT"
  | "TEACHER"
  | "STAFF"
  | "PARENT"
  | "STUDENT";

export const ASSIGNABLE_ROLES: { value: RoleCode; label: string }[] = [
  { value: "SCHOOL_ADMIN", label: "Administrateur d'école" },
  { value: "DIRECTOR", label: "Directeur" },
  { value: "ACCOUNTANT", label: "Comptable" },
  { value: "TEACHER", label: "Enseignant" },
  { value: "STAFF", label: "Personnel" },
  { value: "PARENT", label: "Parent" },
  { value: "STUDENT", label: "Élève" },
];

export type User = {
  id: string;
  email: string;
  full_name: string;
  phone: string | null;
  is_active: boolean;
  created_at: string;
};

export type RoleAssignment = {
  role_code: string;
  organization_id: string | null;
  school_id: string | null;
};

export type UserWithRoles = {
  user: User;
  roles: RoleAssignment[];
};

export type UserCreateRequest = {
  email: string;
  full_name: string;
  phone?: string | null;
  school_id: string;
  role_code: RoleCode;
};

export type UserCreateResponse = {
  user: User;
  roles: RoleAssignment[];
  dev_reset_token: string | null;
};

export const users = {
  list: (schoolId: string) => {
    return apiFetch(`/api/v1/users?school_id=${schoolId}`).then((r) => r.json() as Promise<UserWithRoles[]>);
  },
  create: (payload: UserCreateRequest) => {
    return apiFetch("/api/v1/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then((r) => r.json() as Promise<UserCreateResponse>);
  },
};
