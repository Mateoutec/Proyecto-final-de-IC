import {
  ArrowLeft,
  ArrowRight,
  CameraOff,
  CalendarDays,
  Clock3,
  Fingerprint,
  Keyboard,
  LogIn,
  LogOut,
  ScanFace,
  ShieldAlert,
  TriangleAlert,
  UserX,
  Users,
  WifiOff,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { cx } from "../components/ui";
import { METHOD_LABEL } from "../lib/format";
import type { PersonalSummary, SessionView } from "../lib/types";

export type Tone = "neutral" | "info" | "in" | "out" | "danger" | "warn";

export interface DisplayState {
  key: string;
  icon: ReactNode;
  tone: Tone;
  title: string;
  hint: string;
}

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-fg",
  info: "text-info",
  in: "text-in",
  out: "text-out",
  danger: "text-danger",
  warn: "text-warn",
};
const TONE_SOFT: Record<Tone, string> = {
  neutral: "bg-surface-2",
  info: "bg-info-soft",
  in: "bg-in-soft",
  out: "bg-out-soft",
  danger: "bg-danger-soft",
  warn: "bg-warn-soft",
};
export const TONE_STROKE: Record<Tone, string> = {
  neutral: "rgba(255,255,255,0.85)",
  info: "#9cc2ff",
  in: "#3fd9a2",
  out: "#f7b84b",
  danger: "#ff8a8a",
  warn: "#f2cc60",
};

const icon = (node: ReactNode) => node;

export function describe(view: SessionView | null): DisplayState {
  if (!view) return { key: "waiting", icon: icon(<ScanFace />), tone: "neutral", title: "Preparando", hint: "Iniciando la sesión" };
  const base = { title: view.title, hint: view.hint };
  switch (view.state) {
    case "waiting":
      return { key: "waiting", icon: <ScanFace />, tone: "neutral", ...base };
    case "detecting":
      return { key: "detecting", icon: <ScanFace />, tone: "info", ...base };
    case "challenge":
      return {
        key: "challenge",
        icon: view.challenge?.direction === "right" ? <ArrowRight /> : <ArrowLeft />,
        tone: "info",
        title: "Prueba de vida",
        hint: view.hint,
      };
    case "need_code":
      return { key: "need_code", icon: <Keyboard />, tone: "info", ...base };
    case "success": {
      const exit = view.result?.event_type === "SALIDA";
      return { key: exit ? "exit" : "entry", icon: exit ? <LogOut /> : <LogIn />, tone: exit ? "out" : "in", ...base };
    }
    case "already_registered":
      return { key: "already", icon: <Clock3 />, tone: "info", ...base };
    case "not_recognized":
      return { key: "not_recognized", icon: <UserX />, tone: "danger", ...base };
    case "liveness_failed":
      return { key: "liveness_failed", icon: <ShieldAlert />, tone: "danger", ...base };
    case "no_enrolled":
      return { key: "no_enrolled", icon: <Users />, tone: "warn", ...base };
    default:
      return { key: "error", icon: <TriangleAlert />, tone: "danger", ...base };
  }
}

export const CAMERA_ERROR: DisplayState = {
  key: "camera_error",
  icon: <CameraOff />,
  tone: "danger",
  title: "Error de cámara",
  hint: "Revisa el permiso o elige otra cámara",
};

export const OFFLINE: DisplayState = {
  key: "offline",
  icon: <WifiOff />,
  tone: "danger",
  title: "Sin conexión con el servidor",
  hint: "Reintentando…",
};

export function StatePanel({ state, progress, challenge }: { state: DisplayState; progress?: number; challenge?: SessionView["challenge"] }) {
  return (
    <div className={cx("rounded-3xl border border-border p-6 transition-colors duration-200 lg:p-7", TONE_SOFT[state.tone])} aria-live="polite">
      <div className="flex items-start gap-4">
        <span className={cx("grid size-16 shrink-0 place-items-center rounded-2xl bg-surface [&_svg]:size-9", TONE_TEXT[state.tone])} aria-hidden>
          {state.icon}
        </span>
        <div className="min-w-0">
          <p className={cx("font-display text-3xl font-semibold leading-tight xl:text-4xl", TONE_TEXT[state.tone])}>{state.title}</p>
          <p className="mt-1.5 text-xl leading-snug text-fg">{state.hint}</p>
        </div>
      </div>
      {challenge ? (
        <div className="mt-5" aria-label="Tiempo restante de la prueba de vida">
          <div className="flex justify-between text-sm text-muted">
            <span>Giro detectado</span>
            <span className="tnum">{Math.ceil(challenge.remaining_seconds)} s</span>
          </div>
          <div className="mt-1.5 h-2.5 overflow-hidden rounded-full bg-surface">
            <div className="h-full rounded-full bg-info transition-[width] duration-200" style={{ width: `${Math.round(challenge.progress * 100)}%` }} />
          </div>
        </div>
      ) : progress !== undefined && progress > 0 ? (
        <div className="mt-5 h-2.5 overflow-hidden rounded-full bg-surface" aria-label="Progreso de identificación">
          <div className="h-full rounded-full bg-info transition-[width] duration-200" style={{ width: `${Math.round(progress * 100)}%` }} />
        </div>
      ) : null}
    </div>
  );
}

