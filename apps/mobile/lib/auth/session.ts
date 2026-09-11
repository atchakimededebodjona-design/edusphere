import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

const STORAGE_KEY = "edulinkage.session";
// Phase 27 Sprint 1.1 — ancienne clé, avant la normalisation de marque (voir
// docs/phases/PHASE_27_SPRINT_1_1_AUTH_SESSION_DISCOVERY.md §6). Migration triviale et cohérente
// avec le Web, appliquée par précaution même si l'app n'est pas encore publiée (aucun utilisateur
// réel concerné aujourd'hui).
const LEGACY_STORAGE_KEY = "edusphere.session";

export type StoredTokens = {
  access_token: string;
  refresh_token: string;
};

// expo-secure-store n'a pas d'implémentation web (Keychain/Keystore n'existent pas dans un
// navigateur) — bascule sur localStorage sur cette plateforme uniquement. Le natif (iOS/
// Android, cible réelle de cette app) garde le stockage sécurisé.
async function getItem(key: string): Promise<string | null> {
  if (Platform.OS === "web") return window.localStorage.getItem(key);
  return SecureStore.getItemAsync(key);
}

async function setItem(key: string, value: string): Promise<void> {
  if (Platform.OS === "web") {
    window.localStorage.setItem(key, value);
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

async function deleteItem(key: string): Promise<void> {
  if (Platform.OS === "web") {
    window.localStorage.removeItem(key);
    return;
  }
  await SecureStore.deleteItemAsync(key);
}

function isStoredTokens(value: unknown): value is StoredTokens {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as StoredTokens).access_token === "string" &&
    typeof (value as StoredTokens).refresh_token === "string"
  );
}

async function readTokens(key: string): Promise<StoredTokens | null> {
  const raw = await getItem(key);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    return isStoredTokens(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export async function getStoredTokens(): Promise<StoredTokens | null> {
  const current = await readTokens(STORAGE_KEY);
  if (current) return current;

  const legacy = await readTokens(LEGACY_STORAGE_KEY);
  if (legacy) {
    await setItem(STORAGE_KEY, JSON.stringify(legacy));
    await deleteItem(LEGACY_STORAGE_KEY);
    return legacy;
  }

  return null;
}

export async function setStoredTokens(tokens: StoredTokens): Promise<void> {
  await setItem(STORAGE_KEY, JSON.stringify(tokens));
}

export async function clearStoredTokens(): Promise<void> {
  await deleteItem(STORAGE_KEY);
  await deleteItem(LEGACY_STORAGE_KEY);
}
