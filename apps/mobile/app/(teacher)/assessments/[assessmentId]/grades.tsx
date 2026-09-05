import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, FlatList, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useLocalSearchParams, useNavigation } from "expo-router";
import { toUserMessage } from "@/lib/api/client";
import { results, type AssessmentResult } from "@/lib/grades/client";
import { students as studentsClient, type Student } from "@/lib/students/client";
import { useAuth } from "@/lib/auth/useAuth";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { ErrorView, LoadingView } from "@/components/ScreenState";

type RowValue = { score: string; is_absent: boolean };

type GradeEntrySetup = {
  roster: Student[];
  existing: AssessmentResult[];
};

async function loadGradeEntrySetup(currentSchoolId: string, classId: string, assessmentId: string): Promise<GradeEntrySetup> {
  const [studentList, existing] = await Promise.all([
    studentsClient.list(currentSchoolId, classId),
    results.list(assessmentId),
  ]);
  const roster = [...studentList].sort((a, b) => a.last_name.localeCompare(b.last_name));
  return { roster, existing };
}

export default function GradeEntryScreen() {
  const { assessmentId, classId, name, maxScore } = useLocalSearchParams<{
    assessmentId: string;
    classId: string;
    name: string;
    maxScore: string;
  }>();
  const { currentSchoolId } = useAuth();
  const navigation = useNavigation();

  const [values, setValues] = useState<Record<string, RowValue>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    navigation.setOptions({ title: name ?? "Saisie des notes" });
  }, [navigation, name]);

  const enabled = Boolean(currentSchoolId && classId && assessmentId);
  const state = useAsyncData(
    () => loadGradeEntrySetup(currentSchoolId as string, classId as string, assessmentId as string),
    [currentSchoolId, classId, assessmentId],
    { enabled },
  );

  useEffect(() => {
    if (state.status !== "success") return;
    const initial: Record<string, RowValue> = {};
    for (const student of state.data.roster) {
      const row = state.data.existing.find((r) => r.student_id === student.id);
      initial[student.id] = { score: row?.score != null ? String(row.score) : "", is_absent: row?.is_absent ?? false };
    }
    setValues(initial);
    setSaved(false);
    setError(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status === "success" ? state.data : null]);

  const maxScoreNumber = useMemo(() => Number(maxScore ?? 20), [maxScore]);

  function updateValue(studentId: string, patch: Partial<RowValue>) {
    setValues((prev) => ({ ...prev, [studentId]: { ...prev[studentId], ...patch } }));
  }

  async function handleSave() {
    if (state.status !== "success") return;
    const { roster } = state.data;
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
      setError(toUserMessage(err));
    } finally {
      setSaving(false);
    }
  }

  if (state.status === "error") return <ErrorView message={state.message} onRetry={state.retry} />;
  if (state.status === "loading" || !enabled) return <LoadingView />;

  const { roster } = state.data;

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
