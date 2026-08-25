import * as SecureStore from "expo-secure-store";

const STORAGE_KEY = "edusphere.session";

export type StoredTokens = {
  access_token: string;
  refresh_token: string;
};

export async function getStoredTokens(): Promise<StoredTokens | null> {
  const raw = await SecureStore.getItemAsync(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredTokens;
  } catch {
    return null;
  }
}

export async function setStoredTokens(tokens: StoredTokens): Promise<void> {
  await SecureStore.setItemAsync(STORAGE_KEY, JSON.stringify(tokens));
}

export async function clearStoredTokens(): Promise<void> {
  await SecureStore.deleteItemAsync(STORAGE_KEY);
}
