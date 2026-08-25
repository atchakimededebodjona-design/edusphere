import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

const STORAGE_KEY = "edusphere.session";

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

export async function getStoredTokens(): Promise<StoredTokens | null> {
  const raw = await getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredTokens;
  } catch {
    return null;
  }
}

export async function setStoredTokens(tokens: StoredTokens): Promise<void> {
  await setItem(STORAGE_KEY, JSON.stringify(tokens));
}

export async function clearStoredTokens(): Promise<void> {
  await deleteItem(STORAGE_KEY);
}
