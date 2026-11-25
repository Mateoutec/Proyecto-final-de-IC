import { Activity, Cpu, Fingerprint, RefreshCw, Save } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Badge, Button, Checkbox, ErrorState, Field, Input, LoadingBlock, PageHeader, Panel, Select, useToast } from "../../components/ui";
import { api } from "../../lib/api";
import { pct } from "../../lib/format";
import type { CalibrationResult, RuntimeValues, SettingsPayload } from "../../lib/types";
import { useAsync } from "../../lib/useAsync";

export function SettingsPage() {
  const toast = useToast();
  const { data, error, loading, reload, setData } = useAsync(() => api<SettingsPayload>("/api/admin/settings"), []);
  const [form, setForm] = useState<RuntimeValues | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [reindexing, setReindexing] = useState(false);

  useEffect(() => {
    if (data) setForm(data.values);
  }, [data]);

  if (error) return <ErrorState error={error} onRetry={reload} />;
  if (loading || !data || !form) return <LoadingBlock rows={8} />;

  const changes = Object.fromEntries(
    Object.entries(form).filter(([k, v]) => data.values[k as keyof RuntimeValues] !== v),
  ) as Partial<RuntimeValues>;
  const dirty = Object.keys(changes).length > 0;
  const set = <K extends keyof RuntimeValues>(k: K, v: RuntimeValues[K]) => setForm((f) => (f ? { ...f, [k]: v } : f));
  const num = (k: keyof RuntimeValues) => (e: React.ChangeEvent<HTMLInputElement>) => set(k, Number(e.target.value) as never);

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const next = await api<SettingsPayload>("/api/admin/settings", { method: "PUT", json: { changes } });
      setData(next);
      toast("Configuración guardada");
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  const reindex = async () => {
    setReindexing(true);
    try {
      const r = await api<{ engine: string; created: number; skipped: number; missing: number }>("/api/admin/reindex", {
        method: "POST",
        json: {},
      });
      toast(`Re-indexado ${r.engine}: ${r.created} plantillas creadas, ${r.skipped} omitidas, ${r.missing} fotos faltantes`);
      reload();
    } catch (e) {
      toast((e as Error).message, "danger");
    } finally {
      setReindexing(false);
    }
  };

  const engine = data.engine;
  return (
    <>
      <PageHeader
        title="Configuración"
        description="Los cambios se aplican al instante y quedan en la auditoría. Los valores base viven en .env."
        actions={
          <Button variant="primary" onClick={save} loading={saving} disabled={!dirty} icon={<Save className="size-4" aria-hidden />}>
            Guardar cambios
          </Button>
        }
      />
      {saveError && (
        <p className="mb-4 rounded-lg bg-danger-soft px-4 py-3 text-sm text-danger" role="alert">
          {saveError}
        </p>
      )}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Panel title="Motor facial">
          <div className="flex flex-col gap-4 p-4">
            <div className="flex items-start gap-3 rounded-lg bg-surface-2 px-4 py-3">
              <Cpu className="mt-0.5 size-5 text-muted" aria-hidden />
              <div className="text-sm">
                <p>
                  Activo: <strong>{engine.active ?? "ninguno"}</strong> {engine.description ? `(${engine.description})` : ""}
                </p>
                <p className="text-muted">
                  {engine.templates_loaded} plantillas de {engine.enrolled_people} personas en memoria
                </p>
                {engine.fallback && <p className="mt-1 text-warn">Respaldo automático: {engine.fallback_reason}</p>}
                {engine.error && <p className="mt-1 text-danger">{engine.error}</p>}
                {data.undecryptable_templates > 0 && (
                  <p className="mt-1 text-danger">{data.undecryptable_templates} plantillas no se pudieron descifrar: re-indexa.</p>
                )}
              </div>
            </div>
            <Field label="Motor" hint="Al cambiar de motor, re-indexa para generar las plantillas desde las fotos de enrolamiento.">
              {(id) => (
                <Select id={id} value={form.face_engine} onChange={(e) => set("face_engine", e.target.value as RuntimeValues["face_engine"])}>
                  {data.engines.map((e) => (
                    <option key={e.name} value={e.name} disabled={!e.models}>
                      {e.label}
                      {e.models ? "" : " (faltan modelos)"}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Button onClick={reindex} loading={reindexing} icon={<RefreshCw className="size-4" aria-hidden />} className="self-start">
              Re-indexar plantillas del motor activo
            </Button>
          </div>
        </Panel>

        <Panel title="Umbrales de similitud">
          <div className="grid gap-4 p-4 sm:grid-cols-2">
            <Field label="InsightFace (coseno)" hint="Inicial 0.45">
              {(id) => <Input id={id} type="number" step="0.005" min="0.05" max="0.99" value={form.threshold_insightface} onChange={num("threshold_insightface")} />}
            </Field>
            <Field label="SFace (coseno)" hint="Punto publicado 0.363">
              {(id) => <Input id={id} type="number" step="0.001" min="0.05" max="0.99" value={form.threshold_sface} onChange={num("threshold_sface")} />}
            </Field>
            <Field label="Margen 1.º vs 2.º candidato" hint="Diferencia mínima de similitud">
              {(id) => <Input id={id} type="number" step="0.01" min="0" max="0.5" value={form.identify_margin} onChange={num("identify_margin")} />}
            </Field>
            <Field label="Giro máximo 'de frente'" hint="Desplazamiento de la nariz / distancia entre ojos">
              {(id) => <Input id={id} type="number" step="0.01" min="0.05" max="0.8" value={form.max_frontal_yaw} onChange={num("max_frontal_yaw")} />}
            </Field>
            <Field label="Nitidez mínima" hint="Varianza del Laplaciano del rostro">
              {(id) => <Input id={id} type="number" step="1" min="0" max="1000" value={form.min_sharpness} onChange={num("min_sharpness")} />}
            </Field>
            <p className="self-end text-sm text-muted">Consenso: {data.env.consensus}.</p>
          </div>
        </Panel>

        <Panel title="Prueba de vida">
          <div className="grid gap-4 p-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Checkbox
                label="Pedir giro de cabeza antes de registrar"
                hint="Reto aleatorio: izquierda o derecha, con tiempo límite y verificando que la identidad no cambie."
                checked={form.liveness_enabled}
                onChange={(v) => set("liveness_enabled", v)}
              />
            </div>
            <Field label="Tiempo límite (s)">
              {(id) => <Input id={id} type="number" step="0.5" min="2" max="30" value={form.liveness_timeout_seconds} onChange={num("liveness_timeout_seconds")} />}
            </Field>
            <Field label="Giro mínimo" hint="0.18 ≈ 25–30°">
              {(id) => <Input id={id} type="number" step="0.01" min="0.05" max="0.6" value={form.liveness_yaw_threshold} onChange={num("liveness_yaw_threshold")} />}
            </Field>
          </div>
        </Panel>

        <Panel title="Asistencia y respaldo">
          <div className="grid gap-4 p-4 sm:grid-cols-2">
            <Field label="Anti-rebote (s)" hint="Ignora repeticiones de la misma persona">
              {(id) => <Input id={id} type="number" step="10" min="0" max="3600" value={form.debounce_seconds} onChange={num("debounce_seconds")} />}
            </Field>
            <Field label="Jornada máxima (h)" hint="Una ENTRADA abierta más tiempo queda INCOMPLETA">
              {(id) => <Input id={id} type="number" step="1" min="1" max="48" value={form.max_shift_hours} onChange={num("max_shift_hours")} />}
            </Field>
            <Field label="Modo de respaldo" hint="Si la huella no coincide (siempre con prueba de vida)">
              {(id) => (
                <Select id={id} value={form.fallback_mode} onChange={(e) => set("fallback_mode", e.target.value as RuntimeValues["fallback_mode"])}>
                  <option value="face">Rostro 1:N</option>
                  <option value="code_plus_face">Código + rostro 1:1</option>
                </Select>
              )}
            </Field>
            <Field label="Separador CSV">
              {(id) => (
                <Select id={id} value={form.csv_delimiter} onChange={(e) => set("csv_delimiter", e.target.value)}>
                  <option value=",">Coma (,)</option>
                  <option value=";">Punto y coma (;)</option>
                  <option value={"\t"}>Tabulación</option>
                  <option value="|">Barra (|)</option>
                </Select>
              )}
            </Field>
            <div className="sm:col-span-2">
              <Checkbox
                label="Guardar foto de los intentos fallidos"
                hint="Desactivado por privacidad. Se guardan en data/captures/fallidos/."
                checked={form.save_failed_attempts}
                onChange={(v) => set("save_failed_attempts", v)}
              />
            </div>
          </div>
        </Panel>

        <Panel title="Huella">
          <div className="flex flex-col gap-3 p-4 text-sm">
            <p className="flex items-center gap-2">
              <Fingerprint className="size-5 text-muted" aria-hidden />
              <span>
                Proveedor <strong>{data.fingerprint.provider}</strong>: {data.fingerprint.label}
              </span>
              {data.fingerprint.experimental && <Badge tone="warn">Experimental</Badge>}
              {data.fingerprint.connected ? <Badge tone="in">Conectado</Badge> : <Badge>Sin conexión</Badge>}
            </p>
            {data.fingerprint.detail && <p className="text-muted">{data.fingerprint.detail}</p>}
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
              <dt className="text-muted">Puerto</dt>
              <dd className="font-mono">{String(data.env.fingerprint_port)}</dd>
              <dt className="text-muted">Baudios</dt>
              <dd className="tnum">{String(data.env.fingerprint_baudrate)}</dd>
              <dt className="text-muted">Puntaje alto / medio</dt>
              <dd className="tnum">
                {String(data.env.fingerprint_high_score)} / {String(data.env.fingerprint_medium_score)}
              </dd>
            </dl>
            <p className="text-muted">Se configura en .env (FINGERPRINT_PROVIDER, FINGERPRINT_PORT). Pasos de conexión en el README.</p>
          </div>
        </Panel>

        <CalibrationPanel
          onApply={async (engineName, value) => {
            const key = engineName === "sface" ? "threshold_sface" : engineName === "fake" ? "threshold_fake" : "threshold_insightface";
            const next = await api<SettingsPayload>("/api/admin/settings", { method: "PUT", json: { changes: { [key]: value } } });
            setData(next);
            toast(`Umbral de ${engineName} actualizado a ${value.toFixed(2)}`);
          }}
        />
      </div>
    </>
  );
}

function CalibrationPanel({ onApply }: { onApply: (engine: string, value: number) => Promise<void> }) {
  const [result, setResult] = useState<CalibrationResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api<{ result: CalibrationResult | null }>("/api/admin/calibration/latest")
      .then((r) => setResult(r.result))
      .catch(() => undefined);
  }, []);
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api<CalibrationResult>("/api/admin/calibration", { method: "POST" }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel
      title="Calibración"
      className="xl:col-span-2"
      actions={
        <Button onClick={run} loading={busy} icon={<Activity className="size-4" aria-hidden />}>
          Calcular calibración
        </Button>
      }
    >
      <div className="p-4">
        <p className="text-sm text-muted">
          Compara todas las plantillas enroladas: pares de la misma persona (genuinos) y de personas distintas (impostores). Estima FAR y FRR por umbral y sugiere uno con FAR ≤ 0,1 %.
        </p>
        {error && (
          <p className="mt-3 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-4 grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <dl className="tnum grid grid-cols-[auto_1fr] content-start gap-x-4 gap-y-1.5 text-sm">
              <Row k="Motor" v={result.engine} />
              <Row k="Personas / plantillas" v={`${result.people} / ${result.templates}`} />
              <Row k="Pares genuinos / impostores" v={`${result.genuine_pairs} / ${result.impostor_pairs}`} />
              <Row k="Similitud media genuina" v={result.genuine_mean?.toFixed(3) ?? "—"} />
              <Row k="Similitud media impostora" v={result.impostor_mean?.toFixed(3) ?? "—"} />
              <Row k="Máx. impostor / mín. genuino" v={`${result.max_impostor?.toFixed(3) ?? "—"} / ${result.min_genuine?.toFixed(3) ?? "—"}`} />
              <Row k="EER" v={`${pct(result.eer)} en ${result.eer_threshold.toFixed(2)}`} />
              <Row k="Umbral actual" v={`${result.current_threshold.toFixed(3)}: FAR ${pct(result.current_far)}, FRR ${pct(result.current_frr)}`} />
              <Row
                k="Umbral sugerido"
                v={
                  <span className="font-semibold text-in">
                    {result.suggested_threshold.toFixed(2)}: FAR {pct(result.suggested_far)}, FRR {pct(result.suggested_frr)}
                  </span>
                }
              />
              <dd className="col-span-2 mt-2 flex flex-wrap gap-2">
                <Button size="sm" variant="primary" onClick={() => onApply(result.engine, result.suggested_threshold)}>
                  Aplicar umbral sugerido
                </Button>
                <a className="inline-flex h-8 items-center rounded-lg border border-border px-3 text-sm hover:bg-surface-2" href={result.urls.csv} download>
                  FAR/FRR (CSV)
                </a>
                <a className="inline-flex h-8 items-center rounded-lg border border-border px-3 text-sm hover:bg-surface-2" href={result.urls.scores} download>
                  Similitudes (CSV)
                </a>
                <a className="inline-flex h-8 items-center rounded-lg border border-border px-3 text-sm hover:bg-surface-2" href={result.urls.chart} download>
                  Gráfico (PNG)
                </a>
              </dd>
              <dd className="col-span-2 mt-1 text-xs text-muted">{result.note}</dd>
            </dl>
            <img src={result.urls.chart} alt="Distribuciones de similitud genuina e impostora y curvas FAR/FRR" className="w-full rounded-lg border border-border bg-white" />
          </div>
        )}
      </div>
    </Panel>
  );
}

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <>
      <dt className="text-muted">{k}</dt>
      <dd>{v}</dd>
    </>
  );
}
