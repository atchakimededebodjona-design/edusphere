import { FlatList, StyleSheet, Text, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { schoolClasses } from "@/lib/academics/client";
import { useAuth } from "@/lib/auth/useAuth";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { ErrorView, LoadingView } from "@/components/ScreenState";

export default function MyClassesScreen() {
  const { currentSchoolId } = useAuth();
  const router = useRouter();

  const state = useAsyncData(() => schoolClasses.list(currentSchoolId as string), [currentSchoolId], {
    enabled: currentSchoolId !== null,
  });

  if (state.status === "error") return <ErrorView message={state.message} onRetry={state.retry} />;
  // currentSchoolId === null est un cas de configuration (aucun rôle scopé école), pas une erreur
  // réseau — comportement inchangé par rapport à avant la Phase 12 (hors périmètre de ce correctif).
  if (state.status === "loading" || currentSchoolId === null) return <LoadingView />;

  const classes = state.data;

  return (
    <FlatList
      style={styles.container}
      data={classes}
      keyExtractor={(item) => item.id}
      ListEmptyComponent={<Text style={styles.empty}>Aucune classe affectée.</Text>}
      renderItem={({ item }) => (
        <TouchableOpacity style={styles.row} onPress={() => router.push(`/classes/${item.id}`)}>
          <Text style={styles.rowText}>{item.name}</Text>
        </TouchableOpacity>
      )}
    />
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f8fafc" },
  empty: { textAlign: "center", marginTop: 32, color: "#94a3b8" },
  row: { padding: 16, borderBottomWidth: 1, borderBottomColor: "#e2e8f0", backgroundColor: "#fff" },
  rowText: { fontSize: 16, color: "#0f172a" },
});
