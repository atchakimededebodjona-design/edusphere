import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from "react-native";

/** Écran plein-cadre en chargement — remplace l'`ActivityIndicator` isolé jusqu'ici dupliqué dans
 * chaque écran (Phase 12). */
export function LoadingView() {
  return (
    <View style={styles.center}>
      <ActivityIndicator />
    </View>
  );
}

/** Écran plein-cadre d'erreur réseau avec action de reprise réelle (Phase 12, §5/§7) : message
 * toujours produit par `toUserMessage()` (jamais de détail technique), bouton qui relance
 * effectivement la requête via `retry()` de `useAsyncData`. */
export function ErrorView({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <View style={styles.center}>
      <Text style={styles.message}>{message}</Text>
      <TouchableOpacity style={styles.button} onPress={onRetry}>
        <Text style={styles.buttonText}>Réessayer</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: "#f8fafc", padding: 24, gap: 12 },
  message: { fontSize: 14, color: "#b91c1c", textAlign: "center" },
  button: { backgroundColor: "#0f172a", borderRadius: 6, paddingHorizontal: 20, paddingVertical: 10 },
  buttonText: { color: "#fff", fontWeight: "600" },
});
