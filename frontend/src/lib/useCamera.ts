import { useCallback, useEffect, useRef, useState } from "react";
import { readPref, writePref } from "./theme";

export type CameraStatus = "idle" | "starting" | "ready" | "denied" | "nodevice" | "busy" | "error" | "unsupported";
export type Rotation = 0 | 90 | 180 | 270;

export interface Camera {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  status: CameraStatus;
  error: string | null;
  devices: MediaDeviceInfo[];
  activeId: string | null;
  /** Tamaño de la imagen ya girada. */
  dims: { w: number; h: number } | null;
  /** Giro en sentido horario para cámaras que entregan la imagen de lado (p. ej. un celular en vertical). */
  rotation: Rotation;
  rotate: () => void;
  retry: () => void;
  capture: (width?: number, quality?: number) => Promise<Blob | null>;
}

const ROTATION_PREF = "asistencia.rotation.";

function readRotation(key: string): Rotation {
  const value = Number(readPref(key, "0"));
  return value === 90 || value === 180 || value === 270 ? value : 0;
}

/**
 * Abre la cámara en el navegador (getUserMedia). Los frames capturados NO van espejados, pero sí
 * girados según `rotation`, que se recuerda por cámara.
 */
export function useCamera(deviceId: string | null, enabled = true): Camera {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [status, setStatus] = useState<CameraStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null);
  const [rotation, setRotation] = useState<Rotation>(0);
  const rotationRef = useRef<Rotation>(0);
  const rotationKey = useRef(ROTATION_PREF);
  const [attempt, setAttempt] = useState(0);
  rotationRef.current = rotation;

  useEffect(() => {
    if (!enabled) return;
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus("unsupported");
      return;
    }
    let cancelled = false;
    let stream: MediaStream | null = null;
    setStatus("starting");
    const video: MediaTrackConstraints = deviceId
      ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } }
      : { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } };
    const refreshDevices = () =>
      navigator.mediaDevices
        .enumerateDevices()
        .then((list) => !cancelled && setDevices(list.filter((d) => d.kind === "videoinput")))
        .catch(() => undefined);

    navigator.mediaDevices
      .getUserMedia({ audio: false, video })
      .then(async (s) => {
        if (cancelled) {
          s.getTracks().forEach((t) => t.stop());
          return;
        }
        stream = s;
        const track = s.getVideoTracks()[0];
        track?.addEventListener("ended", () => {
          if (!cancelled) {
            setStatus("error");
            setError("La cámara se desconectó");
          }
        });
        const el = videoRef.current;
        if (el) {
          el.srcObject = s;
          await el.play().catch(() => undefined);
          const setSize = () => el.videoWidth && setDims({ w: el.videoWidth, h: el.videoHeight });
          setSize();
          el.onloadedmetadata = setSize;
        }
        const id = track?.getSettings().deviceId ?? null;
        setActiveId(id);
        // El giro se guarda por nombre de cámara: Chrome puede cambiar el deviceId entre páginas.
        rotationKey.current = ROTATION_PREF + (track?.label || id || "");
        setRotation(readRotation(rotationKey.current));
        setStatus("ready");
        setError(null);
        refreshDevices();
      })
      .catch((e: DOMException) => {
        if (cancelled) return;
        if (e.name === "NotAllowedError" || e.name === "SecurityError") setStatus("denied");
        else if (e.name === "NotFoundError" || e.name === "OverconstrainedError") setStatus("nodevice");
        else if (e.name === "NotReadableError" || e.name === "AbortError") setStatus("busy");
        else setStatus("error");
        setError(e.message || e.name);
        refreshDevices();
      });
    navigator.mediaDevices.addEventListener?.("devicechange", refreshDevices);
    return () => {
      cancelled = true;
      navigator.mediaDevices.removeEventListener?.("devicechange", refreshDevices);
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [deviceId, attempt, enabled]);

  const capture = useCallback(
    (width = 640, quality = 0.85) =>
      new Promise<Blob | null>((resolve) => {
        const el = videoRef.current;
        if (!el || el.readyState < 2 || !el.videoWidth) return resolve(null);
        const rot = rotationRef.current;
        const sideways = rot % 180 !== 0;
        // `width` limita el ancho de la imagen ya girada.
        const scale = Math.min(width, sideways ? el.videoHeight : el.videoWidth) / (sideways ? el.videoHeight : el.videoWidth);
        const w = Math.round(el.videoWidth * scale);
        const h = Math.round(el.videoHeight * scale);
        const canvas = canvasRef.current ?? (canvasRef.current = document.createElement("canvas"));
        canvas.width = sideways ? h : w;
        canvas.height = sideways ? w : h;
        const ctx = canvas.getContext("2d");
        if (!ctx) return resolve(null);
        ctx.setTransform(1, 0, 0, 1, canvas.width / 2, canvas.height / 2);
        ctx.rotate((rot * Math.PI) / 180);
        ctx.drawImage(el, -w / 2, -h / 2, w, h);
        canvas.toBlob((b) => resolve(b), "image/jpeg", quality);
      }),
    [],
  );

  const rotate = useCallback(() => {
    const next = ((rotation + 90) % 360) as Rotation;
    setRotation(next);
    writePref(rotationKey.current, String(next));
  }, [rotation]);

  const retry = useCallback(() => setAttempt((a) => a + 1), []);
  const oriented = dims && rotation % 180 !== 0 ? { w: dims.h, h: dims.w } : dims;
  return { videoRef, status, error, devices, activeId, dims: oriented, rotation, rotate, retry, capture };
}
