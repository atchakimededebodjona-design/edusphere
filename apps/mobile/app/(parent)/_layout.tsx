import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Redirect, Stack, useRouter } from "expo-router";
import { useAuth } from "@/lib/auth/useAuth";

function HeaderActions() {
  const { logout } = useAuth();
  const router = useRouter();
  return (
    <View style={styles.headerActions}>
      <TouchableOpacity onPress={() => router.push("/notifications")}>
        <Text style={styles.headerButton}>🔔</Text>
      </TouchableOpacity>
      <TouchableOpacity onPress={() => logout()}>
        <Text style={styles.logout}>Déconnexion</Text>
      </TouchableOpacity>
    </View>
  );
}

export default function ParentLayout() {
  const { status } = useAuth();

  if (status === "loading") {
    return (
      <View style={styles.loading}>
        <ActivityIndicator />
      </View>
    );
  }

  if (status === "anonymous") return <Redirect href="/login" />;

  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: "#0f172a" },
        headerTintColor: "#fff",
        headerRight: () => <HeaderActions />,
      }}
    >
      <Stack.Screen name="index" options={{ title: "Mes enfants" }} />
      <Stack.Screen name="children/[studentId]" options={{ title: "Enfant" }} />
      <Stack.Screen name="notifications" options={{ title: "Notifications" }} />
    </Stack>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#f8fafc" },
  headerActions: { flexDirection: "row", alignItems: "center", gap: 16 },
  headerButton: { fontSize: 18, marginRight: 4 },
  logout: { color: "#fff", marginRight: 12 },
});
