import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from "react-native";
import { Redirect, Stack } from "expo-router";
import { useAuth } from "@/lib/auth/useAuth";

function HeaderLogout() {
  const { logout } = useAuth();
  return (
    <TouchableOpacity onPress={() => logout()}>
      <Text style={styles.logout}>Déconnexion</Text>
    </TouchableOpacity>
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
        headerRight: () => <HeaderLogout />,
      }}
    >
      <Stack.Screen name="index" options={{ title: "Mes enfants" }} />
      <Stack.Screen name="children/[studentId]" options={{ title: "Enfant" }} />
    </Stack>
  );
}

const styles = StyleSheet.create({
  loading: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#f8fafc" },
  logout: { color: "#fff", marginRight: 12 },
});
