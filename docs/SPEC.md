# Sistema de Asistencia Biométrica — Versión 1

Lee este documento completo antes de empezar. Eres un ingeniero full-stack senior y vas a construir desde cero, en esta carpeta, la v1 completa y funcional de un sistema de control de asistencia (check-in / check-out) con reconocimiento facial local y soporte preparado para lector de huellas.

Trabaja de forma autónoma: crea una lista de tareas y ejecútala de principio a fin, verificando cada parte. No entregues un esqueleto ni dejes TODOs en los flujos principales. Pregúntame solo si estás realmente bloqueado. Si una decisión de este documento resulta inviable, elige la alternativa más cercana, documéntala en el README y sigue. Guarda este documento tal cual en `docs/SPEC.md`.

## Contexto
- Proyecto universitario, piloto con 20 estudiantes. Corre 100% en local en una MacBook Pro M2 Pro (Apple Silicon) con su cámara integrada.
- Sin servicios en la nube ni APIs externas en tiempo de ejecución: las imágenes y los datos biométricos nunca salen de la máquina. Internet solo para instalar dependencias y descargar modelos durante el setup.
- El lector de huellas (AS608 por UART con adaptador USB-TTL) llega después. En v1 la huella es opcional, y la arquitectura debe quedar lista para que en v2 solo haya que conectarlo y configurarlo.
- Interfaz, mensajes, README y documentación en español; identificadores de código en inglés.

## Fase 0: skills de diseño (antes de escribir el frontend)
1. Instala dos skills a nivel de proyecto en `.claude/skills/`, clonando cada repositorio con `git clone --depth 1` en un directorio temporal:
   - `frontend-design` (oficial de Anthropic): de `https://github.com/anthropics/skills`, copia `skills/frontend-design` a `.claude/skills/frontend-design`.
   - `ui-ux-pro-max`: de `https://github.com/nextlevelbuilder/ui-ux-pro-max-skill`, copia la carpeta de la skill a `.claude/skills/ui-ux-pro-max` resolviendo symlinks (`cp -RL`), de modo que queden su `SKILL.md`, `scripts/` y `data/`.
2. Verifica que existan ambos `SKILL.md`, léelos completos y síguelos al construir la interfaz.
3. Con el script de búsqueda de ui-ux-pro-max, genera y guarda un design system para "kiosco de asistencia biométrica + panel de RR.HH." (stack React). Con frontend-design, define una dirección estética propia del producto.
4. Si alguna descarga falla, sigue con los lineamientos de diseño de este documento y avísame al final.

## Stack (decisiones fijas)
- Backend: Python 3.11 en un entorno creado con `uv` (si no está, instálalo con Homebrew), FastAPI + Uvicorn, SQLite en modo WAL (SQLAlchemy 2 o SQLModel), configuración con Pydantic Settings y `.env`.
- Frontend: React + Vite + TypeScript + Tailwind CSS, iconos lucide-react y fuentes empaquetadas localmente (p. ej., @fontsource). Sin CDNs: la app debe funcionar sin internet.
- FastAPI sirve el build del frontend: todo queda en `http://localhost:8000` (kiosco en `/`, panel de RR.HH. en `/admin`). Modo desarrollo opcional con Vite y proxy.
- La cámara se abre en el navegador con `getUserMedia` (localhost es contexto seguro). El frontend envía frames JPEG al backend por HTTP (~5 fps, 640 px de ancho). El backend no abre la cámara.
- El flujo de reconocimiento (sesión, reto de vida, decisión) vive en el backend como una máquina de estados testeable; el frontend solo muestra estados.

## Reconocimiento facial
- Interfaz `FaceEngine` (detección, 5 landmarks, embedding, similitud) con implementaciones seleccionables por `.env`:
  - `insightface` (por defecto): pack `buffalo_l` (SCRFD + ArcFace ResNet50, embeddings de 512 dimensiones, similitud coseno) sobre onnxruntime en CPU, cargando solo los módulos de detección y reconocimiento.
  - `sface` (respaldo): OpenCV YuNet + SFace, con los modelos ONNX del OpenCV Zoo. Si InsightFace no se instala o falla al cargar, el sistema arranca con SFace automáticamente y lo indica en el panel y en los logs.
  - `fake`, para los tests.
