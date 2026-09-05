import { useEffect } from "react";
import { FlatList, StyleSheet, Text, TouchableOpacity } from "react-native";
import { useLocalSearchParams, useNavigation, useRouter } from "expo-router";
import { assessments } from "@/lib/grades/client";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { ErrorView, LoadingView } from "@/components/ScreenState";

export default function AssessmentsScreen() {
  const { classSubjectId, termId, classId, subjectName } = useLocalSearchParams<{
    classSubjectId: string;
    termId: string;
    classId: string;
    subjectName: string;
  }>();
  const router = useRouter();
  const navigation = useNavigation();

  useEffect(() => {
    navigation.setOptions({ title: subjectName ?? "Évaluations" });
  }, [navigation, subjectName]);

  const state = useAsyncData(() => assessments.list(classSubjectId as string, termId as string), [classSubjectId, termId], {
    enabled: Boolean(classSubjectId && termId),
  });

  if (state.status === "error") return <ErrorView message={state.message} onRetry={state.retry} />;
  if (state.status === "loading") return <LoadingView />;

  const items = state.data;

  return (
    <FlatList
      style={styles.container}
      data={items}
      keyExtractor={(item) => item.id}
      ListEmptyComponent={
        <Text style={styles.empty}>Aucune évaluation pour cette matière et cette période.</Text>
      }
      renderItem={({ item }) => (
        <TouchableOpacity
          style={styles.row}
          onPress={() =>
            router.push({
              pathname: "/assessments/[assessmentId]/grades",
              params: { assessmentId: item.id, classId, name: item.name, maxScore: String(item.max_score) },
            })
          }
        >
          <Text style={styles.rowTitle}>{item.name}</Text>
          <Text style={styles.rowSubtitle}>
            {item.assessment_date} — sur {item.max_score}
          </Text>
        </TouchableOpacity>
      )}
    />
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f8fafc" },
  empty: { textAlign: "center", marginTop: 32, color: "#94a3b8" },
  row: { padding: 16, borderBottomWidth: 1, borderBottomColor: "#e2e8f0", backgroundColor: "#fff" },
  rowTitle: { fontSize: 16, color: "#0f172a", fontWeight: "600" },
  rowSubtitle: { fontSize: 13, color: "#64748b", marginTop: 2 },
});
