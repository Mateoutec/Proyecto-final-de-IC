import { Camera as CameraIcon, Fingerprint, Keyboard, Moon, RefreshCw, RotateCw, Settings2, Sun, Volume2, VolumeX } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CameraPreview } from "../components/CameraPreview";
import { Button, Modal, cx } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { readPref, resolvedTheme, toggleTheme, writePref } from "../lib/theme";
import type { KioskStatus, SessionView } from "../lib/types";
import { useCamera } from "../lib/useCamera";
import { CAMERA_ERROR, Clock, OFFLINE, Overlay, ResultTicket, StatePanel, describe, type DisplayState } from "./parts";
import { chime, unlockAudio } from "./sound";

const FRAME_MS = 200; // ~5 fps
const RESULT_MS = 4000;
const RESULT_SUMMARY_MS = 6500; // más tiempo para leer «Tu semana»
const resultMs = (v: SessionView | null) => (v?.result?.summary ? RESULT_SUMMARY_MS : RESULT_MS);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function KioskPage() {
  const [deviceId, setDeviceId] = useState<string | null>(() => readPref("asistencia.camera", "") || null);
  const cam = useCamera(deviceId);
  const { capture, status: camStatus } = cam;
  const [status, setStatus] = useState<KioskStatus | null>(null);
  const [view, setView] = useState<SessionView | null>(null);
  const [phase, setPhase] = useState<"live" | "result">("live");
  const [offline, setOffline] = useState<string | null>(null);
  const [codeOpen, setCodeOpen] = useState(false);
  const [camPickerOpen, setCamPickerOpen] = useState(false);
  const [simOpen, setSimOpen] = useState(false);
  const [sound, setSound] = useState(() => readPref("asistencia.sound", "on") === "on");
  const [theme, setTheme] = useState(resolvedTheme());
  const sessionRef = useRef<SessionView | null>(null);
  const soundRef = useRef(sound);
  const resetTimer = useRef<number | undefined>(undefined);
  soundRef.current = sound;

  useEffect(() => {
    document.title = "Asistencia · Kiosco";
    let alive = true;
    const load = () =>
      api<KioskStatus>("/api/kiosk/status")
        .then((s) => {
          if (!alive) return;
          setStatus(s);
          setOffline(null);
        })
        .catch((e: Error) => alive && setOffline(e.message));
    load();
    const t = setInterval(load, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const startSession = useCallback(async (code?: string) => {
    const v = await api<SessionView>("/api/kiosk/sessions", { method: "POST", json: code ? { code } : {} });
    sessionRef.current = v;
    setView(v);
    setPhase("live");
    return v;
  }, []);

  const handleView = useCallback(
    (v: SessionView) => {
      if (sessionRef.current && sessionRef.current.id !== v.id) return;
      const wasTerminal = sessionRef.current?.terminal;
      sessionRef.current = v;
      setView(v);
      if (v.state === "need_code") setCodeOpen(true);
      if (v.terminal && !wasTerminal) {
        setPhase("result");
        setCodeOpen(false);
        if (soundRef.current) chime(v.state === "success" ? "ok" : v.state === "already_registered" ? "info" : "error");
        window.clearTimeout(resetTimer.current);
        resetTimer.current = window.setTimeout(() => {
          startSession().catch((e: Error) => setOffline(e.message));
        }, resultMs(v));
      }
    },
    [startSession],
  );

  useEffect(() => () => window.clearTimeout(resetTimer.current), []);

  // Bucle de frames: captura -> POST -> muestra el estado que decide el backend.
  useEffect(() => {
    if (camStatus !== "ready") return;
    let alive = true;
    (async () => {
      while (alive) {
        const t0 = performance.now();
        try {
          let s = sessionRef.current;
          if (!s) s = await startSession();
          if (!s.terminal && s.state !== "need_code") {
            const blob = await capture(640, 0.82);
            if (blob && alive) {
              const v = await api<SessionView>(`/api/kiosk/sessions/${s.id}/frames`, {
                method: "POST",
                body: blob,
                headers: { "Content-Type": "image/jpeg" },
              });
              if (alive) handleView(v);
            }
          }
          if (alive) setOffline(null);
        } catch (e) {
          if (e instanceof ApiError && e.code === "session_expired") {
            sessionRef.current = null;
          } else if (alive) {
            setOffline((e as Error).message);
            await sleep(1500);
          }
        }
        await sleep(Math.max(0, FRAME_MS - (performance.now() - t0)));
      }
    })();
    return () => {
      alive = false;
    };
  }, [camStatus, capture, startSession, handleView]);

  // Lector AS608 (v2): espera una huella mientras la sesión está activa.
  const scanEnabled = status?.fingerprint.scan_enabled ?? false;
  useEffect(() => {
    if (!scanEnabled) return;
    let alive = true;
    (async () => {
      while (alive) {
        const s = sessionRef.current;
        if (s && !s.terminal && (s.state === "waiting" || s.state === "detecting")) {
          try {
            const v = await api<SessionView>(`/api/kiosk/sessions/${s.id}/fingerprint/scan`, { method: "POST" });
            if (alive && v.fingerprint?.status !== "no_finger") handleView(v);
          } catch {
            await sleep(2000);
          }
        } else {
          await sleep(500);
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [scanEnabled, handleView]);

  const cameraProblem = cam.status === "denied" || cam.status === "nodevice" || cam.status === "busy" || cam.status === "error" || cam.status === "unsupported";
  let display: DisplayState = describe(view);
  if (cameraProblem) display = CAMERA_ERROR;
  else if (offline && phase === "live") display = { ...OFFLINE, hint: offline };
  else if (status && !status.engine.ready)
    display = { ...CAMERA_ERROR, key: "engine", title: "Reconocimiento no disponible", hint: status.engine.error ?? "Avisa a RR.HH." };
  else if (cam.status === "starting" || cam.status === "idle") display = { ...describe(null), title: "Abriendo la cámara", hint: "Un momento" };

  const aspect = cam.dims ? cam.dims.w / cam.dims.h : 16 / 9;
  // Una imagen vertical se muestra completa (sin recortar arriba y abajo) en el escenario apaisado.
  const fit = aspect < 1 ? "contain" : "cover";
  const live = phase === "live" && !cameraProblem;

  const toggleSound = () => {
    const next = !sound;
    setSound(next);
    writePref("asistencia.sound", next ? "on" : "off");
    if (next) {
      unlockAudio();
      chime("info");
    }
  };

  return (
    <div className="flex min-h-full flex-col bg-bg text-fg" onPointerDown={unlockAudio}>
      <header className="flex flex-wrap items-center gap-3 px-4 pt-4 lg:px-6">
        <div className="flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="size-9" />
          <div className="leading-tight">
            <p className="font-display text-xl font-semibold">Asistencia</p>
            <p className="text-sm text-muted">Marca tu entrada y tu salida</p>
          </div>
        </div>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <span
            className="inline-flex h-10 items-center gap-2 rounded-full bg-surface-2 px-4 text-sm"
            role="status"
            title={status?.fingerprint.provider === "disabled" ? "La huella se conectará en la v2" : undefined}
          >
            <Fingerprint className={cx("size-4", status?.fingerprint.connected ? "text-in" : "text-muted")} aria-hidden />
            <span>
              Huella: <span className="font-medium">{status?.fingerprint.label ?? "…"}</span>
            </span>
          </span>
          {status?.fingerprint.simulated && (
            <Button onClick={() => setSimOpen(true)} icon={<Fingerprint className="size-4" aria-hidden />}>
              Simular huella
            </Button>
          )}
          <Button onClick={() => setCamPickerOpen(true)} icon={<Settings2 className="size-4" aria-hidden />} aria-label="Elegir cámara">
            Cámara
          </Button>
          <Button onClick={toggleSound} aria-pressed={sound} aria-label={sound ? "Desactivar sonido" : "Activar sonido"} icon={sound ? <Volume2 className="size-4" aria-hidden /> : <VolumeX className="size-4" aria-hidden />} />
          <Button
            onClick={() => setTheme(toggleTheme())}
            aria-label={theme === "dark" ? "Usar tema claro" : "Usar tema oscuro"}
            icon={theme === "dark" ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
          />
          <Link to="/admin" className="inline-flex h-10 items-center rounded-lg px-3 text-sm text-muted underline-offset-4 hover:text-fg hover:underline">
            Panel RR.HH.
          </Link>
        </div>
      </header>

      <main className="grid flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-[minmax(0,3fr)_minmax(360px,2fr)] lg:gap-6 lg:p-6">
        <section aria-label="Vista de la cámara" className="relative min-h-[52vh] overflow-hidden rounded-[28px] bg-stage lg:min-h-0">
          <CameraPreview cam={cam} fit={fit} testId="kiosk-video" />
          {!cameraProblem && (
            <Overlay
              aspect={aspect}
              fit={fit}
              tone={display.tone}
              faceBox={live ? (view?.face_box ?? null) : null}
              progress={view?.state === "challenge" ? (view.challenge?.progress ?? 0) : view?.state === "detecting" ? Math.max(view.progress, 0.04) : 1}
              challenge={live && view?.state === "challenge" ? view.challenge : null}
            />
          )}
          {live && view?.state === "detecting" && fit === "cover" && (
            <div className="pointer-events-none absolute inset-x-[30%] top-[14%] bottom-[18%] overflow-hidden rounded-full opacity-40" aria-hidden>
              <div className="scanline h-1/3 w-full bg-gradient-to-b from-transparent via-[#9cc2ff]/50 to-transparent" />
            </div>
          )}
          {cameraProblem && <CameraHelp status={cam.status} error={cam.error} onRetry={cam.retry} onPick={() => setCamPickerOpen(true)} />}
          {phase === "result" && view && <ResultTicket view={view} durationMs={resultMs(view)} />}
          {live && (
            <p className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-[#050c17]/90 to-transparent px-6 pb-5 pt-14 text-center text-2xl font-medium text-white">
              {display.hint}
            </p>
          )}
        </section>

        <aside className="flex flex-col gap-5">
          <Clock />
          <StatePanel
            state={display}
            progress={view?.state === "detecting" ? view.progress : undefined}
            challenge={view?.state === "challenge" ? view.challenge : null}
          />
          {view?.candidate && view.state !== "success" && (
            <p className="rounded-2xl border border-border bg-surface px-5 py-3 text-lg">
              Verificando a <span className="font-semibold">{view.candidate.first_name}</span> (código {view.candidate.code})
            </p>
          )}
          <div className="mt-auto flex flex-wrap gap-3">
            <Button size="lg" variant="primary" onClick={() => setCodeOpen(true)} icon={<Keyboard className="size-6" aria-hidden />} disabled={phase === "result"}>
              Ingresar código
            </Button>
            {status && status.enrolled_people > 0 && (
              <p className="self-center text-sm text-muted">
                {status.enrolled_people} {status.enrolled_people === 1 ? "persona enrolada" : "personas enroladas"}
                {status.liveness_enabled ? ", prueba de vida activa" : ""}
              </p>
            )}
          </div>
        </aside>
      </main>

      <CodeDialog
        open={codeOpen}
        reason={view?.state === "need_code" ? view.hint : null}
        onClose={() => setCodeOpen(false)}
        onSubmit={async (code) => {
          const s = sessionRef.current;
          const v =
            s && !s.terminal
              ? await api<SessionView>(`/api/kiosk/sessions/${s.id}/code`, { method: "POST", json: { code } })
              : await startSession(code);
          handleView(v);
          setCodeOpen(false);
        }}
      />
      <CameraPicker
        open={camPickerOpen}
        onClose={() => setCamPickerOpen(false)}
        devices={cam.devices}
        activeId={cam.activeId}
        rotation={cam.rotation}
        onRotate={cam.rotate}
        onPick={(id) => {
          setDeviceId(id);
          writePref("asistencia.camera", id ?? "");
          setCamPickerOpen(false);
        }}
      />
      {status?.fingerprint.simulated && (
        <SimulatedFingerprint
          open={simOpen}
          onClose={() => setSimOpen(false)}
          onSimulate={async (personId, level) => {
            const s = sessionRef.current ?? (await startSession());
            const v = await api<SessionView>(`/api/kiosk/sessions/${s.id}/fingerprint/simulate`, {
              method: "POST",
              json: { person_id: personId, level },
            });
            handleView(v);
            setSimOpen(false);
          }}
        />
      )}
    </div>
  );
}

function CameraHelp({ status, error, onRetry, onPick }: { status: string; error: string | null; onRetry: () => void; onPick: () => void }) {
  const messages: Record<string, string> = {
    denied: "El navegador no tiene permiso para usar la cámara.",
    nodevice: "No se encontró ninguna cámara (o la elegida ya no está conectada).",
    busy: "Otra aplicación está usando la cámara (Zoom, FaceTime, Teams…). Ciérrala y reintenta.",
    unsupported: "Este navegador no permite usar la cámara. Usa Chrome, Edge o Safari actualizados en http://localhost:8000.",
    error: "La cámara dejó de responder.",
  };
  return (
    <div className="absolute inset-0 overflow-y-auto bg-stage p-6 text-white lg:p-10">
      <div className="mx-auto max-w-2xl">
        <CameraIcon className="size-10 text-[#ff8a8a]" aria-hidden />
        <h2 className="mt-3 font-display text-3xl font-semibold">{messages[status] ?? messages.error}</h2>
        {status === "denied" && (
          <ol className="mt-5 list-decimal space-y-2 pl-6 text-lg text-white/90">
            <li>En Chrome, haz clic en el ícono de cámara (o del candado) de la barra de direcciones y elige "Permitir".</li>
            <li>En Safari: menú Safari → Configuración → Sitios web → Cámara → localhost → Permitir.</li>
            <li>
              Si sigue bloqueada, en macOS abre Configuración del Sistema → Privacidad y seguridad → Cámara y activa tu navegador. Después reinícialo.
            </li>
          </ol>
        )}
        {error && <p className="mt-4 text-sm text-white/60">Detalle técnico: {error}</p>}
        <div className="mt-6 flex flex-wrap gap-3">
          <Button variant="primary" onClick={onRetry} icon={<RefreshCw className="size-4" aria-hidden />}>
            Reintentar
          </Button>
          <Button onClick={onPick}>Elegir otra cámara</Button>
        </div>
      </div>
    </div>
  );
}

function CodeDialog({
  open,
  reason,
  onClose,
  onSubmit,
}: {
  open: boolean;
  reason: string | null;
  onClose: () => void;
  onSubmit: (code: string) => Promise<void>;
}) {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open) {
      setCode("");
      setError(null);
    }
  }, [open]);
  return (
    <Modal open={open} title="Ingresar código" onClose={onClose}>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (!code.trim()) return setError("Escribe tu código de estudiante");
          setBusy(true);
          setError(null);
          try {
            await onSubmit(code.trim());
          } catch (err) {
            setError((err as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {reason && <p className="mb-3 text-muted">{reason}</p>}
        <label htmlFor="kiosk-code" className="text-sm font-medium">
          Código de estudiante
        </label>
        <input
          id="kiosk-code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          autoComplete="off"
          autoCapitalize="characters"
          className="mt-1.5 h-16 w-full rounded-xl border border-border bg-surface px-4 font-mono text-3xl tracking-wider"
          aria-invalid={!!error}
          aria-describedby={error ? "kiosk-code-error" : undefined}
        />
        {error && (
          <p id="kiosk-code-error" className="mt-2 text-danger" role="alert">
            {error}
          </p>
        )}
        <p className="mt-3 text-sm text-muted">Después mira a la cámara: verificaremos que tu rostro coincida con el código.</p>
        <div className="mt-5 flex justify-end gap-2">
          <Button onClick={onClose}>Cancelar</Button>
          <Button type="submit" variant="primary" loading={busy}>
            Continuar
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function CameraPicker({
  open,
  onClose,
  devices,
  activeId,
  rotation,
  onRotate,
  onPick,
}: {
  open: boolean;
  onClose: () => void;
  devices: MediaDeviceInfo[];
  activeId: string | null;
  rotation: number;
  onRotate: () => void;
  onPick: (id: string | null) => void;
}) {
  return (
    <Modal open={open} title="Elegir cámara" onClose={onClose}>
      {devices.length === 0 ? (
        <p className="text-muted">No hay cámaras disponibles todavía. Da permiso de cámara al navegador y vuelve a abrir esta lista.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {devices.map((d, i) => (
            <li key={d.deviceId || i}>
              <button
                type="button"
                onClick={() => onPick(d.deviceId || null)}
                className={cx(
                  "flex w-full cursor-pointer items-center gap-3 rounded-xl border px-4 py-3 text-left hover:bg-surface-2",
                  d.deviceId === activeId ? "border-primary bg-surface-2" : "border-border",
                )}
                aria-current={d.deviceId === activeId}
              >
                <CameraIcon className="size-5 text-muted" aria-hidden />
                <span className="flex-1">{d.label || `Cámara ${i + 1}`}</span>
                {d.deviceId === activeId && <span className="text-sm font-medium text-in">En uso</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {activeId && (
        <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-border pt-4">
          <Button onClick={onRotate} icon={<RotateCw className="size-4" aria-hidden />}>
            Girar imagen
          </Button>
          <p className="flex-1 text-sm text-muted">
            Úsalo si te ves de lado o de cabeza (por ejemplo, con un celular en vertical). Giro actual: <span className="tnum">{rotation}°</span>.
          </p>
        </div>
      )}
      <p className="mt-4 text-sm text-muted">
        En macOS puede aparecer la cámara del iPhone (Continuity Camera). Para el kiosco elige la cámara integrada de la MacBook.
      </p>
    </Modal>
  );
}

function SimulatedFingerprint({
  open,
  onClose,
  onSimulate,
}: {
  open: boolean;
  onClose: () => void;
  onSimulate: (personId: number | null, level: "high" | "medium" | "none" | "bad_image") => Promise<void>;
}) {
  const [people, setPeople] = useState<{ id: number; code: string; full_name: string }[]>([]);
  const [personId, setPersonId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    api<{ id: number; code: string; full_name: string }[]>("/api/kiosk/fingerprint/people")
      .then((list) => {
        setPeople(list);
        setPersonId((p) => p ?? list[0]?.id ?? null);
      })
      .catch((e: Error) => setError(e.message));
  }, [open]);
  const run = async (level: "high" | "medium" | "none" | "bad_image") => {
    setBusy(true);
    setError(null);
    try {
      await onSimulate(level === "none" || level === "bad_image" ? null : personId, level);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal open={open} title="Simular huella (pruebas)" onClose={onClose}>
      <p className="text-sm text-muted">
        Solo visible con FINGERPRINT_PROVIDER=simulated. Prueba la lógica multimodal sin el lector AS608.
      </p>
      <label htmlFor="sim-person" className="mt-4 block text-sm font-medium">
        Persona
      </label>
      <select
        id="sim-person"
        className="mt-1.5 h-11 w-full rounded-lg border border-border bg-surface px-3"
        value={personId ?? ""}
        onChange={(e) => setPersonId(Number(e.target.value))}
      >
        {people.map((p) => (
          <option key={p.id} value={p.id}>
            {p.full_name} ({p.code})
          </option>
        ))}
      </select>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        <Button variant="primary" loading={busy} onClick={() => run("high")} disabled={!personId}>
          Confianza alta (marca por huella)
        </Button>
        <Button loading={busy} onClick={() => run("medium")} disabled={!personId}>
          Confianza media (pide rostro 1:1)
        </Button>
        <Button loading={busy} onClick={() => run("none")}>
          Sin coincidencia
        </Button>
        <Button loading={busy} onClick={() => run("bad_image")}>
          Imagen deficiente
        </Button>
      </div>
      {error && (
        <p className="mt-3 text-danger" role="alert">
          {error}
        </p>
      )}
    </Modal>
  );
}