- Los modelos se descargan en el setup para que el primer arranque sea inmediato.
- Cada plantilla guarda con qué motor se generó. Incluye un comando de re-indexado que regenere las plantillas desde las fotos de enrolamiento cuando se cambie de motor.
- Robustez:
  - Calidad por frame: un solo rostro (si hay varios, pedir que quede una persona), tamaño mínimo, nitidez (varianza del Laplaciano), iluminación y pose casi frontal. Mensajes de guía en pantalla: "acércate", "mira al frente", "falta luz".
  - Identificación 1:N contra plantillas en memoria (matriz numpy que se recarga al enrolar). Aceptar solo si se supera el umbral, hay margen suficiente entre el primer y el segundo candidato, y la identidad se confirma en al menos 3 de 5 frames consecutivos.
  - Umbrales configurables por motor, con valores iniciales razonables (p. ej., ~0.45 coseno para buffalo_l y 0.363 para SFace, su punto publicado). No muestres porcentajes de coincidencia inventados: el panel muestra la similitud real y el umbral.
  - Prueba de vida activa, activada por defecto y desactivable: reto aleatorio "gira la cabeza a la izquierda/derecha", detectado con los 5 landmarks (posición de la nariz respecto a los ojos, independiente del motor). Debe tener tiempo límite, considerar que la vista está espejada y verificar que la identidad se mantenga durante el reto. Deja preparada una interfaz para añadir anti-spoofing pasivo más adelante, sin bloquear la v1 por ello.
- Enrolamiento guiado desde el panel: 5 capturas por persona (frontal, leve giro a cada lado, con y sin lentes si aplica) con control de calidad, o subida de fotos. Advierte si el rostro ya coincide con otra persona.
- Calibración (comando y botón en el panel): con las plantillas enroladas, calcula las distribuciones de similitud genuina e impostora, estima FAR/FRR para varios umbrales, sugiere uno y exporta CSV + gráfico para el informe del proyecto.

## Huella (opcional en v1, lista para v2)
- Interfaz `FingerprintProvider` con tres implementaciones:
  - `disabled` (por defecto).
  - `simulated`: panel de pruebas en el kiosco, visible solo con este proveedor, para simular la huella de una persona con confianza alta, media o sin coincidencia.
  - `as608`: con `adafruit-circuitpython-fingerprint` + `pyserial`, puerto y baudios en `.env`, búsqueda 1:N que devuelve ID y puntaje, enrolamiento con dos capturas y respaldo de plantillas en la base de datos. Márcalo como experimental: aún no hay hardware para probarlo.
- Lógica multimodal, implementada y testeada desde ya con `simulated`:
  - Puntaje de huella alto → acceso por huella (la foto se guarda igual para auditoría).
  - Puntaje medio → ese ID es candidato: verificación facial 1:1 contra él + prueba de vida.
  - Sin coincidencia o mala imagen → rostro 1:N + prueba de vida, o código de estudiante + rostro 1:1 si `FALLBACK_MODE=code_plus_face`.
  - Sin huella configurada (v1) → rostro 1:N + prueba de vida.
- Cada marcación registra el método (ROSTRO, HUELLA, HUELLA+ROSTRO, CODIGO+ROSTRO, MANUAL) y sus puntajes.
- Documenta en `CLAUDE.md` y en el README los pasos para v2: cableado (TX/RX cruzados, verificar el voltaje del módulo), cómo encontrar el puerto con `ls /dev/tty.usb*`, variables de `.env`, un comando de diagnóstico del sensor y el enrolamiento de huellas.

