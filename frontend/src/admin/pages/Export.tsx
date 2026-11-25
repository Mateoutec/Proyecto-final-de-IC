import { FileArchive, FileSpreadsheet, FileText } from "lucide-react";
import { useState } from "react";
import { Button, PageHeader, Panel, useToast } from "../../components/ui";
import { downloadFile, qs } from "../../lib/api";
import { daysAgo, isoDate } from "../../lib/format";
import { AreaSelect, DateRange, useAreas } from "../shared";

const KINDS = [
  {
    kind: "shifts",
    title: "Jornadas",
    text: "Fecha, código, nombre, área, entrada, salida, horas en decimal y HH:MM, estado, métodos y fotos.",
    zip: true,
  },
  {
    kind: "events",
    title: "Marcaciones",
    text: "Cada marcación con tipo, método, similitud y umbral, puntaje de huella, prueba de vida, anulación y foto.",
    zip: true,
  },
  {
    kind: "summary",
    title: "Resumen por persona",
    text: "Días asistidos, total de horas y jornadas incompletas en el rango.",
    zip: false,
  },
] as const;

export function ExportPage() {
  const toast = useToast();
  const { areas } = useAreas();
  const [from, setFrom] = useState(daysAgo(30));
  const [to, setTo] = useState(isoDate(new Date()));
  const [areaId, setAreaId] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [last, setLast] = useState<string | null>(null);

  const run = async (kind: string, format: string) => {
    setBusy(`${kind}-${format}`);
    try {
      const r = await downloadFile(`/api/admin/export${qs({ kind, format, date_from: from, date_to: to, area_id: areaId })}`);
      const msg = `${r.filename} descargado${r.rows !== null ? ` (${r.rows} filas)` : ""}`;
      setLast(msg);
      toast(msg);
    } catch (e) {
      toast((e as Error).message, "danger");
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <PageHeader
        title="Exportar"
        description="CSV en UTF-8 con BOM (Excel muestra bien las tildes). El ZIP incluye el CSV y las fotos con las mismas rutas relativas."
      />
      <div className="mb-5 flex flex-wrap items-end gap-3 rounded-xl border border-border bg-surface p-4">
        <DateRange from={from} to={to} onChange={(f, t) => (setFrom(f), setTo(t))} />
        <AreaSelect value={areaId} onChange={setAreaId} areas={areas} />
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {KINDS.map((k) => (
          <Panel key={k.kind} title={k.title}>
            <div className="flex h-full flex-col gap-4 p-4">
              <p className="text-sm text-muted">{k.text}</p>
              <div className="mt-auto flex flex-wrap gap-2">
                <Button onClick={() => run(k.kind, "csv")} loading={busy === `${k.kind}-csv`} icon={<FileText className="size-4" aria-hidden />} data-testid={`export-${k.kind}-csv`}>
                  CSV
                </Button>
                <Button onClick={() => run(k.kind, "xlsx")} loading={busy === `${k.kind}-xlsx`} icon={<FileSpreadsheet className="size-4" aria-hidden />}>
                  Excel (XLSX)
                </Button>
                {k.zip && (
                  <Button onClick={() => run(k.kind, "zip")} loading={busy === `${k.kind}-zip`} icon={<FileArchive className="size-4" aria-hidden />}>
                    ZIP con fotos
                  </Button>
                )}
              </div>
            </div>
          </Panel>
        ))}
      </div>
      {last && (
        <p className="mt-4 text-sm text-muted" role="status">
          Última exportación: {last}. Queda registrada en la auditoría.
        </p>
      )}
    </>
  );
}
