import { ScanFace, UserCheck } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { EmptyState, ErrorState, Lightbox, LoadingBlock, PageHeader, Panel, Table, Thumb } from "../../components/ui";
import { api } from "../../lib/api";
import { longDate, score } from "../../lib/format";
import type { Summary } from "../../lib/types";
import { useAsync } from "../../lib/useAsync";
import { MethodText, TypeBadge } from "../shared";

export function DashboardPage() {
  const { data, error, loading, reload } = useAsync(() => api<Summary>("/api/admin/summary"), []);
  const [photo, setPhoto] = useState<string | null>(null);

  return (
    <>
      <PageHeader title="Resumen del día" description={longDate()} />
      {error && <ErrorState error={error} onRetry={reload} />}
      {loading && !data && <LoadingBlock rows={6} />}
      {data && (
        <div className="flex flex-col gap-6">
          <section aria-label="Cifras de hoy" className="grid grid-cols-2 overflow-hidden rounded-xl border border-border bg-surface sm:grid-cols-3 xl:grid-cols-6">
            <Stat label="Presentes ahora" value={data.counts.present} accent="text-info" />
            <Stat label="Entradas" value={data.counts.entries} accent="text-in" />
            <Stat label="Salidas" value={data.counts.exits} accent="text-out" />
            <Stat
              label="Jornadas incompletas"
              value={data.counts.incomplete_today}
              note={`${data.counts.incomplete_week} en los últimos 7 días`}
              accent={data.counts.incomplete_today ? "text-danger" : undefined}
            />
            <Stat label="Horas cerradas hoy" value={data.counts.hhmm_today} note={`${data.counts.hours_today.toFixed(2)} h`} />
            <Stat
              label="Personas enroladas"
              value={`${data.counts.enrolled_people}/${data.counts.active_people}`}
              note={`Motor ${data.engine.active ?? "no disponible"}`}
            />
          </section>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
            <Panel title="Presentes ahora">
              {data.present.length === 0 ? (
                <EmptyState icon={<UserCheck className="size-8" aria-hidden />} title="Nadie con jornada abierta">
                  Cuando alguien marque su entrada en el kiosco aparecerá aquí hasta que marque la salida.
                </EmptyState>
              ) : (
                <ul className="divide-y divide-border">
                  {data.present.map((p) => (
                    <li key={p.person_id} className="flex items-center gap-3 px-4 py-2.5">
                      <div className="min-w-0 flex-1">
                        <Link to={`/admin/personas/${p.person_id}`} className="font-medium hover:underline">
                          {p.person_name}
                        </Link>
                        <p className="text-sm text-muted">{p.area ?? "Sin área"}</p>
                      </div>
                      <div className="tnum text-right text-sm">
                        <p>Desde las {p.since}</p>
                        <p className="text-muted">{p.elapsed_hhmm} h</p>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>

            <Panel
              title="Últimas marcaciones"
              actions={
                <Link to="/admin/marcaciones" className="text-sm font-medium text-primary hover:underline">
                  Ver todas
                </Link>
              }
            >
              {data.recent.length === 0 ? (
                <EmptyState icon={<ScanFace className="size-8" aria-hidden />} title="Todavía no hay marcaciones hoy">
                  Las marcaciones del kiosco se listan aquí con su foto de auditoría.
                </EmptyState>
              ) : (
                <Table>
                  <thead>
                    <tr>
                      <th>Foto</th>
                      <th>Hora</th>
                      <th>Persona</th>
                      <th>Tipo</th>
                      <th>Método</th>
                      <th>Similitud</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent.map((e) => (
                      <tr key={e.id}>
                        <td>
                          <Thumb src={e.photo_url} alt={`Foto de ${e.person_name}`} onOpen={setPhoto} />
                        </td>
                        <td className="font-medium">{e.local_time.slice(0, 5)}</td>
                        <td>
                          <p className="font-medium">{e.person_name}</p>
                          <p className="text-xs text-muted">{e.area ?? "Sin área"}</p>
                        </td>
                        <td>
                          <TypeBadge type={e.event_type} />
                        </td>
                        <td>
                          <MethodText method={e.method} />
                        </td>
                        <td>{e.face_score != null ? `${score(e.face_score)} / ${score(e.face_threshold)}` : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </Panel>
          </div>

          <Panel title="Por área">
            {data.by_area.length === 0 ? (
              <EmptyState title="Sin actividad por área hoy" />
            ) : (
              <Table>
                <thead>
                  <tr>
                    <th>Área</th>
                    <th>Presentes</th>
                    <th>Entradas</th>
                    <th>Salidas</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_area.map((a) => (
                    <tr key={a.area}>
                      <td className="font-medium">{a.area}</td>
                      <td>{a.present}</td>
                      <td>{a.entries}</td>
                      <td>{a.exits}</td>
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

function Stat({ label, value, note, accent }: { label: string; value: number | string; note?: string; accent?: string }) {
  return (
    <div className="border-b border-r border-border px-5 py-4 [&:nth-child(2n)]:border-r-0 sm:[&:nth-child(2n)]:border-r sm:[&:nth-child(3n)]:border-r-0 xl:border-b-0 xl:[&:nth-child(3n)]:border-r xl:last:border-r-0">
      <p className="text-sm text-muted">{label}</p>
      <p className={`tnum mt-1 font-display text-4xl font-semibold ${accent ?? ""}`}>{value}</p>
      {note && <p className="mt-0.5 text-xs text-muted">{note}</p>}
    </div>
  );
}
