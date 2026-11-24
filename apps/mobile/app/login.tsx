import { useState } from "react";
import { ActivityIndicator, StyleSheet, Text, TextInput, TouchableOpacity, View } from "react-native";
import { Redirect } from "expo-router";
import { ApiError, toUserMessage } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/useAuth";

export default function LoginScreen() {
  const { status, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  // 2026-11-24 — bouton « Afficher » / « Masquer » du mot de passe, comme sur le site.
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (status === "authenticated") return <Redirect href="/" />;

  async function handleSubmit() {
    setSubmitting(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      // L'API explique l'échec en français (« Compte inexistant », « Mot de passe incorrect »…) ;
      // seul le blocage après trop d'essais arrive en anglais.
      setError(
        err instanceof ApiError && err.status === 429
          ? "Trop d'essais de connexion. Patientez quelques minutes, puis réessayez."
          : toUserMessage(err),
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <View style={styles.container}>
      <Text style={styles.title}>EduLinkage</Text>
      <Text style={styles.subtitle}>Espace enseignant</Text>

      <TextInput
        style={styles.input}
        placeholder="Email"
        autoCapitalize="none"
        keyboardType="email-address"
        value={email}
        onChangeText={setEmail}
      />
      <View style={styles.passwordRow}>
        <TextInput
          style={[styles.input, styles.passwordInput]}
          placeholder="Mot de passe"
          secureTextEntry={!passwordVisible}
          autoCapitalize="none"
          autoCorrect={false}
          value={password}
          onChangeText={setPassword}
        />
        <TouchableOpacity
          style={styles.toggle}
          onPress={() => setPasswordVisible((v) => !v)}
          accessibilityRole="button"
          accessibilityLabel="Afficher le mot de passe"
          accessibilityState={{ selected: passwordVisible }}
        >
          <Text style={styles.toggleText}>{passwordVisible ? "Masquer" : "Afficher"}</Text>
        </TouchableOpacity>
      </View>

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
  passwordRow: { position: "relative", justifyContent: "center" },
  passwordInput: { paddingRight: 88 },
  toggle: { position: "absolute", right: 0, top: 0, bottom: 0, minWidth: 80, justifyContent: "center", alignItems: "center" },
  toggleText: { color: "#1d4ed8", fontWeight: "600" },
  button: { backgroundColor: "#0f172a", borderRadius: 6, padding: 14, alignItems: "center", marginTop: 8 },
  buttonText: { color: "#fff", fontWeight: "600" },
  error: { color: "#b91c1c", textAlign: "center" },
});
