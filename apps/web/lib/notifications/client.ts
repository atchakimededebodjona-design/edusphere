import { apiFetch } from "@/lib/api/client";

export type NotificationType =
  | "ANNOUNCEMENT"
  | "REPORT_CARD_PUBLISHED"
  | "PAYMENT_RECORDED"
  | "STUDENT_ABSENT"
  | "FEE_OVERDUE";

export type Notification = {
  id: string;
  type: NotificationType;
  title: string;
  body: string;
  created_at: string;
  read_at: string | null;
};

export type NotificationList = {
  items: Notification[];
  next_before: string | null;
};

export type AnnouncementTargetType = "SCHOOL" | "CLASS";

export type AnnouncementCreate = {
  school_id: string;
  title: string;
  body: string;
  target_type: AnnouncementTargetType;
  class_ids?: string[];
};

export type AnnouncementResult = {
  recipient_count: number;
};

export type AnnouncementHistoryEntry = {
  title: string;
  body: string;
  type: NotificationType;
  created_at: string;
  recipient_count: number;
};

export type AnnouncementHistoryList = {
  items: AnnouncementHistoryEntry[];
  next_before: string | null;
};

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  return response.json();
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await apiFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return response.json();
}

export const notifications = {
  list: (params: { limit?: number; before?: string } = {}) => {
    const search = new URLSearchParams();
    if (params.limit) search.set("limit", String(params.limit));
    if (params.before) search.set("before", params.before);
    const query = search.toString();
    return getJson<NotificationList>(`/api/v1/notifications${query ? `?${query}` : ""}`);
  },
  unreadCount: () => getJson<{ count: number }>("/api/v1/notifications/unread-count"),
  markRead: (id: string) => postJson<Notification>(`/api/v1/notifications/${id}/read`, {}),
  markAllRead: () => postJson<{ count: number }>("/api/v1/notifications/mark-all-read", {}),
};

export const announcements = {
  create: (payload: AnnouncementCreate) => postJson<AnnouncementResult>("/api/v1/announcements", payload),
  history: (schoolId: string, params: { limit?: number; before?: string } = {}) => {
    const search = new URLSearchParams({ school_id: schoolId });
    if (params.limit) search.set("limit", String(params.limit));
    if (params.before) search.set("before", params.before);
    return getJson<AnnouncementHistoryList>(`/api/v1/announcements?${search.toString()}`);
  },
};
