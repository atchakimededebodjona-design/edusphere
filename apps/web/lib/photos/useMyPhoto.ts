"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth/useAuth";
import { MY_PHOTO_EVENT, MY_PHOTO_PATH, type MyPhotoDetail } from "@/lib/photos/client";

/** Photo du compte connecté : adresse à lire (null sans photo) et version, mise à jour dès qu'elle
 * change dans « Mon profil » (événement MY_PHOTO_EVENT), sans recharger la page. */
export function useMyPhoto(): { path: string | null; version: number } {
  const { user } = useAuth();
  const [state, setState] = useState<{ hasPhoto: boolean; version: number }>({ hasPhoto: false, version: 0 });

  useEffect(() => {
    setState((current) => ({ ...current, hasPhoto: Boolean(user?.has_photo) }));
  }, [user?.id, user?.has_photo]);

  useEffect(() => {
    const onChange = (event: Event) => {
      const detail = (event as CustomEvent<MyPhotoDetail>).detail;
      setState({ hasPhoto: detail.hasPhoto, version: detail.version });
    };
    window.addEventListener(MY_PHOTO_EVENT, onChange);
    return () => window.removeEventListener(MY_PHOTO_EVENT, onChange);
  }, []);

  return { path: state.hasPhoto ? MY_PHOTO_PATH : null, version: state.version };
}
