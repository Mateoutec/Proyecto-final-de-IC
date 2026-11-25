import {
  ClipboardList,
  Download,
  LayoutDashboard,
  LockKeyhole,
  LogOut,
  Menu,
  Moon,
  MonitorSmartphone,
  ScrollText,
  SlidersHorizontal,
  Sun,
  Timer,
  TriangleAlert,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Button, Spinner, ToastProvider, cx } from "../components/ui";
import { api, setUnauthorizedHandler } from "../lib/api";
import { resolvedTheme, toggleTheme } from "../lib/theme";
import type { EngineStatus } from "../lib/types";
import { AuditPage } from "./pages/Audit";
import { DashboardPage } from "./pages/Dashboard";
import { EventsPage } from "./pages/Events";
import { ExportPage } from "./pages/Export";
import { PeoplePage } from "./pages/People";
import { PersonDetailPage } from "./pages/PersonDetail";
import { SettingsPage } from "./pages/Settings";
import { ShiftsPage } from "./pages/Shifts";

const NAV = [
  { to: "/admin", label: "Resumen del día", icon: LayoutDashboard, end: true },
  { to: "/admin/personas", label: "Personas", icon: Users },
  { to: "/admin/marcaciones", label: "Marcaciones", icon: ClipboardList },
  { to: "/admin/horas", label: "Horas", icon: Timer },
  { to: "/admin/exportar", label: "Exportar", icon: Download },
  { to: "/admin/configuracion", label: "Configuración", icon: SlidersHorizontal },
  { to: "/admin/auditoria", label: "Auditoría", icon: ScrollText },
];

export function AdminApp() {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    document.title = "Asistencia · Panel RR.HH.";
    api<{ authenticated: boolean }>("/api/admin/me")
      .then((r) => setAuthed(r.authenticated))
      .catch(() => setAuthed(false));
    setUnauthorizedHandler(() => setAuthed(false));
    return () => setUnauthorizedHandler(null);
  }, []);

  if (authed === null) {
    return (
      <div className="grid min-h-full place-items-center">
        <Spinner label="Cargando el panel" />
      </div>
    );
  }
  if (!authed) return <LoginPage onLogin={() => setAuthed(true)} />;
  return (
    <ToastProvider>
      <Shell onLogout={() => setAuthed(false)}>
        <Routes>
          <Route index element={<DashboardPage />} />
          <Route path="personas" element={<PeoplePage />} />
          <Route path="personas/:id" element={<PersonDetailPage />} />
          <Route path="marcaciones" element={<EventsPage />} />
          <Route path="horas" element={<ShiftsPage />} />
          <Route path="exportar" element={<ExportPage />} />
          <Route path="configuracion" element={<SettingsPage />} />
          <Route path="auditoria" element={<AuditPage />} />
          <Route path="*" element={<DashboardPage />} />
        </Routes>
      </Shell>
    </ToastProvider>
  );
}