## Lógica de asistencia
- Tipo automático: si la última marcación de la persona es una ENTRADA abierta dentro de `MAX_SHIFT_HOURS` (16 por defecto), la nueva es SALIDA; si no, es ENTRADA. Si la ENTRADA abierta superó ese límite, esa jornada queda INCOMPLETA y la nueva marcación es ENTRADA.
- Anti-rebote: ignora repeticiones de la misma persona dentro de `DEBOUNCE_SECONDS` (120 por defecto) y muestra "Ya registraste tu entrada hace X s".
- Jornadas: empareja ENTRADA→SALIDA sin cortar por día calendario (un turno que cruza la medianoche pertenece al día de la entrada). Varias jornadas en un día se suman. Las horas se expresan en decimal (2 decimales) y en HH:MM.
- Las marcaciones son inmutables. RR.HH. puede anular una o agregar una manual (p. ej., completar una salida olvidada), siempre con motivo obligatorio y registro en la auditoría.
- Las fechas se guardan en UTC y se muestran en la zona horaria del sistema (configurable).
- Cada marcación guarda la mejor captura frontal de la sesión (JPEG, ~640 px) en `data/captures/AAAA/MM/DD/`. Los intentos fallidos no guardan foto, salvo que se active `SAVE_FAILED_ATTEMPTS`.

## Datos (SQLite)
- `areas`.
- `people`: código único, nombres, apellidos, área, cargo y email opcionales, activo, consentimiento firmado + fecha, `fingerprint_slot` (nullable).
- `face_templates`: persona, embedding cifrado, motor, calidad, ruta de la foto de enrolamiento.
- `attendance_events`: persona, timestamp, tipo, método, puntajes, resultado de la prueba de vida, ruta de la foto, anulada + motivo.
- `audit_log`: altas, ediciones, enrolamientos, exportaciones, anulaciones y cambios de configuración.
- Seed opcional con áreas y marcaciones de demostración (sin biometría) para ver los reportes poblados.

## Frontend
- Kiosco (pantalla completa, legible a 1–2 m):
  - Cámara espejada con guía ovalada y reloj grande.
  - Estados distinguibles por ícono + texto + color: esperando, detectando, reto de vida, ENTRADA registrada, SALIDA registrada, no reconocido, ya registrado, sin personas enroladas y error de cámara.
  - Tarjeta de resultado con la foto capturada, nombre, código, área, tipo, hora y, en la salida, las horas trabajadas en la jornada. Vuelve sola al inicio en ~4 s. Sonido de confirmación desactivable.
  - Botón "Ingresar código" para el modo código + rostro, e indicador de huella ("no conectada (opcional)" en v1).
  - Selector de cámara (en macOS puede aparecer la del iPhone por Continuity Camera) y manejo del permiso denegado con instrucciones.
- Panel de RR.HH. (`/admin`, protegido con la contraseña de `.env` y sesión con cookie httpOnly):
  - Resumen del día: presentes ahora, entradas, salidas, jornadas incompletas, desglose por área y últimas marcaciones con miniatura.
  - Personas: CRUD, búsqueda, enrolamiento facial guiado, estado de plantillas y huella, desactivar y eliminar datos biométricos.
  - Marcaciones: tabla filtrable (fechas, área, persona, tipo, método) con miniaturas ampliables, y opciones para anular y agregar marcaciones manuales.
  - Horas: jornadas con entrada, salida, horas y estado; totales por persona en el rango.
  - Exportar.
  - Configuración: umbrales, anti-rebote, prueba de vida, modo de respaldo, motor activo, estado de la huella y calibración.
  - Auditoría.
- Diseño: aplica las dos skills. Son dos contextos coherentes entre sí: un kiosco de alto contraste para lectura a distancia y un panel denso en datos pero limpio.
  - Modo claro/oscuro y accesibilidad (contraste AA, foco visible, nunca depender solo del color).
  - Animaciones sutiles y estados de carga, vacío y error en todas las vistas.
  - Evita la estética genérica de plantilla.

## Exportación (clave para RR.HH.)
- Jornadas (CSV y XLSX): fecha, código, nombre, área, hora de entrada, hora de salida, horas trabajadas (decimal y HH:MM), estado (COMPLETA/INCOMPLETA), método de entrada y de salida, foto de entrada y de salida (ruta relativa).
- Marcaciones (CSV y XLSX): fecha, hora, código, nombre, área, tipo, método, puntajes, prueba de vida, anulada y foto.
- Resumen por persona: días asistidos, total de horas y jornadas incompletas.
- ZIP con el CSV y las fotos referenciadas, con rutas que coincidan.
- CSV en UTF-8 con BOM (para que Excel muestre bien las tildes) y separador configurable (coma por defecto).
- Filtros por rango de fechas y área en todas las exportaciones. Cada exportación queda registrada en la auditoría.

