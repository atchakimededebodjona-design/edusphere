import { useState } from "react";
import { ActivityIndicator, FlatList, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useLocalSearchParams } from "expo-router";
import { childAttendance, childGrades, childReportCards } from "@/lib/parent/client";
import { ApiError } from "@/lib/api/client";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { ErrorView } from "@/components/ScreenState";

const TABS = ["Présence", "Notes", "Bulletins"] as const;
type Tab = (typeof TABS)[number];

function AttendanceTab({ studentId }: { studentId: string }) {
  const state = useAsyncData(() => childAttendance.summary(studentId), [studentId]);

  if (state.status === "loading") return <ActivityIndicator style={styles.tabLoading} />;
  if (state.status === "error") return <ErrorView message={state.message} onRetry={state.retry} />;

  const summary = state.data;

  return (
    <View style={styles.tabContent}>
      <View style={styles.statRow}>
        <Text style={styles.statLabel}>Taux de présence</Text>
        <Text style={styles.statValue}>{summary.attendance_rate != null ? `${summary.attendance_rate}%` : "—"}</Text>
      </View>
      <View style={styles.statRow}>
        <Text style={styles.statLabel}>Présences</Text>
        <Text style={styles.statValue}>{summary.present_count}</Text>
      </View>
      <View style={styles.statRow}>
        <Text style={styles.statLabel}>Absences</Text>
        <Text style={styles.statValue}>{summary.absent_count}</Text>
      </View>
      <View style={styles.statRow}>
        <Text style={styles.statLabel}>Retards</Text>
        <Text style={styles.statValue}>{summary.late_count}</Text>
      </View>
      <View style={styles.statRow}>
        <Text style={styles.statLabel}>Absences justifiées</Text>
        <Text style={styles.statValue}>{summary.justified_absence_count}</Text>
      </View>
    </View>
  );
}

function GradesTab({ studentId }: { studentId: string }) {
  const state = useAsyncData(() => childGrades.get(studentId), [studentId]);

  if (state.status === "loading") return <ActivityIndicator style={styles.tabLoading} />;
  if (state.status === "error") return <ErrorView message={state.message} onRetry={state.retry} />;

  const averages = state.data;

  return (
    <FlatList
      style={styles.tabContent}
      data={averages.subject_averages}
      keyExtractor={(item) => item.id}
      ListEmptyComponent={<Text style={styles.empty}>Aucune note disponible pour le moment.</Text>}
      renderItem={({ item }) => (
        <View style={styles.row}>
          <Text style={styles.rowTitle}>Moyenne : {item.average ?? "—"}</Text>
          <Text style={styles.rowSubtitle}>Rang : {item.rank ?? "—"}</Text>
          {item.appreciation && <Text style={styles.rowSubtitle}>{item.appreciation}</Text>}
        </View>
      )}
    />
  );
}

function ReportCardsTab({ studentId }: { studentId: string }) {
  const state = useAsyncData(() => childReportCards.list(studentId), [studentId]);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const [openError, setOpenError] = useState<string | null>(null);

  async function handleOpen(reportCardId: string) {
    setOpeningId(reportCardId);
    setOpenError(null);
    try {
      await childReportCards.openPdf(studentId, reportCardId);
    } catch (err) {
      // Jamais de détail technique/token dans le message affiché — uniquement le message
      // utilisateur déjà porté par ApiError (aucune donnée sensible loguée non plus).
      setOpenError(err instanceof ApiError ? err.message : "Le téléchargement du bulletin a échoué.");
    } finally {
      setOpeningId(null);
    }
  }

  if (state.status === "loading") return <ActivityIndicator style={styles.tabLoading} />;
  if (state.status === "error") return <ErrorView message={state.message} onRetry={state.retry} />;

  const reportCards = state.data;

  return (
    <View style={styles.tabContent}>
      {openError && <Text style={[styles.errorText, styles.errorBanner]}>{openError}</Text>}
      <FlatList
        style={styles.reportCardList}
        data={reportCards}
        keyExtractor={(item) => item.id}
        ListEmptyComponent={<Text style={styles.empty}>Aucun bulletin publié pour le moment.</Text>}
        renderItem={({ item }) => (
          <View style={styles.row}>
            <Text style={styles.rowTitle}>Moyenne générale : {item.general_average ?? "—"}</Text>
            <Text style={styles.rowSubtitle}>Rang : {item.general_rank ?? "—"}</Text>
            <Text style={styles.rowSubtitle}>Publié le {item.published_at?.slice(0, 10)}</Text>
            <TouchableOpacity
              style={styles.pdfButton}
              disabled={openingId === item.id}
              onPress={() => void handleOpen(item.id)}
            >
              {openingId === item.id ? (
                <ActivityIndicator color="#fff" size="small" />
              ) : (
                <Text style={styles.pdfButtonText}>Voir le bulletin</Text>
              )}
            </TouchableOpacity>
          </View>
        )}
      />
    </View>
  );
}

export default function ChildDetailScreen() {
  const { studentId } = useLocalSearchParams<{ studentId: string }>();
  const [tab, setTab] = useState<Tab>("Présence");

  if (!studentId) return null;

  return (
    <View style={styles.container}>
      <View style={styles.tabBar}>
        {TABS.map((t) => (
          <TouchableOpacity key={t} style={[styles.tabButton, tab === t && styles.tabButtonActive]} onPress={() => setTab(t)}>
            <Text style={[styles.tabButtonText, tab === t && styles.tabButtonTextActive]}>{t}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === "Présence" && <AttendanceTab studentId={studentId} />}
      {tab === "Notes" && <GradesTab studentId={studentId} />}
      {tab === "Bulletins" && <ReportCardsTab studentId={studentId} />}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f8fafc" },
  tabBar: { flexDirection: "row", backgroundColor: "#fff", borderBottomWidth: 1, borderBottomColor: "#e2e8f0" },
  tabButton: { flex: 1, paddingVertical: 14, alignItems: "center", borderBottomWidth: 2, borderBottomColor: "transparent" },
  tabButtonActive: { borderBottomColor: "#0f172a" },
  tabButtonText: { fontSize: 13, color: "#64748b" },
  tabButtonTextActive: { color: "#0f172a", fontWeight: "600" },
  tabLoading: { marginTop: 32 },
  tabContent: { flex: 1, padding: 16 },
  statRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#e2e8f0",
  },
  statLabel: { fontSize: 14, color: "#334155" },
  statValue: { fontSize: 14, fontWeight: "700", color: "#0f172a" },
  empty: { textAlign: "center", marginTop: 32, color: "#94a3b8" },
  row: { padding: 14, borderBottomWidth: 1, borderBottomColor: "#e2e8f0", backgroundColor: "#fff", marginBottom: 1 },
  rowTitle: { fontSize: 15, fontWeight: "600", color: "#0f172a" },
  rowSubtitle: { fontSize: 13, color: "#64748b", marginTop: 2 },
  reportCardList: { flex: 1 },
  errorText: { color: "#b91c1c" },
  errorBanner: { textAlign: "center", paddingVertical: 8 },
  pdfButton: {
    marginTop: 10,
    backgroundColor: "#0f172a",
    borderRadius: 6,
    paddingVertical: 10,
    alignItems: "center",
  },
  pdfButtonText: { color: "#fff", fontSize: 13, fontWeight: "600" },
});
