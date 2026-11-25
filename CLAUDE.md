# CLAUDE.md: Asistencia biométrica v1

Contexto para retomar el proyecto en futuras sesiones. La especificación completa está en
`docs/SPEC.md`; la guía de usuario, en `docs/GUIA-DE-USO.md`; el informe del curso, en `docs/informe/`.

## Qué es

Kiosco de asistencia (entrada/salida) con reconocimiento facial local y panel de RR.HH. Piloto
universitario, 20 estudiantes, MacBook Pro M2 Pro. Sin nube: todo corre en `127.0.0.1:8000`.
UI, mensajes y docs en español; identificadores de código en inglés.

## Arquitectura

```
Navegador (getUserMedia) ──JPEG 640px ~5fps──► FastAPI (127.0.0.1:8000) ──► SQLite WAL (data/asistencia.db)
  kiosco  /                                     ├─ KioskSession (máquina de estados, en memoria)
  panel   /admin (cookie httpOnly)              ├─ EngineManager → FaceEngine (insightface | sface | fake)
                                                ├─ TemplateIndex (matriz numpy, 1:N y 1:1)
                                                ├─ FingerprintProvider (disabled | simulated | as608)
                                                └─ servicios: attendance, shifts, exports, enrollment, calibration
```

- `backend/app/context.py`: `AppContext` reúne settings, BD, cifrado, motor, índice, huella,
  configuración en caliente (`runtime`) y el gestor de sesiones del kiosco. Se guarda en
  `app.state.ctx`; los routers lo obtienen con `Depends(get_ctx)`.
- `backend/app/kiosk/session.py`: **toda la lógica del kiosco** (calidad → votos 3/5 → anti-rebote
  → reto de vida → registro). El frontend solo envía frames, huella o código y pinta `view()`.
  Estados: waiting, detecting, challenge, need_code, success, already_registered, not_recognized,
  liveness_failed, no_enrolled, error, cancelled.
- `backend/app/kiosk/decision.py`: tabla multimodal pura (huella alta/media/ninguna → ruta).
- `backend/app/face/`: `base.py` (interfaz, landmarks, pose, `norm_crop`), motores,
  `quality.py`, `index.py`, `liveness.py` (giro + `PassiveLivenessChecker`), `manager.py`
  (respaldo automático a SFace), `samples.py` (rostros de `t1` para pruebas).
- `backend/app/services/runtime_config.py`: valores editables desde el panel = `.env` + overrides
  en la tabla `app_settings`. Cambiar `face_engine` recarga el motor y el índice.
- Frontend: React 19 + Vite 6 + Tailwind 4 (tokens en `src/index.css`), lucide-react, fuentes
  Fira empaquetadas con @fontsource. FastAPI sirve `frontend/dist` (SPA con fallback a index.html).

## Convenciones

- Fechas en UTC en la BD (`UTCDateTime` devuelve aware UTC); se muestran en `ctx.tz`
  (`TIMEZONE` o la del sistema). Usa `app/timeutil.py`.
- Las marcaciones nunca se editan: solo `voided` + motivo, o manuales (`MANUAL`) con motivo.
  Toda acción administrativa llama a `services/audit.audit()` antes del `commit()`.
- Errores al usuario: `AppError("mensaje en español", status_code, code=...)`. Nunca
  `HTTPException` con texto en inglés.
- Embeddings: siempre normalizados L2 y cifrados con `ctx.cipher` (Fernet). Cada plantilla guarda
  su `engine`; el índice solo carga las del motor activo.
- Landmarks normalizados: ojo izq. imagen, ojo der. imagen, nariz, comisura izq., comisura der.
  Los frames llegan **sin espejar**; `yaw > 0` = la persona gira a SU izquierda. Sí llegan girados
  según `useCamera().rotation` (botón *Girar imagen*, guardado por nombre de cámara en localStorage
  porque Chrome puede cambiar el `deviceId`); la vista previa usa `components/CameraPreview.tsx`.
- Fotos: rutas relativas a `data/` con `/` (`captures/AAAA/MM/DD/...jpg`), servidas solo por
  `/api/admin/files/...` con sesión.
- Diseño: ver `docs/DESIGN.md` y `design-system/asistencia-biometrica/MASTER.md`. Skills de diseño
  en `.claude/skills/` (frontend-design, ui-ux-pro-max). Estados = ícono + texto + color.

## Comandos

```bash
scripts/setup.sh                 # instalación idempotente (macOS; también Git Bash)
scripts/start.sh                 # servidor + navegador   (NO_BROWSER=1 para no abrirlo)
scripts/dev.sh                   # backend --reload + Vite :5173
scripts/test.sh [quick]          # verificación completa

cd backend
uv run pytest -q                 # 79 tests (motor fake + integración con motores reales)
uv run ruff check app tests scripts
uv run python scripts/smoke_api.py   # prueba de humo, ambos motores, puerto 8765
uv run python -m app.cli --help      # env-init, init-db, download-models, check-engine, seed-demo,
                                     # reindex, calibrate, fingerprint-diagnose/enroll/restore

cd frontend
npm run typecheck && npm run lint && npm run build
npx playwright test              # E2E con cámara falsa (levanta backend en :8766)
```

## Estado de la v1 (verificado)

- pytest 69/69, ruff limpio, tsc + eslint sin errores ni advertencias, build OK.
- Prueba de humo 30/30 con insightface y sface (enrolamiento con rostros de `t1`, 1:N, huella
  simulada alta/media, re-indexado al cambiar de motor, CSV/XLSX/ZIP con horas correctas).
- E2E 5/5, incluido un flujo con video de rostro (reto de vida → falla por tiempo → ENTRADA →
  "ya registrado").
- 31/10: corregidos foto ↔ identidad y anti-rebote concurrente (`BEGIN IMMEDIATE`); ver
  `docs/REVISION-2026-10-31.md`.
- 24/11: resumen personal «Tu semana» en el kiosco (`services/personal_summary.py`), solo tras
  identificarse. Verificado: pytest 79/79, humo 30/30 con ambos motores, E2E 6/6.

## Plan de v2

1. **Huella AS608:** conectar (TX/RX cruzados, verificar 3.3 V/5 V), `ls /dev/tty.usb*`, `.env`
   (`FINGERPRINT_PROVIDER=as608`, `FINGERPRINT_PORT`), `app.cli fingerprint-diagnose`, enrolar con
   `fingerprint-enroll --code ...`. Probar `as608.py` con hardware real (está marcado como
   experimental), calibrar `FINGERPRINT_HIGH_SCORE`/`MEDIUM_SCORE` con puntajes reales.
   El kiosco ya hace long-poll a `/fingerprint/scan` cuando el sensor está conectado.
2. **Anti-spoofing pasivo:** implementar `PassiveLivenessChecker` (p. ej. MiniFASNet ONNX) y
   asignarlo a `ctx.passive_liveness`; llamarlo en `KioskSession._on_identified` con el mejor frame.
3. Calibración con datos de varias sesiones (genuinos de días distintos) para el informe.
4. Opcional: aceleración CoreML en onnxruntime (`CoreMLExecutionProvider`) si hiciera falta.

Fuera de alcance: nube, múltiples sedes, app móvil, cálculo de pagos.
