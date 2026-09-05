import { FlatList, StyleSheet, Text, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { children as childrenClient } from "@/lib/parent/client";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { ErrorView, LoadingView } from "@/components/ScreenState";

export default function MyChildrenScreen() {
  const router = useRouter();
  const state = useAsyncData(() => childrenClient.list(), []);

  if (state.status === "error") return <ErrorView message={state.message} onRetry={state.retry} />;
  if (state.status === "loading") return <LoadingView />;

  const items = state.data;

  return (
    <FlatList
      style={styles.container}
      data={items}
      keyExtractor={(item) => item.id}
      ListEmptyComponent={<Text style={styles.empty}>Aucun enfant rattaché à ce compte.</Text>}
      renderItem={({ item }) => (
        <TouchableOpacity style={styles.row} onPress={() => router.push(`/children/${item.id}`)}>
          <Text style={styles.rowTitle}>
            {item.first_name} {item.last_name}
          </Text>
          <Text style={styles.rowSubtitle}>{item.matricule}</Text>
        </TouchableOpacity>
      )}
    />
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f8fafc" },
  empty: { textAlign: "center", marginTop: 32, color: "#94a3b8", paddingHorizontal: 24 },
  row: { padding: 16, borderBottomWidth: 1, borderBottomColor: "#e2e8f0", backgroundColor: "#fff" },
  rowTitle: { fontSize: 16, fontWeight: "600", color: "#0f172a" },
  rowSubtitle: { fontSize: 13, color: "#64748b", marginTop: 2 },
});
