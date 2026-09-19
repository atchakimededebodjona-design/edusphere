// Phase 28A — réutilisation stricte : le centre de notifications existant (app/(app)/notifications
// /page.tsx) n'a aucune dépendance à l'espace admin (ni currentSchoolId, ni permission RBAC), voir
// audit préalable. Le réexporter tel quel sous cette route évite de dupliquer un second système de
// notifications pour le seul portail parent.
export { default } from "@/app/(app)/notifications/page";