export function Clock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const hh = String(now.getHours()).padStart(2, "0");
  const mm = String(now.getMinutes()).padStart(2, "0");
  const ss = String(now.getSeconds()).padStart(2, "0");
  const date = new Intl.DateTimeFormat("es", { weekday: "long", day: "numeric", month: "long" }).format(now);
  return (
    <div>
      <p className="tnum font-display text-[clamp(5.5rem,11vw,10rem)] font-semibold leading-none" aria-label={`Son las ${hh}:${mm}`}>
        {hh}
        <span className="opacity-60">:</span>
        {mm}
        <span className="ml-3 align-top text-[0.3em] font-medium text-muted">{ss}</span>
      </p>
      <p className="mt-3 text-2xl text-muted first-letter:uppercase">{date}</p>
    </div>
  );
}

/** Guía ovalada + caja del rostro. Usa el mismo ajuste que el video (cover o contain). */
export function Overlay({
  aspect,
  fit = "cover",
  tone,
  faceBox,
  progress,
  challenge,
}: {
  aspect: number;
  fit?: "cover" | "contain";
  tone: Tone;
  faceBox: SessionView["face_box"];
  progress: number;
  challenge: SessionView["challenge"];
}) {
  const W = 100 * aspect;
  const H = 100;
  const cxp = W / 2;
  const cyp = H * 0.48;
  // Medido con el lado corto para que el óvalo también encaje en imágenes verticales.
  const side = Math.min(W, H);
  const rx = side * 0.26;
  const ry = side * 0.36;
  const perimeter = Math.PI * (3 * (rx + ry) - Math.sqrt((3 * rx + ry) * (rx + 3 * ry)));
  const stroke = TONE_STROKE[tone];
  let box = null;
  if (faceBox) {
    const [x, y, w, h] = faceBox;
    box = { x: W - (x + w) * W, y: y * H, w: w * W, h: h * H };
  }
  return (
    <svg
      className="pointer-events-none absolute inset-0 size-full"
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio={fit === "contain" ? "xMidYMid meet" : "xMidYMid slice"}
      aria-hidden
    >
      <defs>
        <mask id="oval-cut">
          <rect width={W} height={H} fill="white" />
          <ellipse cx={cxp} cy={cyp} rx={rx} ry={ry} fill="black" />
        </mask>
      </defs>
      <rect width={W} height={H} fill="rgba(5,12,23,0.5)" mask="url(#oval-cut)" />
      <ellipse cx={cxp} cy={cyp} rx={rx} ry={ry} fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth={0.6} />
      {/* Trazo que empieza arriba y avanza en sentido horario con el progreso. */}
      <path
        d={`M ${cxp} ${cyp - ry} A ${rx} ${ry} 0 1 1 ${cxp} ${cyp + ry} A ${rx} ${ry} 0 1 1 ${cxp} ${cyp - ry}`}
        fill="none"
        stroke={stroke}
        strokeWidth={1.1}
        strokeLinecap="round"
        strokeDasharray={`${perimeter * Math.max(progress, tone === "neutral" ? 1 : 0.02)} ${perimeter}`}
        style={{ transition: "stroke-dasharray 200ms ease, stroke 200ms ease" }}
      />
      {box && (
        <rect x={box.x} y={box.y} width={box.w} height={box.h} rx={2} fill="none" stroke={stroke} strokeOpacity={0.55} strokeWidth={0.5} strokeDasharray="3 2" />
      )}
      {challenge && (
        <g className={challenge.direction === "left" ? "nudge-left" : "nudge-right"}>
          <path
            d={
              challenge.direction === "left"
                ? `M ${cxp - rx - 6} ${cyp} l 7 -7 M ${cxp - rx - 6} ${cyp} l 7 7 M ${cxp - rx - 6} ${cyp} h 14`
                : `M ${cxp + rx + 6} ${cyp} l -7 -7 M ${cxp + rx + 6} ${cyp} l -7 7 M ${cxp + rx + 6} ${cyp} h -14`
            }
            stroke="#9cc2ff"
            strokeWidth={2.2}
            strokeLinecap="round"
            fill="none"
          />
        </g>
      )}
    </svg>
  );
}

