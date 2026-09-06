import { useEffect, useState } from "react";
import { ActivityIndicator, FlatList, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { notifications as notificationsClient, type Notification } from "@/lib/notifications/client";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { ErrorView, LoadingView } from "@/components/ScreenState";

const TYPE_LABELS: Record<string, string> = {
  ANNOUNCEMENT: "Annonce",
  REPORT_CARD_PUBLISHED: "Bulletin",
  PAYMENT_RECORDED: "Paiement",
};

/** Partagé entre le flux Parent et le flux Enseignant (Phase 21) — les deux affichent la même
 * chose (les notifications de l'utilisateur courant, quel que soit son rôle), aucune raison de
 * dupliquer l'écran. */
export function NotificationsScreen() {
  const state = useAsyncData(() => notificationsClient.list(), []);
  const [items, setItems] = useState<Notification[]>([]);
  const [markingAll, setMarkingAll] = useState(false);

  useEffect(() => {
    if (state.status === "success") setItems(state.data.items);
  }, [state]);

  async function handleMarkRead(id: string) {
    const updated = await notificationsClient.markRead(id);
    setItems((prev) => prev.map((n) => (n.id === id ? updated : n)));
  }

  async function handleMarkAllRead() {
    setMarkingAll(true);
    try {
      await notificationsClient.markAllRead();
      setItems((prev) => prev.map((n) => ({ ...n, read_at: n.read_at ?? new Date().toISOString() })));
    } finally {
      setMarkingAll(false);
    }
  }

  if (state.status === "loading") return <LoadingView />;
  if (state.status === "error") return <ErrorView message={state.message} onRetry={state.retry} />;

  const hasUnread = items.some((n) => n.read_at === null);

  return (
    <View style={styles.container}>
      {hasUnread && (
        <TouchableOpacity style={styles.markAllButton} disabled={markingAll} onPress={() => void handleMarkAllRead()}>
          {markingAll ? <ActivityIndicator size="small" /> : <Text style={styles.markAllText}>Tout marquer comme lu</Text>}
        </TouchableOpacity>
      )}
      <FlatList
        data={items}
        keyExtractor={(item) => item.id}
        ListEmptyComponent={<Text style={styles.empty}>Aucune notification.</Text>}
        renderItem={({ item }) => (
          <TouchableOpacity
            style={[styles.row, item.read_at === null && styles.rowUnread]}
            disabled={item.read_at !== null}
            onPress={() => void handleMarkRead(item.id)}
          >
            <Text style={styles.rowType}>{TYPE_LABELS[item.type] ?? item.type}</Text>
            <Text style={styles.rowTitle}>{item.title}</Text>
            <Text style={styles.rowBody}>{item.body}</Text>
            <Text style={styles.rowDate}>{new Date(item.created_at).toLocaleString()}</Text>
          </TouchableOpacity>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f8fafc" },
  markAllButton: { padding: 12, alignItems: "flex-end" },
  markAllText: { fontSize: 13, color: "#0f172a", fontWeight: "600" },
  empty: { textAlign: "center", marginTop: 32, color: "#94a3b8" },
  row: { padding: 14, borderBottomWidth: 1, borderBottomColor: "#e2e8f0", backgroundColor: "#fff" },
  rowUnread: { backgroundColor: "#eff6ff" },
  rowType: { fontSize: 11, fontWeight: "700", color: "#94a3b8", textTransform: "uppercase" },
  rowTitle: { fontSize: 15, fontWeight: "600", color: "#0f172a", marginTop: 2 },
  rowBody: { fontSize: 13, color: "#475569", marginTop: 2 },
  rowDate: { fontSize: 11, color: "#94a3b8", marginTop: 4 },
});
