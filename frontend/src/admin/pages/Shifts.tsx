import { Moon, Timer } from "lucide-react";
import { useState } from "react";
import { EmptyState, ErrorState, Field, Lightbox, LoadingBlock, PageHeader, Panel, Select, Table, Thumb } from "../../components/ui";
import { api, qs } from "../../lib/api";
import { METHOD_LABEL, daysAgo, hours, isoDate, prettyDate } from "../../lib/format";
import type { PersonTotals, Shift } from "../../lib/types";
import { useAsync } from "../../lib/useAsync";
import { AreaSelect, DateRange, ShiftBadge, useAreas, usePeopleOptions } from "../shared";

export function ShiftsPage() {
  const { areas } = useAreas();
  const people = usePeopleOptions();
  const [from, setFrom] = useState(daysAgo(6));
  const [to, setTo] = useState(isoDate(new Date()));
  const [areaId, setAreaId] = useState("");
  const [personId, setPersonId] = useState("");
  const [photo, setPhoto] = useState<string | null>(null);
  const { data, error, loading, reload } = useAsync(
    () =>
      api<{ items: Shift[]; totals: PersonTotals[] }>(
        `/api/admin/shifts${qs({ date_from: from, date_to: to, area_id: areaId, person_id: personId })}`,
      ),
    [from, to, areaId, personId],
  );

  return (
    <>
      <PageHeader
        title="Horas"
        description="Jornadas ENTRADA→SALIDA. Un turno que cruza la medianoche cuenta en el día de la entrada; varias jornadas del mismo día se suman."
      />
      <div className="mb-5 flex flex-wrap items-end gap-3 rounded-xl border border-border bg-surface p-4">
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
      </div>
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && !data && <LoadingBlock rows={6} />}
      {data && (
        <div className="flex flex-col gap-6">
          <Panel title="Totales por persona">
            {data.totals.length === 0 ? (
              <EmptyState icon={<Timer className="size-8" aria-hidden />} title="Sin jornadas en este rango" />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <th>Persona</th>
                    <th>Área</th>
                    <th>Días asistidos</th>
                    <th>Horas (decimal)</th>
                    <th>Horas (HH:MM)</th>
                    <th>Incompletas</th>
                    <th>En curso</th>
                  </tr>
                </thead>
                <tbody>
                  {data.totals.map((t) => (
                    <tr key={t.person_id}>
                      <td>
                        <p className="font-medium">{t.person_name}</p>
                        <p className="text-xs text-muted">{t.person_code}</p>
                      </td>
                      <td>{t.area ?? "—"}</td>
                      <td>{t.days}</td>
                      <td className="font-semibold">{hours(t.hours)}</td>
                      <td>{t.hhmm}</td>
                      <td className={t.incomplete ? "font-semibold text-danger" : undefined}>{t.incomplete}</td>
                      <td>{t.open}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Panel>
          <Panel title="Jornadas">
            {data.items.length === 0 ? (
              <EmptyState title="Sin jornadas en este rango">Cuando haya marcaciones de entrada y salida, las jornadas aparecen aquí.</EmptyState>
            ) : (
              <Table>
                <thead>
                  <tr>
                    <th>Fecha</th>
                    <th>Persona</th>
                    <th>Área</th>
                    <th>Entrada</th>
                    <th>Salida</th>
                    <th>Horas</th>
                    <th>HH:MM</th>
                    <th>Estado</th>
                    <th>Métodos</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((s, i) => (
                    <tr key={`${s.person_id}-${s.entry?.id ?? "x"}-${s.exit?.id ?? i}`}>
                      <td className="whitespace-nowrap">{prettyDate(s.work_date)}</td>
                      <td>
                        <p className="font-medium">{s.person_name}</p>
                        <p className="text-xs text-muted">{s.person_code}</p>
                      </td>
                      <td>{s.area ?? "—"}</td>
                      <td>
                        <div className="flex items-center gap-2">
                          {s.entry && <Thumb src={s.entry.photo_url} alt="Foto de entrada" onOpen={setPhoto} size="size-8" />}
                          <span className="font-medium">{s.entry?.local_time.slice(0, 5) ?? "—"}</span>
                        </div>
                      </td>
                      <td>
                        <div className="flex items-center gap-2">
                          {s.exit && <Thumb src={s.exit.photo_url} alt="Foto de salida" onOpen={setPhoto} size="size-8" />}
                          <span className="font-medium">{s.exit?.local_time.slice(0, 5) ?? "—"}</span>
                          {s.crosses_midnight && (
                            <span title="Cruza la medianoche" className="text-muted">
                              <Moon className="size-4" aria-label="Cruza la medianoche" />
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="font-semibold">{hours(s.hours)}</td>
                      <td>{s.hhmm ?? "—"}</td>
                      <td>
                        <ShiftBadge status={s.status} />
                      </td>
                      <td className="text-xs text-muted">
                        {[s.entry && METHOD_LABEL[s.entry.method], s.exit && METHOD_LABEL[s.exit.method]].filter(Boolean).join(" / ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Panel>
        </div>
      )}
      <Lightbox src={photo} alt="Foto de la marcación" onClose={() => setPhoto(null)} />
    </>
  );
}
