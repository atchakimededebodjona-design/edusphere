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

async function getJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path);
  return response.json();
}

async function postJson<T>(path: string): Promise<T> {
  const response = await apiFetch(path, { method: "POST" });
  return response.json();
}

export const notifications = {
  list: (before?: string) => getJson<NotificationList>(`/api/v1/notifications${before ? `?before=${before}` : ""}`),
  unreadCount: () => getJson<{ count: number }>("/api/v1/notifications/unread-count"),
  markRead: (id: string) => postJson<Notification>(`/api/v1/notifications/${id}/read`),
  markAllRead: () => postJson<{ count: number }>("/api/v1/notifications/mark-all-read"),
};
