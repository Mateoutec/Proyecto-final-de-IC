import { LogIn, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge, Field, Input, Select, type Tone } from "../components/ui";
import { api } from "../lib/api";
import { METHOD_LABEL } from "../lib/format";
import type { Area, EventType, Method, Person } from "../lib/types";

export function useAreas() {
  const [areas, setAreas] = useState<Area[]>([]);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    api<Area[]>("/api/admin/areas")
      .then(setAreas)
      .catch(() => setAreas([]));
  }, [tick]);
  return { areas, reload: () => setTick((t) => t + 1) };
}

export function usePeopleOptions() {
  const [people, setPeople] = useState<Person[]>([]);
  useEffect(() => {
    api<Person[]>("/api/admin/people")
      .then(setPeople)
      .catch(() => setPeople([]));
  }, []);
  return people;
}

export function TypeBadge({ type }: { type: EventType }) {
  return type === "ENTRADA" ? (
    <Badge tone="in" icon={<LogIn className="size-3.5" aria-hidden />}>
      ENTRADA
    </Badge>
  ) : (
    <Badge tone="out" icon={<LogOut className="size-3.5" aria-hidden />}>
      SALIDA
    </Badge>
  );
}

export function MethodText({ method }: { method: Method }) {
  return <span className="whitespace-nowrap">{METHOD_LABEL[method] ?? method}</span>;
}

const SHIFT_TONE: Record<string, Tone> = { COMPLETA: "in", INCOMPLETA: "danger", EN_CURSO: "info" };
const SHIFT_TEXT: Record<string, string> = { COMPLETA: "Completa", INCOMPLETA: "Incompleta", EN_CURSO: "En curso" };

export function ShiftBadge({ status }: { status: string }) {
  return <Badge tone={SHIFT_TONE[status] ?? "neutral"}>{SHIFT_TEXT[status] ?? status}</Badge>;
}

export function DateRange({
  from,
  to,
  onChange,
}: {
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
}) {
  return (
    <>
      <Field label="Desde" className="w-40">
        {(id) => <Input id={id} type="date" value={from} max={to} onChange={(e) => onChange(e.target.value, to)} />}
      </Field>
      <Field label="Hasta" className="w-40">
        {(id) => <Input id={id} type="date" value={to} min={from} onChange={(e) => onChange(from, e.target.value)} />}
      </Field>
    </>
  );
}

export function AreaSelect({ value, onChange, areas, label = "Área" }: { value: string; onChange: (v: string) => void; areas: Area[]; label?: string }) {
  return (
    <Field label={label} className="w-52">
      {(id) => (
        <Select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">Todas las áreas</option>
          {areas.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </Select>
      )}
    </Field>
  );
}
