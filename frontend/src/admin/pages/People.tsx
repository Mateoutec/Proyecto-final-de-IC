import { Building2, Fingerprint, Pencil, Plus, ScanFace, Search, Trash2, UserPlus, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Badge,
  Button,
  Checkbox,
  EmptyState,
  ErrorState,
  Field,
  Input,
  LoadingBlock,
  Modal,
  PageHeader,
  Panel,
  Select,
  Table,
  useToast,
} from "../../components/ui";
import { api, qs } from "../../lib/api";
import { isoDate } from "../../lib/format";
import type { Area, Person } from "../../lib/types";
import { useAsync } from "../../lib/useAsync";
import { useAreas } from "../shared";

export function PeoplePage() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [areaId, setAreaId] = useState("");
  const [status, setStatus] = useState("all");
  const [editing, setEditing] = useState<Person | "new" | null>(null);
  const [areasOpen, setAreasOpen] = useState(false);
  const { areas, reload: reloadAreas } = useAreas();
  const navigate = useNavigate();

  useEffect(() => {
    const t = setTimeout(() => setQuery(search), 250);
    return () => clearTimeout(t);
  }, [search]);

  const { data, error, loading, reload } = useAsync(
    () => api<Person[]>(`/api/admin/people${qs({ search: query, area_id: areaId, status })}`),
    [query, areaId, status],
  );

  return (
    <>
      <PageHeader
        title="Personas"
        description="Registra a las personas, marca su consentimiento y enrola su rostro."
        actions={
          <>
            <Button onClick={() => setAreasOpen(true)} icon={<Building2 className="size-4" aria-hidden />}>
              Áreas
            </Button>
            <Button variant="primary" onClick={() => setEditing("new")} icon={<UserPlus className="size-4" aria-hidden />}>
              Nueva persona
            </Button>
          </>
        }
      />
      <Panel>
        <div className="flex flex-wrap items-end gap-3 border-b border-border p-4">
          <Field label="Buscar" className="min-w-56 flex-1">
            {(id) => (
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
                <Input id={id} value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Nombre o código" className="pl-9" />
              </div>
            )}
          </Field>
          <Field label="Área" className="w-56">
            {(id) => (
              <Select id={id} value={areaId} onChange={(e) => setAreaId(e.target.value)}>
                <option value="">Todas las áreas</option>
                {areas.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Estado" className="w-44">
            {(id) => (
              <Select id={id} value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="all">Todas</option>
                <option value="active">Activas</option>
                <option value="inactive">Desactivadas</option>
              </Select>
            )}
          </Field>
        </div>
        {error && <ErrorState error={error} onRetry={reload} />}
        {loading && !data && <LoadingBlock />}
        {data && data.length === 0 && (
          <EmptyState
            icon={<Users className="size-8" aria-hidden />}
            title={query || areaId || status !== "all" ? "Ninguna persona coincide con los filtros" : "Aún no hay personas registradas"}
            action={
              <Button variant="primary" onClick={() => setEditing("new")} icon={<UserPlus className="size-4" aria-hidden />}>
                Registrar la primera persona
              </Button>
            }
          >
            Primero crea un área, luego registra a la persona con su consentimiento firmado y enrola su rostro.
          </EmptyState>
        )}
        {data && data.length > 0 && (
          <Table>
            <thead>
              <tr>
                <th>Código</th>
                <th>Nombre</th>
                <th>Área</th>
                <th>Consentimiento</th>
                <th>Rostro</th>
                <th>Huella</th>
                <th>Última marcación</th>
                <th>Estado</th>
                <th>
                  <span className="sr-only">Acciones</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((p) => (
                <tr key={p.id} className="hover:bg-surface-2/50">
                  <td className="font-medium">{p.code}</td>
                  <td>
                    <Link to={`/admin/personas/${p.id}`} className="font-medium text-fg hover:underline">
                      {p.full_name}
                    </Link>
                    {p.position && <p className="text-xs text-muted">{p.position}</p>}
                  </td>
                  <td>{p.area ?? <span className="text-muted">Sin área</span>}</td>
                  <td>{p.consent_signed ? <Badge tone="in">Firmado {p.consent_date}</Badge> : <Badge tone="warn">Pendiente</Badge>}</td>
                  <td>
                    {p.enrolled ? (
                      <Badge tone="in" icon={<ScanFace className="size-3.5" aria-hidden />}>
                        {p.templates_active} capturas
                      </Badge>
                    ) : p.needs_reindex ? (
                      <Badge tone="warn">Re-indexar</Badge>
                    ) : (
                      <Badge>Sin enrolar</Badge>
                    )}
                  </td>
                  <td>
                    {p.fingerprint_slot ? (
                      <Badge tone="info" icon={<Fingerprint className="size-3.5" aria-hidden />}>
                        Posición {p.fingerprint_slot}
                      </Badge>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap">{p.last_event ? `${p.last_event.event_type} ${p.last_event.local}` : <span className="text-muted">—</span>}</td>
                  <td>{p.active ? <Badge tone="in">Activa</Badge> : <Badge>Desactivada</Badge>}</td>
                  <td className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setEditing(p)} icon={<Pencil className="size-4" aria-hidden />} aria-label={`Editar a ${p.full_name}`} />
                      <Button size="sm" onClick={() => navigate(`/admin/personas/${p.id}`)}>
                        Ver ficha
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>
      <PersonFormModal
        open={editing !== null}
        person={editing === "new" ? null : editing}
        areas={areas}
        onClose={() => setEditing(null)}
        onSaved={(p, isNew) => {
          setEditing(null);
          reload();
          if (isNew) navigate(`/admin/personas/${p.id}`);
        }}
      />
      <AreasModal
        open={areasOpen}
        areas={areas}
        onClose={() => setAreasOpen(false)}
        onChanged={() => {
          reloadAreas();
          reload();
        }}
      />
    </>
  );
}

export function PersonFormModal({
  open,
  person,
  areas,
  onClose,
  onSaved,
}: {
  open: boolean;
  person: Person | null;
  areas: Area[];
  onClose: () => void;
  onSaved: (p: Person, isNew: boolean) => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState({
    code: "",
    first_name: "",
    last_name: "",
    area_id: "",
    position: "",
    email: "",
    active: true,
    consent_signed: false,
    consent_date: isoDate(new Date()),
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setForm({
      code: person?.code ?? "",
      first_name: person?.first_name ?? "",
      last_name: person?.last_name ?? "",
      area_id: person?.area_id ? String(person.area_id) : "",
      position: person?.position ?? "",
      email: person?.email ?? "",
      active: person?.active ?? true,
      consent_signed: person?.consent_signed ?? false,
      consent_date: person?.consent_date ?? isoDate(new Date()),
    });
  }, [open, person]);

  const set = (k: keyof typeof form, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const body = {
        ...form,
        area_id: form.area_id ? Number(form.area_id) : null,
        consent_date: form.consent_signed ? form.consent_date : null,
      };
      const saved = person
        ? await api<Person>(`/api/admin/people/${person.id}`, { method: "PUT", json: body })
        : await api<Person>("/api/admin/people", { method: "POST", json: body });
      toast(person ? "Cambios guardados" : `${saved.full_name} registrada`);
      onSaved(saved, !person);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title={person ? `Editar a ${person.full_name}` : "Nueva persona"}
      onClose={onClose}
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button variant="primary" loading={busy} onClick={save}>
            {person ? "Guardar cambios" : "Registrar persona"}
          </Button>
        </>
      }
    >
      <form
        className="grid gap-4 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <Field label="Código de estudiante">{(id) => <Input id={id} value={form.code} onChange={(e) => set("code", e.target.value)} required />}</Field>
        <Field label="Área">
          {(id) => (
            <Select id={id} value={form.area_id} onChange={(e) => set("area_id", e.target.value)}>
              <option value="">Sin área</option>
              {areas.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Nombres">{(id) => <Input id={id} value={form.first_name} onChange={(e) => set("first_name", e.target.value)} required />}</Field>
        <Field label="Apellidos">{(id) => <Input id={id} value={form.last_name} onChange={(e) => set("last_name", e.target.value)} required />}</Field>
        <Field label="Cargo (opcional)">{(id) => <Input id={id} value={form.position} onChange={(e) => set("position", e.target.value)} />}</Field>
        <Field label="Email (opcional)">{(id) => <Input id={id} type="email" value={form.email} onChange={(e) => set("email", e.target.value)} />}</Field>
        <div className="flex flex-col gap-3 sm:col-span-2">
          <Checkbox
            label="Consentimiento firmado"
            hint="Obligatorio para enrolar rostro o huella. Guarda el documento firmado fuera del sistema."
            checked={form.consent_signed}
            onChange={(v) => set("consent_signed", v)}
          />
          {form.consent_signed && (
            <Field label="Fecha de firma" className="w-48">
              {(id) => <Input id={id} type="date" value={form.consent_date} onChange={(e) => set("consent_date", e.target.value)} />}
            </Field>
          )}
          <Checkbox label="Activa" hint="Las personas desactivadas no pueden marcar." checked={form.active} onChange={(v) => set("active", v)} />
        </div>
        {error && (
          <p className="text-sm text-danger sm:col-span-2" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="hidden" />
      </form>
    </Modal>
  );
}

function AreasModal({ open, areas, onClose, onChanged }: { open: boolean; areas: Area[]; onClose: () => void; onChanged: () => void }) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [renaming, setRenaming] = useState<{ id: number; name: string } | null>(null);

  const run = async (fn: () => Promise<unknown>, msg: string) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      toast(msg);
      onChanged();
      return true;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} title="Áreas" onClose={onClose}>
      <form
        className="flex items-end gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!name.trim()) return;
          if (await run(() => api("/api/admin/areas", { method: "POST", json: { name } }), `Área "${name}" creada`)) setName("");
        }}
      >
        <Field label="Nueva área" className="flex-1">
          {(id) => <Input id={id} value={name} onChange={(e) => setName(e.target.value)} placeholder="Ej.: Laboratorio de IA" />}
        </Field>
        <Button type="submit" variant="primary" loading={busy} icon={<Plus className="size-4" aria-hidden />}>
          Crear área
        </Button>
      </form>
      {error && (
        <p className="mt-2 text-sm text-danger" role="alert">
          {error}
        </p>
      )}
      <ul className="mt-4 divide-y divide-border rounded-lg border border-border">
        {areas.length === 0 && <li className="px-4 py-6 text-center text-sm text-muted">Todavía no hay áreas. Crea la primera arriba.</li>}
        {areas.map((a) => (
          <li key={a.id} className="flex items-center gap-2 px-3 py-2">
            {renaming?.id === a.id ? (
              <form
                className="flex flex-1 gap-2"
                onSubmit={async (e) => {
                  e.preventDefault();
                  if (await run(() => api(`/api/admin/areas/${a.id}`, { method: "PUT", json: { name: renaming.name } }), "Área renombrada"))
                    setRenaming(null);
                }}
              >
                <Input aria-label="Nuevo nombre" value={renaming.name} onChange={(e) => setRenaming({ id: a.id, name: e.target.value })} />
                <Button type="submit" size="sm" variant="primary">
                  Guardar
                </Button>
              </form>
            ) : (
              <>
                <span className="flex-1">
                  {a.name} <span className="text-sm text-muted">({a.people_count ?? 0} activas)</span>
                </span>
                <Button size="sm" variant="ghost" onClick={() => setRenaming({ id: a.id, name: a.name })} icon={<Pencil className="size-4" aria-hidden />} aria-label={`Renombrar ${a.name}`} />
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => run(() => api(`/api/admin/areas/${a.id}`, { method: "DELETE" }), "Área eliminada")}
                  icon={<Trash2 className="size-4" aria-hidden />}
                  aria-label={`Eliminar ${a.name}`}
                />
              </>
            )}
          </li>
        ))}
      </ul>
    </Modal>
  );
}
