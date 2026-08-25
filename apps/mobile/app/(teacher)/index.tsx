import { useEffect, useState } from "react";
import { ActivityIndicator, FlatList, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { useRouter } from "expo-router";
import { schoolClasses, type SchoolClass } from "@/lib/academics/client";
import { useAuth } from "@/lib/auth/useAuth";

export default function MyClassesScreen() {
  const { currentSchoolId } = useAuth();
  const router = useRouter();
  const [classes, setClasses] = useState<SchoolClass[] | null>(null);

  useEffect(() => {
    if (!currentSchoolId) return;
    void schoolClasses.list(currentSchoolId).then(setClasses);
  }, [currentSchoolId]);

  if (!currentSchoolId || classes === null) {
    return (
      <View style={styles.center}>
        <ActivityIndicator />
      </View>
    );
  }

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
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#f8fafc" },
  empty: { textAlign: "center", marginTop: 32, color: "#94a3b8" },
  row: { padding: 16, borderBottomWidth: 1, borderBottomColor: "#e2e8f0", backgroundColor: "#fff" },
  rowText: { fontSize: 16, color: "#0f172a" },
});