export function ResultTicket({ view, durationMs }: { view: SessionView; durationMs: number }) {
  const r = view.result ?? {};
  const state = describe(view);
  const success = view.state === "success";
  const exit = r.event_type === "SALIDA";
  return (
    <div className="absolute inset-0 grid place-items-center bg-[#050c17]/70 p-4 backdrop-blur-[2px]" role="status" aria-live="assertive">
      <article className="relative w-full max-w-[38rem] overflow-hidden rounded-3xl bg-[#f7f8fa] text-[#0f1e33] shadow-2xl">
        {success ? (
          <div className="grid gap-5 p-6 sm:grid-cols-[11rem_1fr] sm:p-7">
            {r.photo ? (
              <img src={r.photo} alt="Captura de la marcación" className="aspect-[3/4] w-full rounded-2xl object-cover -scale-x-100 sm:w-44" />
            ) : (
              <div className="grid aspect-[3/4] w-full place-items-center rounded-2xl bg-[#e3e8ef] sm:w-44">
                <Fingerprint className="size-14 text-[#4f5e73]" aria-hidden />
              </div>
            )}
            <div className="min-w-0">
              <p className="font-display text-[2.1rem] font-semibold leading-tight">{r.person?.full_name}</p>
              <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 text-lg">
                <dt className="text-[#4f5e73]">Código</dt>
                <dd className="tnum font-medium">{r.person?.code}</dd>
                {r.person?.area ? (
                  <>
                    <dt className="text-[#4f5e73]">Área</dt>
                    <dd>{r.person.area}</dd>
                  </>
                ) : null}
              </dl>
              <div
                className={cx(
                  "stamp mt-5 inline-flex items-center gap-3 rounded-xl border-[3px] px-4 py-2",
                  exit ? "border-[#b45309] text-[#b45309]" : "border-[#047857] text-[#047857]",
                )}
              >
                {exit ? <LogOut className="size-8" aria-hidden /> : <LogIn className="size-8" aria-hidden />}
                <span className="font-display text-4xl font-bold">{r.event_type}</span>
                <span className="tnum font-display text-4xl font-bold">{r.local_time}</span>
              </div>
              {exit && r.worked_hhmm ? (
                <p className="mt-4 text-xl">
                  Jornada de <span className="tnum font-semibold">{r.worked_hhmm} h</span>{" "}
                  <span className="text-[#4f5e73]">({r.worked_hours?.toFixed(2)} h)</span>
                </p>
              ) : null}
              <p className="mt-2 text-sm text-[#4f5e73]">
                {r.method ? `Método: ${METHOD_LABEL[r.method]}` : ""}
                {r.face_score != null && r.face_threshold != null
                  ? `, similitud ${r.face_score.toFixed(3)} con umbral ${r.face_threshold.toFixed(3)}`
                  : ""}
              </p>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-5 p-7">
            <span
              className={cx(
                "grid size-16 shrink-0 place-items-center rounded-2xl [&_svg]:size-9",
                state.tone === "info" ? "bg-[#dde8fd] text-[#1d4ed8]" : "bg-[#fde3e3] text-[#b91c1c]",
              )}
              aria-hidden
            >
              {state.icon}
            </span>
            <div>
              <p className="font-display text-[2rem] font-semibold leading-tight">
                {view.state === "already_registered" && r.person ? r.person.first_name + ", ya marcaste" : state.title}
              </p>
              <p className="mt-2 text-xl">{view.hint}</p>
            </div>
          </div>
        )}
        {r.summary ? <SummaryStrip summary={r.summary} /> : null}
        <div className="h-1.5 bg-[#e3e8ef]">
          <div
            className={cx("drain h-full", success ? (exit ? "bg-[#b45309]" : "bg-[#047857]") : "bg-[#4f5e73]")}
            style={{ animationDuration: `${durationMs}ms` }}
          />
        </div>
      </article>
    </div>
  );
}

/** Perfil Usuario: su semana y sus últimas marcaciones (solo tras identificarse). */
function SummaryStrip({ summary }: { summary: PersonalSummary }) {
  const days = summary.week_days === 1 ? "1 día" : `${summary.week_days} días`;
  return (
    <section aria-label="Tu resumen de la semana" className="border-t border-[#e3e8ef] bg-white px-6 py-4 sm:px-7">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="flex items-center gap-2 text-base font-semibold">
          <CalendarDays className="size-5 text-[#4f5e73]" aria-hidden />
          Tu semana
        </p>
        <p className="text-base">
          <span className="tnum font-semibold">{days}</span>
          <span className="text-[#4f5e73]"> · </span>
          <span className="tnum font-semibold">{summary.week_hhmm} h</span>
          {summary.week_incomplete > 0 ? (
            <span className="text-[#b45309]"> · {summary.week_incomplete} sin salida</span>
          ) : null}
        </p>
      </div>
      {summary.recent.length > 0 ? (
        <ol className="mt-3 flex flex-wrap gap-2" aria-label="Últimas marcaciones">
          {summary.recent.map((m, i) => (
            <li
              key={`${m.day}-${m.time}-${i}`}
              className={cx(
                "tnum inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-sm",
                m.type === "SALIDA" ? "border-[#f3d3b0] text-[#8a4106]" : "border-[#b9e2d3] text-[#035e44]",
              )}
            >
              {m.type === "SALIDA" ? <LogOut className="size-4" aria-hidden /> : <LogIn className="size-4" aria-hidden />}
              <span className="font-medium">{m.type === "SALIDA" ? "Salida" : "Entrada"}</span>
              <span className="text-[#4f5e73]">
                {m.day} {m.time}
              </span>
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
