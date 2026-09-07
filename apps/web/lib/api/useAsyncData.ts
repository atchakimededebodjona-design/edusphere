"use client";

import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";
import { ApiError } from "@/lib/api/client";

export function toErrorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Une erreur est survenue.";
}

export type AsyncDataResult<T> = {
  /** Dernière donnée obtenue avec succès. Reste peuplée pendant un `retry()` et même après un
   * échec de rechargement — jamais effacée par autre chose qu'un changement de `deps` (nouvelle
   * ressource) ou un nouveau succès. */
  data: T | null;
  /** Message du dernier chargement en échec, le cas échéant. Peut être présent en même temps
   * qu'une `data` non nulle (échec d'un rechargement, pas du premier chargement). */
  error: string | null;
  /** true uniquement le temps du tout premier chargement, avant toute donnée obtenue. */
  isLoading: boolean;
  /** true pendant un rechargement (retry ou changement de dépendance secondaire) déclenché alors
   * qu'une donnée précédente existe déjà. */
  isRefreshing: boolean;
  retry: () => void;
};

/**
 * Charge une ressource et expose data/error/retry sans jamais faire disparaître un résultat déjà
 * affiché pendant un rechargement (Phase 25.1 — corrige un défaut identifié en revue Phase 25 :
 * `retry()` remettait `data` à `null` avant de recharger, provoquant un flash "Chargement..." qui
 * faisait disparaître la liste ET le formulaire de saisie après chaque création/modification).
 *
 * - Premier chargement (aucune donnée encore obtenue) : `isLoading` true, `data` null.
 * - `retry()` (ou changement de dépendance) alors qu'une donnée existe déjà : `isRefreshing`
 *   true, `data` INCHANGÉ tant que la nouvelle requête n'a pas abouti.
 * - Succès : `data` remplacé par le nouveau résultat, `error` effacé.
 * - Échec pendant un rechargement : `data` reste l'ANCIENNE valeur, `error` prend le message —
 *   l'appelant peut afficher l'erreur tout en gardant le contenu précédent visible.
 * - Un changement des `deps` elles-mêmes (nouvelle ressource, ex. changement d'école) repart d'un
 *   chargement initial propre : `data`/`error` sont réinitialisés avant le nouveau chargement.
 *
 * `options.enabled: false` garde l'état de chargement initial sans lancer la requête, le temps
 * qu'une dépendance obligatoire soit disponible.
 */
export function useAsyncData<T>(
  fetcher: () => Promise<T>,
  deps: DependencyList,
  options?: { enabled?: boolean },
): AsyncDataResult<T> {
  const enabled = options?.enabled ?? true;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [retryToken, setRetryToken] = useState(0);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  // Miroir synchrone de `data`, lu au démarrage de l'effet de chargement pour savoir si une
  // donnée précédente existe déjà — sans ajouter `data` aux dépendances de cet effet (ce qui
  // provoquerait une boucle, l'effet lui-même appelant `setData`).
  const dataRef = useRef<T | null>(null);

  // Nouvelle ressource (changement de `deps`, pas un simple retry) : repart d'un chargement
  // initial propre plutôt que de garder affichée la donnée de la ressource précédente.
  useEffect(() => {
    setData(null);
    dataRef.current = null;
    setError(null);
    setIsLoading(true);
    setIsRefreshing(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    if (dataRef.current !== null) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }
    fetcherRef
      .current()
      .then((result) => {
        if (cancelled) return;
        dataRef.current = result;
        setData(result);
        setError(null);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(toErrorMessage(err));
      })
      .finally(() => {
        if (cancelled) return;
        setIsLoading(false);
        setIsRefreshing(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, retryToken]);

  const retry = useCallback(() => setRetryToken((c) => c + 1), []);

  return { data, error, isLoading, isRefreshing, retry };
}
