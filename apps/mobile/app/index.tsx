import { ActivityIndicator, StyleSheet, View } from "react-native";
import { Redirect } from "expo-router";
import { useAuth } from "@/lib/auth/useAuth";

/**
 * Point d'entrée unique après connexion : route par rôle (Phase 7).
 *
 * PARENT -> (parent). Tout autre rôle -> (teacher), comportement strictement inchangé par
 * rapport à avant cette phase (TEACHER, mais aussi SCHOOL_ADMIN/DIRECTOR/STAFF qui atterrissaient
 * déjà sur (teacher) — non modifié ici, seul le cas PARENT est nouveau).
 */
export default function RootIndex() {
  const { status, roles } = useAuth();

  if (status === "loading") {
    return (
      <View style={styles.center}>
        <ActivityIndicator />
      </View>
    );
  }

  if (status === "anonymous") return <Redirect href="/login" />;

  const isParent = roles.some((r) => r.role_code === "PARENT");
  return <Redirect href={isParent ? "/(parent)" : "/(teacher)"} />;
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#f8fafc" },
});
