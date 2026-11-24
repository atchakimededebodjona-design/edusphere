"use client";

import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { toErrorMessage } from "@/lib/api/useAsyncData";
import {
  FRAME_RATIO,
  MAX_ZOOM,
  MIN_ZOOM,
  OUTPUT_HEIGHT,
  OUTPUT_WIDTH,
  centeredPosition,
  clampPosition,
  positionAfterZoom,
  sourceRect,
} from "@/lib/photos/passport.mjs";
import { photoFileProblem } from "@/lib/photos/client";

type Source = { url: string; image: HTMLImageElement };

const FRAME_WIDTH = 252;
const FRAME = { width: FRAME_WIDTH, height: Math.round(FRAME_WIDTH / FRAME_RATIO) };

function loadImage(file: File): Promise<Source> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => resolve({ url, image });
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("unreadable"));
    };
    image.src = url;
  });
}

function toJpeg(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("canvas"))), "image/jpeg", 0.88),
  );
}

/**
 * Deux façons de mettre une photo d'identité (2026-11-19) :
 * - « Prendre une photo » : appareil photo du téléphone (galerie sur ordinateur), puis cadrage au
 *   format passeport 35 × 45 (déplacer, agrandir) ; la partie cadrée part en JPEG 700 × 900 ;
 * - « Choisir un fichier » : image déjà prête (JPEG, PNG, WebP, 5 Mio au plus), envoyée telle quelle.
 * `capture` : « user » (caméra de face, sa propre photo) ou « environment » (caméra arrière).
 */
export function PassportPhotoPicker({
  onPhoto,
  capture,
  disabled = false,
}: {
  onPhoto: (file: File) => Promise<unknown>;
  capture: "user" | "environment";
  disabled?: boolean;
}) {
  const cameraInput = useRef<HTMLInputElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [zoom, setZoom] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const drag = useRef<{ pointerId: number; startX: number; startY: number; from: { x: number; y: number } } | null>(null);

  useEffect(() => {
    return () => {
      if (source) URL.revokeObjectURL(source.url);
    };
  }, [source]);

  const size = source ? { width: source.image.naturalWidth, height: source.image.naturalHeight } : null;

  async function send(file: File) {
    setBusy(true);
    setError(null);
    try {
      await onPhoto(file);
      setSource(null);
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function onCamera(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError(null);
    try {
      const loaded = await loadImage(file);
      const natural = { width: loaded.image.naturalWidth, height: loaded.image.naturalHeight };
      setZoom(1);
      setPosition(centeredPosition(natural, FRAME, 1));
      setSource(loaded);
    } catch {
      setError("Image illisible. Reprenez la photo, ou choisissez un fichier JPEG, PNG ou WebP.");
    }
  }

  function onFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const problem = photoFileProblem(file);
    if (problem) {
      setError(problem);
      return;
    }
    void send(file);
  }

  function onZoom(next: number) {
    if (!size) return;
    setPosition((current) => positionAfterZoom(size, FRAME, zoom, next, current));
    setZoom(next);
  }

  function onPointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, from: position };
  }

  function onPointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId || !size) return;
    setPosition(
      clampPosition(size, FRAME, zoom, {
        x: current.from.x + event.clientX - current.startX,
        y: current.from.y + event.clientY - current.startY,
      }),
    );
  }

  async function validate() {
    if (!source || !size) return;
    const canvas = document.createElement("canvas");
    canvas.width = OUTPUT_WIDTH;
    canvas.height = OUTPUT_HEIGHT;
    const context = canvas.getContext("2d");
    if (!context) {
      setError("Cadrage impossible sur ce navigateur : choisissez plutôt un fichier.");
      return;
    }
    const { sx, sy, sw, sh } = sourceRect(size, FRAME, zoom, position);
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, OUTPUT_WIDTH, OUTPUT_HEIGHT);
    context.imageSmoothingQuality = "high";
    context.drawImage(source.image, sx, sy, sw, sh, 0, 0, OUTPUT_WIDTH, OUTPUT_HEIGHT);
    try {
      const blob = await toJpeg(canvas);
      await send(new File([blob], "photo-passeport.jpg", { type: "image/jpeg" }));
    } catch {
      setError("Cadrage impossible sur ce navigateur : choisissez plutôt un fichier.");
    }
  }

  const scale = size ? Math.max(FRAME.width / size.width, FRAME.height / size.height) * zoom : 1;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={disabled || busy}
          onClick={() => cameraInput.current?.click()}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10"
        >
          📷 Prendre une photo
        </button>
        <button
          type="button"
          disabled={disabled || busy}
          onClick={() => fileInput.current?.click()}
          className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10"
        >
          Choisir un fichier
        </button>
        {busy && !source && <span className="self-center text-sm text-slate-600">Envoi...</span>}
      </div>
      <input
        ref={cameraInput}
        type="file"
        accept="image/*"
        capture={capture}
        onChange={onCamera}
        className="hidden"
        data-testid="photo-camera-input"
      />
      <input
        ref={fileInput}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        onChange={onFile}
        className="hidden"
        data-testid="photo-file-input"
      />
      {error && !source && (
        <p role="alert" className="text-sm text-red-700" data-testid="photo-error">
          {error}
        </p>
      )}

      {source && size && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/70 p-4" role="dialog" aria-modal="true" aria-label="Cadrer la photo">
          <div className="flex w-full max-w-sm flex-col items-center gap-3 rounded-xl bg-white p-4 shadow-xl">
            <p className="text-center text-sm font-medium text-slate-900">
              Cadrez la photo : le visage dans l&apos;ovale, les épaules en bas.
            </p>
            <div
              data-testid="passport-frame"
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={() => (drag.current = null)}
              onPointerCancel={() => (drag.current = null)}
              className="relative touch-none select-none overflow-hidden rounded bg-slate-100"
              style={{ width: FRAME.width, height: FRAME.height, cursor: "grab" }}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={source.url}
                alt=""
                draggable={false}
                className="pointer-events-none absolute left-0 top-0 max-w-none origin-top-left"
                style={{
                  width: size.width,
                  height: size.height,
                  transform: `translate(${position.x}px, ${position.y}px) scale(${scale})`,
                }}
              />
              <div
                aria-hidden="true"
                className="pointer-events-none absolute left-1/2 top-[12%] h-[62%] w-[62%] -translate-x-1/2 rounded-[50%] border-2 border-dashed border-white/90 shadow-[0_0_0_9999px_rgba(15,23,42,0.35)]"
              />
            </div>
            <label className="flex w-full items-center gap-2 text-sm text-slate-700">
              Zoom
              <input
                type="range"
                min={MIN_ZOOM}
                max={MAX_ZOOM}
                step={0.01}
                value={zoom}
                onChange={(event) => onZoom(Number(event.target.value))}
                className="flex-1"
                aria-label="Zoom"
              />
            </label>
            <p className="text-center text-xs text-slate-600">Faites glisser la photo pour la déplacer.</p>
            {error && (
              <p role="alert" className="text-sm text-red-700">
                {error}
              </p>
            )}
            <div className="flex flex-wrap justify-center gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => void validate()}
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-primary-600 px-4 text-sm font-medium text-white hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10"
              >
                {busy ? "Envoi..." : "Valider la photo"}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => cameraInput.current?.click()}
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:cursor-not-allowed disabled:opacity-50 sm:min-h-10"
              >
                Reprendre
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => setSource(null)}
                className="px-2 py-2 text-sm text-slate-600 underline disabled:opacity-50"
              >
                Annuler
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