## Seguridad y privacidad
- El servidor escucha solo en `127.0.0.1`. Las fotos y capturas solo se sirven a sesiones autenticadas del panel.
- Embeddings cifrados en reposo con Fernet (clave en `.env`) y carpeta `data/` con permisos restrictivos. El setup nunca sobrescribe claves existentes de `.env`; si la clave se pierde, se re-indexa desde las fotos.
- No se puede enrolar a nadie sin marcar el consentimiento. "Eliminar datos biométricos" borra las plantillas y fotos de enrolamiento de esa persona.
- Aviso de licencia en el README: los modelos preentrenados de InsightFace son solo para uso no comercial y de investigación (válido para este proyecto universitario); para uso comercial, usar el motor `sface`.

## Calidad
- Errores manejados en todos los endpoints con mensajes claros en español; logs rotativos en `data/logs/`.
- Tests con pytest, usando el motor `fake`, que cubran:
  - el tipo automático de marcación y el anti-rebote;
  - el cálculo de horas (cruce de medianoche, varias jornadas al día, jornadas incompletas);
  - la tabla de decisión multimodal con huella simulada;
  - las exportaciones CSV/XLSX y los endpoints principales.
- Prueba de integración del motor real con rostros recortados de la imagen de ejemplo de InsightFace (`insightface.data.get_image('t1')`), que se salte sola si el motor no está disponible.
- El frontend compila sin errores de TypeScript ni de lint.

## Scripts y documentación
- `scripts/setup.sh`, idempotente y no interactivo:
  - Verifica Xcode Command Line Tools, Python 3.11 vía `uv` y Node LTS 20+. Si falta algo, indica el comando exacto para instalarlo.
  - Instala dependencias, descarga los modelos (buffalo_l y los ONNX de YuNet/SFace) y compila el frontend.
  - Crea `.env` desde `.env.example` generando la contraseña de admin y la clave de cifrado, inicializa la base de datos e imprime la contraseña al final.
- `scripts/start.sh` arranca el servidor en `http://localhost:8000` y abre el navegador; `scripts/dev.sh` arranca el modo desarrollo con recarga.
- `README.md` con:
  - requisitos e instalación en pocos comandos;
  - cómo dar permiso de cámara al navegador en macOS;
  - primer uso: crear área, registrar y enrolar a una persona, marcar y exportar;
  - calibración;
  - solución de problemas: InsightFace no instala, cámara bloqueada, puerto ocupado;
  - guía de conexión de la huella para v2.
- `CLAUDE.md` con arquitectura, convenciones, comandos y el plan de v2, para retomar el proyecto en futuras sesiones.

## Verificación final (definición de terminado)
1. Ejecuta `scripts/setup.sh` y `scripts/start.sh`; confirma que `/api/health` responde e informa el motor facial activo.
2. Todos los tests pasan y el build del frontend no tiene errores.
3. Prueba de humo por API con ambos motores: crea un área y personas, enrólalas con rostros de la imagen de ejemplo, reconoce a cada una, registra entrada y salida (al menos un caso con huella simulada) y exporta CSV/XLSX con las horas correctas.
4. E2E con Playwright y Chromium usando cámara falsa (`--use-fake-ui-for-media-stream --use-fake-device-for-media-stream`): el kiosco carga y obtiene video, y en el panel se puede iniciar sesión, listar personas y exportar. Toma capturas del kiosco y del panel, revísalas contra el design system y corrige lo que se vea mal.
5. Al terminar, dame un resumen: qué se construyó, cómo correrlo, limitaciones conocidas y los pasos exactos para que pruebe con mi cara.

## Fuera de alcance en v1
Nube, múltiples sedes, app móvil y cálculo de pagos (solo horas trabajadas).
