import { apiFetch } from "@/lib/api/client";

// PR #14 — journal d'audit administratif (voir apps/api/app/modules/audit). Lecture seule : il
// n'existe aucune route de création côté client, chaque entrée est écrite par le backend lui-même
// dans la même transaction que l'action métier qu'elle décrit.
export type AuditLogEntry = {
  id: string;
  school_id: string;
  actor_user_id: string | null;
  actor_email: string | null;
  action: string;
  entity_type: string;
  entity_id: string | null;
  summary: string;
  metadata: Record<string, unknown> | null;
  created_at: string;
};

export type AuditLogsPage = {
  items: AuditLogEntry[];
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
};

export type AuditLogFilters = {
  dateFrom?: string;
  dateTo?: string;
  actorUserId?: string;
  action?: string;
  entityType?: string;
  page?: number;
  pageSize?: number;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  return response.json();
}

export const auditLogs = {
  list: (schoolId: string, filters: AuditLogFilters = {}) => {
    const params = new URLSearchParams({ school_id: schoolId });
    if (filters.dateFrom) params.set("date_from", filters.dateFrom);
    if (filters.dateTo) params.set("date_to", filters.dateTo);
    if (filters.actorUserId) params.set("actor_user_id", filters.actorUserId);
    if (filters.action) params.set("action", filters.action);
    if (filters.entityType) params.set("entity_type", filters.entityType);
    params.set("page", String(filters.page ?? 1));
    params.set("page_size", String(filters.pageSize ?? 20));
    return getJson<AuditLogsPage>(`/api/v1/audit-logs?${params.toString()}`);
  },
};
