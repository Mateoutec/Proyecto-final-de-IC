import { ScrollText } from "lucide-react";
import { useState } from "react";
import { Button, EmptyState, ErrorState, Field, LoadingBlock, PageHeader, Panel, Select, Table } from "../../components/ui";
import { api, qs } from "../../lib/api";
import { daysAgo, isoDate } from "../../lib/format";
import type { AuditItem } from "../../lib/types";
import { useAsync } from "../../lib/useAsync";
import { DateRange } from "../shared";

const PAGE = 100;

export function AuditPage() {
  const [action, setAction] = useState("");
  const [from, setFrom] = useState(daysAgo(30));
  const [to, setTo] = useState(isoDate(new Date()));
  const [page, setPage] = useState(0);
  const { data, error, loading, reload } = useAsync(
    () =>
      api<{ items: AuditItem[]; total: number; actions: { key: string; label: string }[] }>(
        `/api/admin/audit${qs({ action, date_from: from, date_to: to, limit: PAGE, offset: page * PAGE })}`,
      ),
    [action, from, to, page],
  );
  return (
    <>
      <PageHeader title="Auditoría" description="Altas, ediciones, enrolamientos, exportaciones, anulaciones y cambios de configuración." />
      <Panel>
        <div className="flex flex-wrap items-end gap-3 border-b border-border p-4">
          <DateRange from={from} to={to} onChange={(f, t) => (setFrom(f), setTo(t), setPage(0))} />
          <Field label="Acción" className="w-64">
            {(id) => (
              <Select id={id} value={action} onChange={(e) => (setAction(e.target.value), setPage(0))}>
                <option value="">Todas</option>
                {data?.actions.map((a) => (
                  <option key={a.key} value={a.key}>
                    {a.label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        {error && <ErrorState error={error} onRetry={reload} />}
        {loading && !data && <LoadingBlock rows={6} />}
        {data && data.items.length === 0 && <EmptyState icon={<ScrollText className="size-8" aria-hidden />} title="Sin registros en este rango" />}
        {data && data.items.length > 0 && (
          <>
            <Table>
              <thead>
                <tr>
                  <th>Fecha y hora</th>
                  <th>Actor</th>
                  <th>Acción</th>
                  <th>Entidad</th>
                  <th>Detalles</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.id} className="align-top">
                    <td className="whitespace-nowrap">{a.local.replace("T", " ").slice(0, 19)}</td>
                    <td>{a.actor}</td>
                    <td className="font-medium">{a.action_label}</td>
                    <td className="whitespace-nowrap text-muted">{a.entity_type ? `${a.entity_type} ${a.entity_id ?? ""}` : "—"}</td>
                    <td>
                      {a.details ? (
                        <details>
                          <summary className="cursor-pointer text-sm text-primary">Ver</summary>
                          <pre className="mt-1 max-w-xl overflow-x-auto whitespace-pre-wrap rounded-md bg-surface-2 p-2 text-xs">{JSON.stringify(a.details, null, 2)}</pre>
                        </details>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <div className="flex items-center justify-between border-t border-border px-4 py-3 text-sm">
              <span className="text-muted">
                {page * PAGE + 1}–{page * PAGE + data.items.length} de {data.total}
              </span>
              <div className="flex gap-2">
                <Button size="sm" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
                  Anterior
                </Button>
                <Button size="sm" disabled={(page + 1) * PAGE >= data.total} onClick={() => setPage((p) => p + 1)}>
                  Siguiente
                </Button>
              </div>
            </div>
          </>
        )}
      </Panel>
    </>
  );
}
