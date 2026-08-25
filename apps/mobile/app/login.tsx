import { useState } from "react";
import { ActivityIndicator, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { Redirect } from "expo-router";
import { ApiError } from "@/lib/auth/client";
import { useAuth } from "@/lib/auth/useAuth";

export default function LoginScreen() {
  const { status, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status === "authenticated") return <Redirect href="/" />;

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Une erreur est survenue.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>EduSphere</Text>
      <Text style={styles.subtitle}>Espace enseignant</Text>

      <TextInput
        style={styles.input}
        placeholder="Email"
        autoCapitalize="none"
        keyboardType="email-address"
        value={email}
        onChangeText={setEmail}
      />
      <TextInput
        style={styles.input}
        placeholder="Mot de passe"
        secureTextEntry
        value={password}
        onChangeText={setPassword}
      />

      <TouchableOpacity style={styles.button} onPress={handleSubmit} disabled={submitting}>
        {submitting ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>Se connecter</Text>}
      </TouchableOpacity>

      {error && <Text style={styles.error}>{error}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: "center", padding: 24, gap: 12, backgroundColor: "#f8fafc" },
  title: { fontSize: 28, fontWeight: "700", color: "#0f172a", textAlign: "center" },
  subtitle: { fontSize: 14, color: "#475569", textAlign: "center", marginBottom: 12 },
  input: { borderWidth: 1, borderColor: "#cbd5e1", borderRadius: 6, padding: 12, backgroundColor: "#fff" },
  button: { backgroundColor: "#0f172a", borderRadius: 6, padding: 14, alignItems: "center", marginTop: 8 },
  buttonText: { color: "#fff", fontWeight: "600" },
  error: { color: "#b91c1c", textAlign: "center" },
});
