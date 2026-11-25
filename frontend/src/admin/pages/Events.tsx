import { Ban, ClipboardList, Plus } from "lucide-react";
import { useState } from "react";
import {
  Badge,
  Button,
  Checkbox,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Lightbox,
  LoadingBlock,
  Modal,
  PageHeader,
  Panel,
  Select,
  Table,
  Textarea,
  Thumb,
  useToast,
} from "../../components/ui";
import { api, qs } from "../../lib/api";
import { LIVENESS_LABEL, METHOD_LABEL, daysAgo, isoDate, localDateTimeInput, prettyDate, score } from "../../lib/format";
import type { AttendanceEvent, Method, Person } from "../../lib/types";
import { useAsync } from "../../lib/useAsync";
import { AreaSelect, DateRange, MethodText, TypeBadge, useAreas, usePeopleOptions } from "../shared";

export function EventsPage() {
  const toast = useToast();
  const { areas } = useAreas();
  const people = usePeopleOptions();
  const [from, setFrom] = useState(daysAgo(6));
  const [to, setTo] = useState(isoDate(new Date()));
  const [areaId, setAreaId] = useState("");
  const [personId, setPersonId] = useState("");
  const [type, setType] = useState("");
  const [method, setMethod] = useState("");
  const [includeVoided, setIncludeVoided] = useState(true);
  const [photo, setPhoto] = useState<string | null>(null);
  const [voiding, setVoiding] = useState<AttendanceEvent | null>(null);
  const [manualOpen, setManualOpen] = useState(false);

  const { data, error, loading, reload } = useAsync(
    () =>
      api<{ items: AttendanceEvent[]; total: number }>(
        `/api/admin/events${qs({ date_from: from, date_to: to, area_id: areaId, person_id: personId, event_type: type, method, include_voided: includeVoided, limit: 500 })}`,
      ),
    [from, to, areaId, personId, type, method, includeVoided],
  );

  return (
    <>
      <PageHeader
        title="Marcaciones"
        description="Cada marcación es inmutable. Puedes anularla o agregar una manual, siempre con motivo."
        actions={
          <Button variant="primary" onClick={() => setManualOpen(true)} icon={<Plus className="size-4" aria-hidden />}>
            Agregar marcación manual
          </Button>
        }
      />
      <Panel>
        <div className="flex flex-wrap items-end gap-3 border-b border-border p-4">
          <DateRange from={from} to={to} onChange={(f, t) => (setFrom(f), setTo(t))} />
          <AreaSelect value={areaId} onChange={setAreaId} areas={areas} />
          <Field label="Persona" className="w-56">
            {(id) => (
              <Select id={id} value={personId} onChange={(e) => setPersonId(e.target.value)}>
                <option value="">Todas</option>
                {people.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.full_name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Tipo" className="w-36">
            {(id) => (
              <Select id={id} value={type} onChange={(e) => setType(e.target.value)}>
                <option value="">Ambos</option>
                <option value="ENTRADA">Entrada</option>
                <option value="SALIDA">Salida</option>
              </Select>
            )}
          </Field>
          <Field label="Método" className="w-44">
            {(id) => (
              <Select id={id} value={method} onChange={(e) => setMethod(e.target.value)}>
                <option value="">Todos</option>
                {(Object.keys(METHOD_LABEL) as Method[]).map((m) => (
                  <option key={m} value={m}>
                    {METHOD_LABEL[m]}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <div className="pb-2">
            <Checkbox label="Incluir anuladas" checked={includeVoided} onChange={setIncludeVoided} />
          </div>
        </div>
        {error && <ErrorState error={error} onRetry={reload} />}
        {loading && !data && <LoadingBlock rows={6} />}
        {data && data.items.length === 0 && (
          <EmptyState icon={<ClipboardList className="size-8" aria-hidden />} title="No hay marcaciones en este rango">
            Amplía el rango de fechas o quita filtros.
          </EmptyState>
        )}
        {data && data.items.length > 0 && (
          <>
            <p className="px-4 pt-3 text-sm text-muted">
              {data.total} marcaciones{data.total > data.items.length ? `, se muestran las ${data.items.length} más recientes` : ""}
            </p>
            <Table>
              <thead>
                <tr>
                  <th>Foto</th>
                  <th>Fecha</th>
                  <th>Hora</th>
                  <th>Persona</th>
                  <th>Área</th>
                  <th>Tipo</th>
                  <th>Método</th>
                  <th>Similitud / umbral</th>
                  <th>Huella</th>
                  <th>Prueba de vida</th>
                  <th>Estado</th>
                  <th>
                    <span className="sr-only">Acciones</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((e) => (
                  <tr key={e.id} className={e.voided ? "opacity-60" : undefined}>
                    <td>
                      <Thumb src={e.photo_url} alt={`Foto de ${e.person_name}`} onOpen={setPhoto} />
                    </td>
                    <td className="whitespace-nowrap">{prettyDate(e.local_date)}</td>
                    <td className="font-medium">{e.local_time}</td>
                    <td>
                      <p className="font-medium">{e.person_name}</p>
                      <p className="text-xs text-muted">{e.person_code}</p>
                    </td>
                    <td>{e.area ?? "—"}</td>
                    <td>
                      <TypeBadge type={e.event_type} />
                    </td>
                    <td>
                      <MethodText method={e.method} />
                      {e.manual_reason && <p className="max-w-48 truncate text-xs text-muted" title={e.manual_reason}>{e.manual_reason}</p>}
                    </td>
                    <td className="whitespace-nowrap">{e.face_score != null ? `${score(e.face_score)} / ${score(e.face_threshold)}` : "—"}</td>
                    <td>{e.fingerprint_score != null ? e.fingerprint_score : "—"}</td>
                    <td>{LIVENESS_LABEL[e.liveness] ?? e.liveness}</td>
                    <td>
                      {e.voided ? (
                        <span title={e.void_reason ?? undefined}>
                          <Badge tone="danger">Anulada</Badge>
                        </span>
                      ) : (
                        <Badge tone="neutral">Válida</Badge>
                      )}
                    </td>
                    <td className="text-right">
                      {!e.voided && (
                        <Button size="sm" variant="ghost" onClick={() => setVoiding(e)} icon={<Ban className="size-4" aria-hidden />}>
                          Anular
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </>
        )}
      </Panel>
      <Lightbox src={photo} alt="Foto de la marcación" onClose={() => setPhoto(null)} />
      <VoidModal
        event={voiding}
        onClose={() => setVoiding(null)}
        onDone={() => {
          setVoiding(null);
          toast("Marcación anulada");
          reload();
        }}
      />
      <ManualModal
        open={manualOpen}
        people={people}
        onClose={() => setManualOpen(false)}
        onDone={() => {
          setManualOpen(false);
          toast("Marcación manual registrada");
          reload();
        }}
      />
    </>
  );
}

function VoidModal({ event, onClose, onDone }: { event: AttendanceEvent | null; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal
      open={event !== null}
      title="Anular marcación"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button
            variant="danger"
            loading={busy}
            onClick={async () => {
              if (!event) return;
              if (reason.trim().length < 3) return setError("Escribe el motivo de la anulación");
              setBusy(true);
              setError(null);
              try {
                await api(`/api/admin/events/${event.id}/void`, { method: "POST", json: { reason } });
                setReason("");
                onDone();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Anular marcación
          </Button>
        </>
      }
    >
      {event && (
        <p className="mb-3">
          {event.event_type} de <strong>{event.person_name}</strong> el {prettyDate(event.local_date)} a las {event.local_time}. Queda en el historial como anulada y deja de contar en las horas.
        </p>
      )}
      <Field label="Motivo (obligatorio)" error={error}>
        {(id) => <Textarea id={id} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Ej.: marcación duplicada por error" />}
      </Field>
    </Modal>
  );
}

function ManualModal({ open, people, onClose, onDone }: { open: boolean; people: Person[]; onClose: () => void; onDone: () => void }) {
  const [personId, setPersonId] = useState("");
  const [type, setType] = useState<"ENTRADA" | "SALIDA">("SALIDA");
  const [when, setWhen] = useState(localDateTimeInput());
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <Modal
      open={open}
      title="Agregar marcación manual"
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button
            variant="primary"
            loading={busy}
            onClick={async () => {
              if (!personId) return setError("Elige a la persona");
              if (reason.trim().length < 3) return setError("El motivo es obligatorio");
              setBusy(true);
              setError(null);
              try {
                await api("/api/admin/events/manual", {
                  method: "POST",
                  json: { person_id: Number(personId), event_type: type, local_datetime: when, reason },
                });
                setReason("");
                onDone();
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Registrar marcación
          </Button>
        </>
      }
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Persona" className="sm:col-span-2">
          {(id) => (
            <Select id={id} value={personId} onChange={(e) => setPersonId(e.target.value)}>
              <option value="">Elige una persona</option>
              {people.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.full_name} ({p.code})
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Tipo">
          {(id) => (
            <Select id={id} value={type} onChange={(e) => setType(e.target.value as "ENTRADA" | "SALIDA")}>
              <option value="ENTRADA">Entrada</option>
              <option value="SALIDA">Salida</option>
            </Select>
          )}
        </Field>
        <Field label="Fecha y hora">{(id) => <Input id={id} type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />}</Field>
        <Field label="Motivo (obligatorio)" className="sm:col-span-2" error={error} hint="Ej.: completar una salida olvidada. Queda registrado en la auditoría.">
          {(id) => <Textarea id={id} value={reason} onChange={(e) => setReason(e.target.value)} />}
        </Field>
      </div>
    </Modal>
  );
}
