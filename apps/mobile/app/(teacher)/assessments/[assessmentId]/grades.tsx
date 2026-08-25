import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { useLocalSearchParams, useNavigation } from "expo-router";
import { ApiError } from "@/lib/api/client";
import { results, type AssessmentResult } from "@/lib/grades/client";
import { students as studentsClient, type Student } from "@/lib/students/client";
import { useAuth } from "@/lib/auth/useAuth";

type RowValue = { score: string; is_absent: boolean };

export default function GradeEntryScreen() {
  const { assessmentId, classId, name, maxScore } = useLocalSearchParams<{
    assessmentId: string;
    classId: string;
    name: string;
    maxScore: string;
  }>();
  const { currentSchoolId } = useAuth();
  const navigation = useNavigation();

  const [roster, setRoster] = useState<Student[] | null>(null);
  const [values, setValues] = useState<Record<string, RowValue>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    navigation.setOptions({ title: name ?? "Saisie des notes" });
  }, [navigation, name]);

  useEffect(() => {
    if (!currentSchoolId || !classId || !assessmentId) return;
    void (async () => {
      const [studentList, existing] = await Promise.all([
        studentsClient.list(currentSchoolId, classId),
        results.list(assessmentId),
      ]);
      const sorted = [...studentList].sort((a, b) => a.last_name.localeCompare(b.last_name));
      setRoster(sorted);
      const initial: Record<string, RowValue> = {};
      for (const student of sorted) {
        const row = existing.find((r: AssessmentResult) => r.student_id === student.id);
        initial[student.id] = { score: row?.score != null ? String(row.score) : "", is_absent: row?.is_absent ?? false };
      }
      setValues(initial);
    })();
  }, [currentSchoolId, classId, assessmentId]);

  const maxScoreNumber = useMemo(() => Number(maxScore ?? 20), [maxScore]);

  function updateValue(studentId: string, patch: Partial<RowValue>) {
    setValues((prev) => ({ ...prev, [studentId]: { ...prev[studentId], ...patch } }));
  }

  async function handleSave() {
    if (!roster) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const entries = roster.map((student) => {
        const value = values[student.id] ?? { score: "", is_absent: false };
        return {
          student_id: student.id,
          score: value.is_absent || value.score === "" ? null : Number(value.score),
          is_absent: value.is_absent,
        };
      });
      await results.submit(assessmentId, entries);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setSaving(false);
    }
  }

  if (roster === null) {
    return (
      <View style={styles.center}>
        <ActivityIndicator />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Text style={styles.hint}>Note sur {maxScoreNumber}</Text>
      <FlatList
        data={roster}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => {
          const value = values[item.id] ?? { score: "", is_absent: false };
          return (
            <View style={styles.row}>
              <Text style={styles.studentName}>
                {item.last_name} {item.first_name}
              </Text>
              <View style={styles.rowControls}>
                <TextInput
                  style={styles.scoreInput}
                  keyboardType="numeric"
                  value={value.score}
                  editable={!value.is_absent}
                  onChangeText={(text) => updateValue(item.id, { score: text })}
                  placeholder="—"
                />
                <View style={styles.absentControl}>
                  <Text style={styles.absentLabel}>Absent</Text>
                  <Switch value={value.is_absent} onValueChange={(v) => updateValue(item.id, { is_absent: v })} />
                </View>
              </View>
            </View>
          );
        }}
        ListEmptyComponent={<Text style={styles.empty}>Aucun élève inscrit dans cette classe.</Text>}
      />
      {roster.length > 0 && (
        <TouchableOpacity style={styles.saveButton} onPress={handleSave} disabled={saving}>
          {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.saveButtonText}>Enregistrer les notes</Text>}
        </TouchableOpacity>
      )}
      {saved && <Text style={styles.saved}>Notes enregistrées.</Text>}
      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f8fafc", padding: 16, gap: 8 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#f8fafc" },
  hint: { fontSize: 13, color: "#475569" },
  empty: { textAlign: "center", marginTop: 32, color: "#94a3b8" },
  row: {
    backgroundColor: "#fff",
    borderRadius: 6,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: "#e2e8f0",
    gap: 8,
  },
  studentName: { fontSize: 15, color: "#0f172a", fontWeight: "600" },
  rowControls: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  scoreInput: {
    borderWidth: 1,
    borderColor: "#cbd5e1",
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    width: 80,
    backgroundColor: "#fff",
  },
  absentControl: { flexDirection: "row", alignItems: "center", gap: 6 },
  absentLabel: { fontSize: 13, color: "#475569" },
  saveButton: { backgroundColor: "#0f172a", borderRadius: 6, padding: 14, alignItems: "center", marginTop: 8 },
  saveButtonText: { color: "#fff", fontWeight: "600" },
  saved: { color: "#15803d", textAlign: "center" },
  error: { color: "#b91c1c", textAlign: "center" },
});
