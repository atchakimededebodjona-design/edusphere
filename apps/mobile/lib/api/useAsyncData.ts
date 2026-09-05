import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";
import { toUserMessage } from "@/lib/api/client";

export type AsyncState<T> =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "success"; data: T };

export type AsyncDataResult<T> = AsyncState<T> & { retry: () => void };

/**
 * Centralise le triplet Loading/Error/Success + Retry pour les écrans qui chargent des données au
 * montage (Phase 12 — évite de dupliquer, dans chaque écran, le même `.catch()` manquant et le
 * même bloc de rendu loading/erreur).
 *
 * `deps` fonctionne comme le tableau de dépendances d'un `useEffect` classique (ex. `[classId]`) :
 * un changement relance le chargement. `options.enabled: false` garde l'état "loading" sans
 * lancer la requête — utilisé le temps qu'une dépendance obligatoire (ex. `currentSchoolId`) soit
 * disponible ; ce n'est pas un cas d'erreur réseau, donc pas traité comme tel.
 */
export function useAsyncData<T>(
  fetcher: () => Promise<T>,
  deps: DependencyList,
  options?: { enabled?: boolean },
): AsyncDataResult<T> {
  const enabled = options?.enabled ?? true;
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });
  const [retryToken, setRetryToken] = useState(0);

  // Réf plutôt que dépendance directe : `fetcher` est une fermeture recréée à chaque rendu par
  // l'écran appelant ; c'est `deps` qui pilote explicitement quand relancer, pas l'identité de
  // la fonction elle-même (sinon la requête repartirait à chaque rendu, boucle indésirable).
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setState({ status: "loading" });
    fetcherRef
      .current()
      .then((data) => {
        if (!cancelled) setState({ status: "success", data });
      })
      .catch((err: unknown) => {
        if (!cancelled) setState({ status: "error", message: toUserMessage(err) });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, retryToken]);

  const retry = useCallback(() => setRetryToken((c) => c + 1), []);

  return { ...state, retry } as AsyncDataResult<T>;
}
