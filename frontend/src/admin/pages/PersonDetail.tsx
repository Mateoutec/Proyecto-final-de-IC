import { ArrowLeft, Camera, CircleCheck, Fingerprint, Pencil, RotateCw, ScanFace, ShieldOff, Trash2, Upload, UserX } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { CameraPreview } from "../../components/CameraPreview";
import { Badge, Button, EmptyState, ErrorState, Lightbox, LoadingBlock, Modal, Panel, cx, useToast } from "../../components/ui";
import { ApiError, api } from "../../lib/api";
import type { PersonDetail } from "../../lib/types";
import { useAsync } from "../../lib/useAsync";
import { useCamera } from "../../lib/useCamera";
import { useAreas } from "../shared";
import { PersonFormModal } from "./People";

interface Duplicate {
  full_name: string;
  code: string;
  score: number;
  threshold: number;
}

export function PersonDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast();
  const { areas } = useAreas();
  const { data: p, error, loading, reload } = useAsync(() => api<PersonDetail>(`/api/admin/people/${id}`), [id]);
  const [editOpen, setEditOpen] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [confirm, setConfirm] = useState<null | "biometrics" | "delete">(null);
  const [photo, setPhoto] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const act = async (fn: () => Promise<unknown>, msg: string) => {
    setBusy(true);
    try {
      await fn();
      toast(msg);
      reload();
    } catch (e) {
      toast((e as Error).message, "danger");
    } finally {
      setBusy(false);
    }
  };

  const uploadFiles = async (files: FileList) => {
    setBusy(true);
    const messages: string[] = [];
    for (const file of Array.from(files)) {
      const send = (confirmDup: boolean) => {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("pose", "upload");
        fd.append("source", "upload");
        fd.append("confirm_duplicate", String(confirmDup));
        return api(`/api/admin/people/${id}/templates`, { method: "POST", body: fd });
      };
      try {
        await send(false);
        messages.push(`${file.name}: guardada`);
      } catch (e) {
        if (e instanceof ApiError && e.code === "duplicate") {
          const ok = window.confirm(`${e.message}\n\n¿Guardar la foto de todos modos?`);
          if (ok) {
            await send(true).catch((err: Error) => messages.push(`${file.name}: ${err.message}`));
            messages.push(`${file.name}: guardada (coincidencia confirmada)`);
          } else messages.push(`${file.name}: descartada`);
        } else messages.push(`${file.name}: ${(e as Error).message}`);
      }
    }
    setUploadMsg(messages.join("\n"));
    setBusy(false);
    reload();
  };

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading && !p) return <LoadingBlock rows={6} />;
  if (!p) return null;

  const activeTemplates = p.face_templates.filter((t) => t.active_engine);
  const otherTemplates = p.face_templates.filter((t) => !t.active_engine);

  return (
    <>
      <Link to="/admin/personas" className="mb-3 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft className="size-4" aria-hidden /> Personas
      </Link>
      <header className="flex flex-wrap items-start justify-between gap-4 pb-5">
        <div>
          <h1 className="font-display text-3xl font-semibold">{p.full_name}</h1>
          <p className="mt-1 text-muted">
            Código <span className="tnum font-medium text-fg">{p.code}</span>, {p.area ?? "sin área"}
            {p.position ? `, ${p.position}` : ""}
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {p.active ? <Badge tone="in">Activa</Badge> : <Badge>Desactivada</Badge>}
            {p.consent_signed ? <Badge tone="in">Consentimiento firmado {p.consent_date}</Badge> : <Badge tone="warn">Sin consentimiento</Badge>}
            {p.is_demo && <Badge tone="info">Demostración</Badge>}
          </div>
        </div>
        <Button onClick={() => setEditOpen(true)} icon={<Pencil className="size-4" aria-hidden />}>
          Editar datos
        </Button>
      </header>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Panel
          title="Rostro"
          actions={
            <div className="flex flex-wrap gap-2">
              <input
                ref={fileRef}
                type="file"
                accept="image/jpeg,image/png"
                multiple
                className="hidden"
                onChange={(e) => {
                  if (e.target.files?.length) void uploadFiles(e.target.files);
                  e.target.value = "";
                }}
              />
              <Button onClick={() => fileRef.current?.click()} disabled={!p.consent_signed || busy} icon={<Upload className="size-4" aria-hidden />}>
                Subir fotos
              </Button>
              <Button variant="primary" onClick={() => setWizardOpen(true)} disabled={!p.consent_signed || !p.active} icon={<Camera className="size-4" aria-hidden />}>
                Enrolar con cámara
              </Button>
            </div>
          }
        >
          {!p.consent_signed && (
            <p className="m-4 rounded-lg bg-warn-soft px-4 py-3 text-sm text-warn">
              Para enrolar, primero marca el consentimiento firmado en <button type="button" className="cursor-pointer font-semibold underline" onClick={() => setEditOpen(true)}>Editar datos</button>.
            </p>
          )}
          {uploadMsg && <pre className="m-4 whitespace-pre-wrap rounded-lg bg-surface-2 px-4 py-3 font-sans text-sm">{uploadMsg}</pre>}
          {activeTemplates.length === 0 ? (
            <EmptyState icon={<ScanFace className="size-8" aria-hidden />} title="Sin capturas para el motor activo">
              El enrolamiento guiado toma 5 capturas: de frente, leve giro a cada lado y con y sin lentes.
              {otherTemplates.length > 0 && " Hay capturas de otro motor: re-indexa en Configuración."}
            </EmptyState>
          ) : (
            <ul className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-3 lg:grid-cols-5">
              {activeTemplates.map((t) => (
                <li key={t.id} className="overflow-hidden rounded-lg border border-border">
                  <button type="button" className="block w-full cursor-zoom-in" onClick={() => setPhoto(t.photo_url)} aria-label={`Ampliar captura ${t.pose_label}`}>
                    <img src={t.photo_url} alt={`Captura ${t.pose_label}`} loading="lazy" className="aspect-[4/3] w-full -scale-x-100 object-cover" />
                  </button>
                  <div className="flex items-start justify-between gap-1 p-2">
                    <div className="min-w-0 text-xs">
                      <p className="truncate font-medium">{t.pose_label}</p>
                      <p className="text-muted">Calidad {t.quality.toFixed(2)}</p>
                    </div>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="px-2"
                      onClick={() => act(() => api(`/api/admin/templates/${t.id}`, { method: "DELETE" }), "Captura eliminada")}
                      icon={<Trash2 className="size-4" aria-hidden />}
                      aria-label={`Eliminar captura ${t.pose_label}`}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
          {otherTemplates.length > 0 && (
            <p className="border-t border-border px-4 py-3 text-sm text-muted">
              {otherTemplates.length} plantilla(s) de otros motores ({[...new Set(otherTemplates.map((t) => t.engine))].join(", ")}).
            </p>
          )}
        </Panel>

        <div className="flex flex-col gap-6">
          <FingerprintPanel person={p} onChanged={reload} />
          <Panel title="Privacidad y estado">
            <div className="flex flex-col gap-3 p-4">
              <p className="text-sm text-muted">{p.events_count} marcaciones registradas. Las marcaciones nunca se borran: se anulan con motivo.</p>
              <Button
                onClick={() => setConfirm("biometrics")}
                disabled={busy || (p.face_templates.length === 0 && !p.fingerprint_slot)}
                icon={<ShieldOff className="size-4" aria-hidden />}
              >
                Eliminar datos biométricos
              </Button>
              <Button
                onClick={() =>
                  act(
                    () =>
                      api(`/api/admin/people/${p.id}`, {
                        method: "PUT",
                        json: { ...p, area_id: p.area_id, active: !p.active, consent_date: p.consent_date },
                      }),
                    p.active ? "Persona desactivada" : "Persona activada",
                  )
                }
                icon={<UserX className="size-4" aria-hidden />}
              >
                {p.active ? "Desactivar" : "Activar"}
              </Button>
              {p.events_count === 0 && (
                <Button variant="danger" onClick={() => setConfirm("delete")} icon={<Trash2 className="size-4" aria-hidden />}>
                  Eliminar persona
                </Button>
              )}
            </div>
          </Panel>
        </div>
      </div>

      <PersonFormModal open={editOpen} person={p} areas={areas} onClose={() => setEditOpen(false)} onSaved={() => { setEditOpen(false); reload(); }} />
      <EnrollmentWizard open={wizardOpen} person={p} onClose={() => { setWizardOpen(false); reload(); }} />
      <Modal
        open={confirm !== null}
        title={confirm === "delete" ? "Eliminar persona" : "Eliminar datos biométricos"}
        onClose={() => setConfirm(null)}
        footer={
          <>
            <Button onClick={() => setConfirm(null)}>Cancelar</Button>
            <Button
              variant="danger"
              loading={busy}
              onClick={async () => {
                if (confirm === "delete") {
                  await act(() => api(`/api/admin/people/${p.id}`, { method: "DELETE" }), "Persona eliminada");
                  navigate("/admin/personas");
                } else {
                  await act(() => api(`/api/admin/people/${p.id}/biometrics`, { method: "DELETE" }), "Datos biométricos eliminados");
                }
                setConfirm(null);
              }}
            >
              {confirm === "delete" ? "Eliminar persona" : "Eliminar datos biométricos"}
            </Button>
          </>
        }
      >
        <p>
          {confirm === "delete"
            ? `Se eliminará a ${p.full_name} y todos sus datos biométricos. Solo es posible porque no tiene marcaciones.`
            : `Se borrarán las ${p.face_templates.length} plantillas faciales, sus fotos de enrolamiento y la huella de ${p.full_name}. Sus marcaciones se conservan. No se puede deshacer.`}
        </p>
      </Modal>
      <Lightbox src={photo} alt="Captura de enrolamiento" onClose={() => setPhoto(null)} />
    </>
  );
}

function FingerprintPanel({ person, onChanged }: { person: PersonDetail; onChanged: () => void }) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [provider, setProvider] = useState<{ provider: string; label: string; simulated: boolean } | null>(null);
  useEffect(() => {
    api<{ fingerprint: { provider: string; label: string; simulated: boolean } }>("/api/kiosk/status")
      .then((s) => setProvider(s.fingerprint))
      .catch(() => setProvider(null));
  }, []);
  const disabled = !provider || provider.provider === "disabled";
  const run = async (fn: () => Promise<unknown>, msg: string) => {
    setBusy(true);
    try {
      await fn();
      toast(msg);
      onChanged();
    } catch (e) {
      toast((e as Error).message, "danger");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Huella">
      <div className="flex flex-col gap-3 p-4">
        <p className="flex items-center gap-2">
          <Fingerprint className="size-5 text-muted" aria-hidden />
          {person.fingerprint_slot ? (
            <span>
              Registrada en la posición <span className="tnum font-semibold">{person.fingerprint_slot}</span>
              {person.fingerprint_backup ? ", con respaldo cifrado" : ""}
            </span>
          ) : (
            <span className="text-muted">Sin huella registrada</span>
          )}
        </p>
        <p className="text-sm text-muted">Lector: {provider?.label ?? "…"}</p>
        {disabled ? (
          <p className="text-sm text-muted">La huella es opcional en la v1. Cuando llegue el AS608 se configura en .env (ver README).</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button
              variant="primary"
              loading={busy}
              disabled={!person.consent_signed}
              onClick={() => run(() => api(`/api/admin/people/${person.id}/fingerprint`, { method: "POST", json: {} }), "Huella registrada")}
            >
              {provider?.simulated ? "Asignar huella simulada" : person.fingerprint_slot ? "Volver a enrolar" : "Enrolar huella (2 capturas)"}
            </Button>
            {person.fingerprint_slot && (
              <Button loading={busy} onClick={() => run(() => api(`/api/admin/people/${person.id}/fingerprint`, { method: "DELETE" }), "Huella eliminada")}>
                Quitar huella
              </Button>
            )}
          </div>
        )}
      </div>
    </Panel>
  );
}

const STEPS = [
  { pose: "frontal", label: "De frente", tip: "Mira directo a la cámara, rostro dentro del óvalo." },
  { pose: "left", label: "Leve giro a tu izquierda", tip: "Gira un poco la cabeza a tu izquierda (unos 15°)." },
  { pose: "right", label: "Leve giro a tu derecha", tip: "Gira un poco la cabeza a tu derecha (unos 15°)." },
  { pose: "glasses", label: "Con lentes", tip: "Si usas lentes, póntelos. Si no, sonríe ligeramente.", optional: true },
  { pose: "frontal_2", label: "Sin lentes", tip: "De frente otra vez, sin lentes." },
];

function EnrollmentWizard({ open, person, onClose }: { open: boolean; person: PersonDetail; onClose: () => void }) {
  const cam = useCamera(null, open);
  const [step, setStep] = useState(0);
  const [done, setDone] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<{ tone: "danger" | "in" | "warn"; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [duplicate, setDuplicate] = useState<{ blob: Blob; dup: Duplicate } | null>(null);

  useEffect(() => {
    if (open) {
      setStep(0);
      setDone({});
      setMessage(null);
    }
  }, [open]);

  const current = STEPS[step];
  const finished = step >= STEPS.length;
  const portrait = cam.dims ? cam.dims.h > cam.dims.w : false;
  const guideW = portrait ? 75 : 133;

  const send = async (blob: Blob, confirmDup: boolean) => {
    const fd = new FormData();
    fd.append("file", blob, "captura.jpg");
    fd.append("pose", current.pose);
    fd.append("source", "camera");
    fd.append("confirm_duplicate", String(confirmDup));
    setBusy(true);
    try {
      await api(`/api/admin/people/${person.id}/templates`, { method: "POST", body: fd });
      setDone((d) => ({ ...d, [current.pose]: URL.createObjectURL(blob) }));
      setMessage({ tone: "in", text: `${current.label}: captura guardada` });
      setStep((s) => s + 1);
    } catch (e) {
      if (e instanceof ApiError && e.code === "duplicate" && e.data?.duplicate) {
        setDuplicate({ blob, dup: e.data.duplicate as Duplicate });
      } else {
        setMessage({ tone: "danger", text: (e as Error).message });
      }
    } finally {
      setBusy(false);
    }
  };

  const capture = async () => {
    const blob = await cam.capture(960, 0.9);
    if (!blob) return setMessage({ tone: "danger", text: "La cámara todavía no entrega imagen" });
    await send(blob, false);
  };

  return (
    <Modal open={open} title={`Enrolar rostro de ${person.first_name}`} onClose={onClose} wide>
      <div className="grid grid-cols-1 gap-5 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="flex flex-col items-center gap-3">
          {/* Si la imagen es vertical (celular en vertical), el recuadro también lo es. */}
          <div
            className={cx("relative max-w-full overflow-hidden rounded-xl bg-stage", !portrait && "aspect-[4/3] w-full")}
            style={portrait ? { height: "min(60vh, 560px)", aspectRatio: "3 / 4" } : undefined}
          >
            <CameraPreview cam={cam} />
            <svg className="pointer-events-none absolute inset-0 size-full" viewBox={`0 0 ${guideW} 100`} preserveAspectRatio="xMidYMid slice" aria-hidden>
              <ellipse cx={guideW / 2} cy="48" rx="24" ry="33" fill="none" stroke="rgba(255,255,255,0.8)" strokeWidth="0.8" strokeDasharray="2 1.5" />
            </svg>
            {cam.status !== "ready" && (
              <div className="absolute inset-0 grid place-items-center p-6 text-center text-white">
                <p>{cam.status === "denied" ? "Permite el acceso a la cámara en el navegador para enrolar." : cam.status === "starting" ? "Abriendo la cámara…" : cam.error ?? "Cámara no disponible"}</p>
              </div>
            )}
          </div>
          <div className="flex w-full flex-wrap items-center gap-3">
            <Button onClick={cam.rotate} disabled={cam.status !== "ready"} icon={<RotateCw className="size-4" aria-hidden />}>
              Girar imagen
            </Button>
            <p className="flex-1 text-sm text-muted">Si te ves de lado o de cabeza, gira la imagen hasta que se vea normal.</p>
          </div>
        </div>
        <div className="flex flex-col gap-3">
          <ol className="flex flex-col gap-1.5">
            {STEPS.map((s, i) => (
              <li
                key={s.pose}
                className={cx(
                  "flex items-center gap-3 rounded-lg border px-3 py-2",
                  i === step ? "border-primary bg-surface-2" : "border-border",
                )}
                aria-current={i === step ? "step" : undefined}
              >
                {done[s.pose] ? (
                  <img src={done[s.pose]} alt="" className="size-9 rounded-md object-cover -scale-x-100" />
                ) : (
                  <span className="tnum grid size-9 place-items-center rounded-md bg-surface-2 text-sm font-semibold">{i + 1}</span>
                )}
                <span className="flex-1 text-sm font-medium">{s.label}</span>
                {done[s.pose] && <CircleCheck className="size-5 text-in" aria-label="Lista" />}
              </li>
            ))}
          </ol>
          {!finished ? (
            <>
              <p className="text-sm text-muted">{current.tip}</p>
              <div className="flex flex-wrap gap-2">
                <Button variant="primary" size="lg" onClick={capture} loading={busy} disabled={cam.status !== "ready"} icon={<Camera className="size-5" aria-hidden />}>
                  Capturar
                </Button>
                {current.optional && (
                  <Button size="lg" onClick={() => setStep((s) => s + 1)}>
                    Omitir
                  </Button>
                )}
              </div>
            </>
          ) : (
            <p className="rounded-lg bg-in-soft px-4 py-3 font-medium text-in">Enrolamiento completo. Ya puede marcar en el kiosco.</p>
          )}
          {message && (
            <p className={cx("text-sm", message.tone === "danger" ? "text-danger" : message.tone === "warn" ? "text-warn" : "text-in")} role="status">
              {message.text}
            </p>
          )}
          <Button className="mt-auto" onClick={onClose}>
            {finished ? "Cerrar" : "Terminar después"}
          </Button>
        </div>
      </div>
      <Modal open={duplicate !== null} title="Posible duplicado" onClose={() => setDuplicate(null)}>
        {duplicate && (
          <>
            <p>
              Este rostro coincide con <strong>{duplicate.dup.full_name}</strong> ({duplicate.dup.code}): similitud{" "}
              <span className="tnum">{duplicate.dup.score.toFixed(3)}</span> con umbral <span className="tnum">{duplicate.dup.threshold.toFixed(3)}</span>.
            </p>
            <p className="mt-2 text-sm text-muted">Si son personas distintas (por ejemplo, gemelos), puedes guardar la captura igual.</p>
            <div className="mt-4 flex justify-end gap-2">
              <Button onClick={() => setDuplicate(null)}>Descartar captura</Button>
              <Button
                variant="primary"
                onClick={async () => {
                  const blob = duplicate.blob;
                  setDuplicate(null);
                  await send(blob, true);
                }}
              >
                Guardar de todos modos
              </Button>
            </div>
          </>
        )}
      </Modal>
    </Modal>
  );
}
