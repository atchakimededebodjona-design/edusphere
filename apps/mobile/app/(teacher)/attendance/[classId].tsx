import { useEffect, useState } from "react";
import { FlatList, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { useLocalSearchParams, useNavigation } from "expo-router";
import { academicTerms, schoolClasses, type AcademicTerm } from "@/lib/academics/client";
import {
  attendanceRecords,
  attendanceSessions,
  type AttendanceRecord,
  type AttendanceSession,
  type AttendanceStatusValue,
} from "@/lib/attendance/client";
import { students as studentsClient, type Student } from "@/lib/students/client";
import { useAuth } from "@/lib/auth/useAuth";
import { toUserMessage } from "@/lib/api/client";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { ErrorView, LoadingView } from "@/components/ScreenState";

const STATUS_OPTIONS: { value: AttendanceStatusValue; label: string }[] = [
  { value: "PRESENT", label: "Présent" },
  { value: "ABSENT", label: "Absent" },
  { value: "LATE", label: "Retard" },
];

type RowValue = { status: AttendanceStatusValue; justified: boolean; reason: string };

type AttendanceSetup = {
  term: AcademicTerm | null;
  roster: Student[];
  session: AttendanceSession | null;
  records: AttendanceRecord[];
};

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

async function loadAttendanceSetup(classId: string, currentSchoolId: string, sessionDate: string): Promise<AttendanceSetup> {
  const cls = await schoolClasses.get(classId);
  const terms = await academicTerms.list(cls.academic_year_id);
  const currentTerm = terms.find((t) => t.start_date <= sessionDate && sessionDate <= t.end_date) ?? terms[0] ?? null;

  const rosterList = await studentsClient.list(currentSchoolId, classId);

  if (!currentTerm) return { term: null, roster: rosterList, session: null, records: [] };

  const existingSessions = await attendanceSessions.list(classId, currentTerm.id, sessionDate);
  let activeSession = existingSessions[0] ?? null;
  if (!activeSession) {
    activeSession = await attendanceSessions.create({
      class_id: classId,
      academic_term_id: currentTerm.id,
      session_date: sessionDate,
    });
  }

  const records = await attendanceRecords.list(activeSession.id);
  return { term: currentTerm, roster: rosterList, session: activeSession, records };
}

export default function AttendanceScreen() {
  const { classId } = useLocalSearchParams<{ classId: string }>();
  const { currentSchoolId } = useAuth();
  const navigation = useNavigation();

  const [values, setValues] = useState<Record<string, RowValue>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const sessionDate = todayIso();

  useEffect(() => {
    navigation.setOptions({ title: "Faire l'appel" });
  }, [navigation]);

  const enabled = Boolean(classId && currentSchoolId);
  const state = useAsyncData(
    () => loadAttendanceSetup(classId as string, currentSchoolId as string, sessionDate),
    [classId, currentSchoolId, sessionDate],
    { enabled },
  );

  useEffect(() => {
    if (state.status !== "success") return;
    const initial: Record<string, RowValue> = {};
    for (const student of state.data.roster) {
      const record = state.data.records.find((r) => r.student_id === student.id);
      initial[student.id] = {
        status: record?.status ?? "PRESENT",
        justified: record?.justified ?? false,
        reason: record?.reason ?? "",
      };
    }
    setValues(initial);
    setSaved(false);
    setError(null);
    // Ne dépend que de la réussite du chargement (nouvelle session/roster) — pas de `values` pour
    // ne pas écraser les modifications en cours de l'utilisateur.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status === "success" ? state.data : null]);

  function updateValue(studentId: string, patch: Partial<RowValue>) {
    setValues((prev) => ({ ...prev, [studentId]: { ...prev[studentId], ...patch } }));
  }

  async function handleSave() {
    if (state.status !== "success" || !state.data.session) return;
    const { session, roster } = state.data;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      const entries = roster.map((student) => {
        const value = values[student.id] ?? { status: "PRESENT" as AttendanceStatusValue, justified: false, reason: "" };
        return {
          student_id: student.id,
          status: value.status,
          justified: value.justified,
          reason: value.reason.trim() === "" ? null : value.reason,
        };
      });
      await attendanceRecords.submit(session.id, entries);
      setSaved(true);
    } catch (err) {
      setError(toUserMessage(err));
    } finally {
      setSaving(false);
    }
  }

  if (state.status === "error") return <ErrorView message={state.message} onRetry={state.retry} />;
  if (state.status === "loading" || !enabled) return <LoadingView />;

  const { term, roster, session } = state.data;
  // `term`/`session` null après un chargement réussi signifie "aucune période académique
  // couvrant aujourd'hui" — un problème de configuration côté école, pas une erreur réseau.
  // Comportement inchangé par rapport à avant la Phase 12 (hors périmètre de ce correctif).
  if (!term || !session) return <LoadingView />;

  return (
    <View style={styles.container}>
      {session.locked && <Text style={styles.locked}>Cette session est verrouillée — contactez l&apos;administration pour la modifier.</Text>}
      <FlatList
        data={roster.slice().sort((a, b) => a.last_name.localeCompare(b.last_name))}
        keyExtractor={(item) => item.id}
        ListEmptyComponent={<Text style={styles.empty}>Aucun élève inscrit dans cette classe.</Text>}
        renderItem={({ item }) => {
          const value = values[item.id] ?? { status: "PRESENT" as AttendanceStatusValue, justified: false, reason: "" };
          return (
            <View style={styles.row}>
              <Text style={styles.studentName}>
                {item.last_name} {item.first_name}
              </Text>
              <View style={styles.statusGroup}>
                {STATUS_OPTIONS.map((option) => (
                  <TouchableOpacity
                    key={option.value}
                    disabled={session.locked}
                    style={[styles.statusChip, value.status === option.value && styles.statusChipSelected]}
                    onPress={() => updateValue(item.id, { status: option.value })}
                  >
                    <Text style={[styles.statusChipText, value.status === option.value && styles.statusChipTextSelected]}>
                      {option.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
              {value.status !== "PRESENT" && (
                <View style={styles.detailsRow}>
                  <TouchableOpacity
                    disabled={session.locked}
                    style={styles.justifiedToggle}
                    onPress={() => updateValue(item.id, { justified: !value.justified })}
                  >
                    <Text style={styles.justifiedText}>{value.justified ? "☑" : "☐"} Justifié</Text>
                  </TouchableOpacity>
                  <TextInput
                    editable={!session.locked}
                    value={value.reason}
                    onChangeText={(text) => updateValue(item.id, { reason: text })}
                    placeholder="Motif (optionnel)"
                    style={styles.reasonInput}
                  />
                </View>
              )}
            </View>
          );
        }}
      />
      {!session.locked && roster.length > 0 && (
        <TouchableOpacity style={[styles.saveButton, saving && styles.saveButtonDisabled]} onPress={handleSave} disabled={saving}>
          <Text style={styles.saveButtonText}>{saving ? "Enregistrement..." : "Enregistrer l'appel"}</Text>
        </TouchableOpacity>
      )}
      {saved && <Text style={styles.saved}>Présences enregistrées.</Text>}
      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f8fafc" },
  empty: { textAlign: "center", marginTop: 32, color: "#94a3b8" },
  locked: { backgroundColor: "#fef3c7", color: "#92400e", padding: 10, fontSize: 13 },
  row: { padding: 14, borderBottomWidth: 1, borderBottomColor: "#e2e8f0", backgroundColor: "#fff", gap: 8 },
  studentName: { fontSize: 15, fontWeight: "600", color: "#0f172a" },
  statusGroup: { flexDirection: "row", gap: 8 },
  statusChip: { borderWidth: 1, borderColor: "#cbd5e1", borderRadius: 16, paddingHorizontal: 12, paddingVertical: 6, backgroundColor: "#fff" },
  statusChipSelected: { backgroundColor: "#0f172a", borderColor: "#0f172a" },
  statusChipText: { color: "#0f172a", fontSize: 13 },
  statusChipTextSelected: { color: "#fff" },
  detailsRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  justifiedToggle: { paddingVertical: 4 },
  justifiedText: { fontSize: 13, color: "#334155" },
  reasonInput: { flex: 1, borderWidth: 1, borderColor: "#cbd5e1", borderRadius: 6, paddingHorizontal: 8, paddingVertical: 4, fontSize: 13 },
  saveButton: { margin: 16, backgroundColor: "#0f172a", borderRadius: 8, paddingVertical: 14, alignItems: "center" },
  saveButtonDisabled: { opacity: 0.5 },
  saveButtonText: { color: "#fff", fontSize: 15, fontWeight: "600" },
  saved: { textAlign: "center", color: "#15803d", marginBottom: 8 },
  error: { textAlign: "center", color: "#b91c1c", marginBottom: 8 },
});
