import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, FlatList, StyleSheet, Text, TouchableOpacity, View } from "react-native";
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

export default function ClassDetailScreen() {
  const { classId } = useLocalSearchParams<{ classId: string }>();
  const { currentSchoolId, user } = useAuth();
  const router = useRouter();

  const [schoolClass, setSchoolClass] = useState<SchoolClass | null>(null);
  const [terms, setTerms] = useState<AcademicTerm[] | null>(null);
  const [selectedTermId, setSelectedTermId] = useState("");
  const [mySubjects, setMySubjects] = useState<{ classSubject: ClassSubject; subject: Subject | undefined }[] | null>(null);

  useEffect(() => {
    if (!classId || !currentSchoolId || !user) return;
    void (async () => {
      const cls = await schoolClasses.get(classId);
      setSchoolClass(cls);
      const [termList, csList, subjectList, assignmentList] = await Promise.all([
        academicTerms.list(cls.academic_year_id),
        classSubjects.list(classId),
        subjectsClient.list(currentSchoolId),
        teacherAssignments.list(classId),
      ]);
      setTerms(termList);
      setSelectedTermId(termList[0]?.id ?? "");

      const myAssignedClassSubjectIds = new Set(
        assignmentList.filter((a: TeacherAssignment) => a.user_id === user.id).map((a) => a.class_subject_id),
      );
      setMySubjects(
        csList
          .filter((cs) => myAssignedClassSubjectIds.has(cs.id))
          .map((cs) => ({ classSubject: cs, subject: subjectList.find((s) => s.id === cs.subject_id) })),
      );
    })();
  }, [classId, currentSchoolId, user]);

  const selectedTerm = useMemo(() => terms?.find((t) => t.id === selectedTermId), [terms, selectedTermId]);

  if (!schoolClass || terms === null || mySubjects === null) {
    return (
      <View style={styles.center}>
        <ActivityIndicator />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>{schoolClass.name}</Text>

      <Text style={styles.sectionLabel}>Période</Text>
      <FlatList
        horizontal
        data={terms}
        keyExtractor={(t) => t.id}
        showsHorizontalScrollIndicator={false}
        renderItem={({ item }) => (
          <TouchableOpacity
            style={[styles.chip, item.id === selectedTermId && styles.chipSelected]}
            onPress={() => setSelectedTermId(item.id)}
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
            disabled={!selectedTerm}
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
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#f8fafc" },
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
});
