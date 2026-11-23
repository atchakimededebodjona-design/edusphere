"use client";

import { useEffect, useRef, useState } from "react";
import { initials } from "@/lib/photos/passport.mjs";
import { photoObjectUrl } from "@/lib/photos/client";

const SIZES = {
  sm: "h-[46px] w-9 text-xs",
  md: "h-[72px] w-14 text-sm",
  lg: "h-36 w-28 text-2xl",
} as const;

/**
 * Photo d'identité au format passeport (35 × 45), ou les initiales sans photo. `path` : adresse de
 * l'API ; null = pas de photo (aucune requête). `lazy` : chargée seulement quand elle devient
 * visible (longues listes d'élèves sur téléphone). `version` force un nouveau chargement.
 */
export function PhotoThumb({
  path,
  name,
  size = "md",
  lazy = false,
  version = 0,
  testId,
}: {
  path: string | null;
  name: string;
  size?: keyof typeof SIZES;
  lazy?: boolean;
  version?: number;
  testId?: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(!lazy);
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!lazy || visible || !box.current) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(box.current);
    return () => observer.disconnect();
  }, [lazy, visible]);

  useEffect(() => {
    if (!path || !visible) {
      setUrl(null);
      return;
    }
    let cancelled = false;
    let created: string | null = null;
    void photoObjectUrl(path).then((objectUrl) => {
      if (cancelled) {
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        return;
      }
      created = objectUrl;
      setUrl(objectUrl);
    });
    return () => {
      cancelled = true;
      if (created) URL.revokeObjectURL(created);
    };
  }, [path, visible, version]);

  return (
    <div
      ref={box}
      data-testid={testId}
      data-has-photo={url ? "true" : "false"}
      className={`flex shrink-0 items-center justify-center overflow-hidden rounded-md bg-slate-200 font-semibold text-slate-600 ${SIZES[size]}`}
    >
      {url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={url} alt={`Photo de ${name}`} className="h-full w-full object-cover" />
      ) : (
        <span aria-hidden="true">{initials(name)}</span>
      )}
    </div>
  );
}
