import { useEffect, useState } from "react";
import { ActivityIndicator, FlatList, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useLocalSearchParams, useNavigation, useRouter } from "expo-router";
import { assessments, type Assessment } from "@/lib/grades/client";

export default function AssessmentsScreen() {
  const { classSubjectId, termId, classId, subjectName } = useLocalSearchParams<{
    classSubjectId: string;
    termId: string;
    classId: string;
    subjectName: string;
  }>();
  const router = useRouter();
  const navigation = useNavigation();
  const [items, setItems] = useState<Assessment[] | null>(null);

  useEffect(() => {
    navigation.setOptions({ title: subjectName ?? "Évaluations" });
  }, [navigation, subjectName]);

  useEffect(() => {
    if (!classSubjectId || !termId) return;
    void assessments.list(classSubjectId, termId).then(setItems);
  }, [classSubjectId, termId]);

  if (items === null) {
    return (
      <View style={styles.center}>
        <ActivityIndicator />
      </View>
    );
  }

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
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#f8fafc" },
  empty: { textAlign: "center", marginTop: 32, color: "#94a3b8" },
  row: { padding: 16, borderBottomWidth: 1, borderBottomColor: "#e2e8f0", backgroundColor: "#fff" },
  rowTitle: { fontSize: 16, color: "#0f172a", fontWeight: "600" },
  rowSubtitle: { fontSize: 13, color: "#64748b", marginTop: 2 },
});