function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div className="grid min-h-full place-items-center bg-bg p-4">
      <form
        className="w-full max-w-sm rounded-2xl border border-border bg-surface p-7 shadow-sm"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            await api("/api/admin/login", { method: "POST", json: { password } });
            onLogin();
          } catch (err) {
            setError((err as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="flex items-center gap-3">
          <span className="grid size-11 place-items-center rounded-xl bg-primary text-on-primary">
            <LockKeyhole className="size-5" aria-hidden />
          </span>
          <div>
            <h1 className="font-display text-2xl font-semibold">Panel de RR.HH.</h1>
            <p className="text-sm text-muted">Asistencia biométrica</p>
          </div>
        </div>
        <label htmlFor="admin-password" className="mt-6 block text-sm font-medium">
          Contraseña
        </label>
        <input
          id="admin-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1.5 h-11 w-full rounded-lg border border-border bg-surface px-3"
          aria-invalid={!!error}
          required
        />
        {error && (
          <p className="mt-2 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
        <p className="mt-2 text-sm text-muted">Es ADMIN_PASSWORD del archivo .env (setup.sh la muestra al terminar).</p>
        <Button type="submit" variant="primary" className="mt-5 w-full" loading={busy}>
          Iniciar sesión
        </Button>
        <Link to="/" className="mt-4 block text-center text-sm text-muted underline-offset-4 hover:underline">
          Volver al kiosco
        </Link>
      </form>
    </div>
  );
}

function Shell({ children, onLogout }: { children: ReactNode; onLogout: () => void }) {
  const [theme, setTheme] = useState(resolvedTheme());
  const [menuOpen, setMenuOpen] = useState(false);
  const [engine, setEngine] = useState<EngineStatus | null>(null);
  const location = useLocation();

  const loadEngine = useCallback(() => {
    api<{ engine: EngineStatus }>("/api/kiosk/status")
      .then((s) => setEngine(s.engine))
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    loadEngine();
    setMenuOpen(false);
  }, [location.pathname, loadEngine]);

  const logout = async () => {
    await api("/api/admin/logout", { method: "POST" }).catch(() => undefined);
    onLogout();
  };

  return (
    <div className="flex min-h-full flex-col lg:flex-row">
      <aside
        className={cx(
          "z-30 flex flex-col bg-rail text-rail-fg lg:sticky lg:top-0 lg:h-screen lg:w-64 lg:shrink-0",
          menuOpen ? "fixed inset-0" : "",
        )}
      >
        <div className="flex items-center gap-3 px-5 py-4">
          <img src="/favicon.svg" alt="" className="size-8" />
          <div className="leading-tight">
            <p className="font-display text-lg font-semibold">Asistencia</p>
            <p className="text-xs opacity-75">Panel de RR.HH.</p>
          </div>
          <button
            type="button"
            className="ml-auto grid size-10 cursor-pointer place-items-center rounded-lg hover:bg-white/10 lg:hidden"
            onClick={() => setMenuOpen((v) => !v)}
            aria-expanded={menuOpen}
            aria-label="Menú"
          >
            <Menu className="size-5" aria-hidden />
          </button>
        </div>
        <nav className={cx("flex-1 flex-col gap-0.5 px-3 pb-3", menuOpen ? "flex" : "hidden lg:flex")} aria-label="Secciones">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cx(
                  "flex h-11 items-center gap-3 rounded-lg px-3 text-[15px] transition-colors",
                  isActive ? "bg-white/14 font-semibold text-white" : "opacity-85 hover:bg-white/8 hover:opacity-100",
                )
              }
            >
              <item.icon className="size-[18px]" aria-hidden />
              {item.label}
            </NavLink>
          ))}
          <div className="mt-auto flex flex-col gap-0.5 border-t border-white/10 pt-3">
            <Link to="/" className="flex h-10 items-center gap-3 rounded-lg px-3 text-sm opacity-85 hover:bg-white/8">
              <MonitorSmartphone className="size-[18px]" aria-hidden /> Abrir el kiosco
            </Link>
            <button
              type="button"
              onClick={() => setTheme(toggleTheme())}
              className="flex h-10 cursor-pointer items-center gap-3 rounded-lg px-3 text-left text-sm opacity-85 hover:bg-white/8"
            >
              {theme === "dark" ? <Sun className="size-[18px]" aria-hidden /> : <Moon className="size-[18px]" aria-hidden />}
              {theme === "dark" ? "Tema claro" : "Tema oscuro"}
            </button>
            <button
              type="button"
              onClick={logout}
              className="flex h-10 cursor-pointer items-center gap-3 rounded-lg px-3 text-left text-sm opacity-85 hover:bg-white/8"
            >
              <LogOut className="size-[18px]" aria-hidden /> Cerrar sesión
            </button>
          </div>
        </nav>
      </aside>
      <div className="min-w-0 flex-1">
        {engine && (engine.fallback || !engine.ready) && (
          <div className="flex items-start gap-2 border-b border-warn/40 bg-warn-soft px-6 py-2.5 text-sm text-warn" role="alert">
            <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
            <p>
              {engine.ready
                ? `Motor de respaldo activo (${engine.active}). ${engine.fallback_reason ?? ""}`
                : `Reconocimiento facial no disponible: ${engine.error ?? "revisa los logs"}`}{" "}
              <Link to="/admin/configuracion" className="font-semibold underline">
                Ver configuración
              </Link>
            </p>
          </div>
        )}
        <main className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
