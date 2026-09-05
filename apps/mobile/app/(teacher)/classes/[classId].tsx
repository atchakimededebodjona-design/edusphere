import { useEffect, useState } from "react";
import { FlatList, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import {
  academicTerms,
  classSubjects,
  schoolClasses,
  subjects as subjectsClient,
  teacherAssignments,
  type AcademicTerm,
  type ClassSubject,
  type SchoolClass,
  type Subject,
  type TeacherAssignment,
} from "@/lib/academics/client";
import { useAuth } from "@/lib/auth/useAuth";
import { useAsyncData } from "@/lib/api/useAsyncData";
import { ErrorView, LoadingView } from "@/components/ScreenState";

type ClassDetail = {
  schoolClass: SchoolClass;
  terms: AcademicTerm[];
  mySubjects: { classSubject: ClassSubject; subject: Subject | undefined }[];
};

async function loadClassDetail(classId: string, currentSchoolId: string, userId: string): Promise<ClassDetail> {
  const cls = await schoolClasses.get(classId);
  const [termList, csList, subjectList, assignmentList] = await Promise.all([
    academicTerms.list(cls.academic_year_id),
    classSubjects.list(classId),
    subjectsClient.list(currentSchoolId),
    teacherAssignments.list(classId),
  ]);

  const myAssignedClassSubjectIds = new Set(
    assignmentList.filter((a: TeacherAssignment) => a.user_id === userId).map((a) => a.class_subject_id),
  );
  const mySubjects = csList
    .filter((cs) => myAssignedClassSubjectIds.has(cs.id))
    .map((cs) => ({ classSubject: cs, subject: subjectList.find((s) => s.id === cs.subject_id) }));

  return { schoolClass: cls, terms: termList, mySubjects };
}

export default function ClassDetailScreen() {
  const { classId } = useLocalSearchParams<{ classId: string }>();
  const { currentSchoolId, user } = useAuth();
  const router = useRouter();

  const [selectedTermIdOverride, setSelectedTermIdOverride] = useState<string | null>(null);
  useEffect(() => {
    setSelectedTermIdOverride(null);
  }, [classId]);

  const enabled = Boolean(classId && currentSchoolId && user);
  const state = useAsyncData(
    // `enabled` garantit que classId/currentSchoolId/user sont non-nuls quand cette fonction est
    // réellement invoquée (useAsyncData n'appelle pas fetcher tant que enabled est false).
    () => loadClassDetail(classId as string, currentSchoolId as string, user!.id),
    [classId, currentSchoolId, user],
    { enabled },
  );

  if (state.status === "error") return <ErrorView message={state.message} onRetry={state.retry} />;
  if (state.status === "loading" || !enabled) return <LoadingView />;

  const { schoolClass, terms, mySubjects } = state.data;
  const selectedTermId = selectedTermIdOverride ?? terms[0]?.id ?? "";

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{schoolClass.name}</Text>

      {mySubjects.length > 0 && (
        <TouchableOpacity
          style={styles.attendanceButton}
          onPress={() => router.push({ pathname: "/attendance/[classId]", params: { classId } })}
        >
          <Text style={styles.attendanceButtonText}>Faire l&apos;appel</Text>
        </TouchableOpacity>
      )}

      <Text style={styles.sectionLabel}>Période</Text>
      <FlatList
        horizontal
        data={terms}
        keyExtractor={(t) => t.id}
        showsHorizontalScrollIndicator={false}
        renderItem={({ item }) => (
          <TouchableOpacity
            style={[styles.chip, item.id === selectedTermId && styles.chipSelected]}
            onPress={() => setSelectedTermIdOverride(item.id)}
          >
            <Text style={[styles.chipText, item.id === selectedTermId && styles.chipTextSelected]}>{item.name}</Text>
          </TouchableOpacity>
        )}
      />

      <Text style={styles.sectionLabel}>Mes matières</Text>
      <FlatList
        data={mySubjects}
        keyExtractor={(item) => item.classSubject.id}
        ListEmptyComponent={<Text style={styles.empty}>Aucune matière affectée dans cette classe.</Text>}
        renderItem={({ item }) => (
          <TouchableOpacity
            style={styles.row}
            disabled={!selectedTermId}
            onPress={() =>
              router.push({
                pathname: "/assessments/[classSubjectId]",
                params: {
                  classSubjectId: item.classSubject.id,
                  termId: selectedTermId,
                  classId,
                  subjectName: item.subject?.name ?? "Matière",
                },
              })
            }
          >
            <Text style={styles.rowText}>{item.subject?.name ?? item.classSubject.subject_id}</Text>
          </TouchableOpacity>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#f8fafc", padding: 16, gap: 8 },
  title: { fontSize: 22, fontWeight: "700", color: "#0f172a" },
  sectionLabel: { fontSize: 13, fontWeight: "600", color: "#475569", marginTop: 12 },
  empty: { color: "#94a3b8", marginTop: 8 },
  chip: {
    borderWidth: 1,
    borderColor: "#cbd5e1",
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 6,
    marginRight: 8,
    backgroundColor: "#fff",
  },
  chipSelected: { backgroundColor: "#0f172a", borderColor: "#0f172a" },
  chipText: { color: "#0f172a", fontSize: 13 },
  chipTextSelected: { color: "#fff" },
  row: { padding: 14, borderBottomWidth: 1, borderBottomColor: "#e2e8f0", backgroundColor: "#fff", borderRadius: 6, marginTop: 6 },
  rowText: { fontSize: 15, color: "#0f172a" },
  attendanceButton: { backgroundColor: "#0f172a", borderRadius: 8, paddingVertical: 10, alignItems: "center", marginTop: 4 },
  attendanceButtonText: { color: "#fff", fontSize: 14, fontWeight: "600" },
});
