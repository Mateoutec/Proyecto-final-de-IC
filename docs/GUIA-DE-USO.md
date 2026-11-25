# Guía de uso: Asistencia biométrica (v1)

Control de asistencia (entrada y salida) con reconocimiento facial **100 % local** para un piloto
universitario de 20 estudiantes. Corre en una MacBook (Apple Silicon) con su cámara integrada: las
imágenes y los datos biométricos nunca salen de la máquina. La huella dactilar (lector AS608) es
opcional en la v1 y queda lista para conectarse en la v2.

- **Kiosco** en `http://localhost:8000`: cámara espejada con guía ovalada, reloj grande, prueba de
  vida (giro de cabeza), tarjeta de marcación con foto y horas trabajadas.
- **Panel de RR.HH.** en `http://localhost:8000/admin`: resumen del día, personas y enrolamiento
  guiado, marcaciones (anular / agregar manual), horas, exportación CSV/XLSX/ZIP, configuración,
  calibración y auditoría.

La especificación original está en [`docs/SPEC.md`](SPEC.md) y la dirección de diseño en
[`docs/DESIGN.md`](DESIGN.md).

---

## Requisitos

| Requisito | Cómo instalarlo (macOS) |
|---|---|
| Xcode Command Line Tools | `xcode-select --install` |
| Homebrew | <https://brew.sh> |
| uv (gestiona Python 3.11) | `brew install uv` (setup.sh lo instala si hay Homebrew) |
| Node.js 20 o superior | `brew install node@22` |
| Chrome, Edge o Safari actualizado | — |

Internet solo se usa durante la instalación (dependencias y modelos, unos 300 MB).

## Instalación

```bash
cd asistencia-biometrica
chmod +x scripts/*.sh
scripts/setup.sh      # instala todo, descarga modelos, crea .env y compila el frontend
scripts/start.sh      # arranca en http://localhost:8000 y abre el navegador
```

`setup.sh` es idempotente: se puede repetir sin perder nada. Al final imprime la **contraseña del
panel** (también está en `.env`, variable `ADMIN_PASSWORD`). Nunca sobrescribe claves que ya existan
en `.env`.

Para desarrollo con recarga automática: `scripts/dev.sh` (backend en `:8000`, Vite en `:5173`).

## Permiso de cámara en macOS

1. Abre `http://localhost:8000` (localhost es un contexto seguro: no hace falta HTTPS).
2. **Chrome / Edge:** cuando lo pida, elige *Permitir*. Si lo bloqueaste, haz clic en el ícono de
   cámara (o del candado) de la barra de direcciones → *Permitir* y recarga.
3. **Safari:** menú *Safari → Configuración → Sitios web → Cámara → localhost → Permitir*.
4. Si macOS lo bloquea: *Configuración del Sistema → Privacidad y seguridad → Cámara*, activa tu
   navegador y **reinícialo**.
5. Si aparece la cámara del iPhone (Continuity Camera), usa el botón **Cámara** del kiosco y elige
   *Cámara FaceTime HD* (la integrada). La elección se recuerda.

## Primer uso (5 minutos)

1. **Entrar al panel:** `http://localhost:8000/admin` con la contraseña de `.env`.
2. **Crear un área:** *Personas → Áreas → Nueva área* (p. ej., "Laboratorio de Cognitive Computing").
3. **Registrar a una persona:** *Personas → Nueva persona*. Completa código, nombres y apellidos,
   área y marca **Consentimiento firmado** (sin consentimiento no se puede enrolar).
4. **Enrolar el rostro:** en la ficha, *Enrolar con cámara*. Son 5 capturas guiadas: de frente, leve
   giro a cada lado, con lentes (u otra expresión; se puede omitir) y sin lentes. Cada captura pasa
   control de calidad; si el rostro ya coincide con otra persona, el sistema avisa. También puedes
   *Subir fotos* (JPG/PNG).
5. **Marcar:** abre `http://localhost:8000`, colócate frente a la cámara, espera la identificación
   (3 de 5 frames), gira la cabeza hacia donde indique la flecha y listo: aparece la tarjeta con
   **ENTRADA** y la hora. La siguiente marcación (pasado el anti-rebote de 120 s) será **SALIDA** con
   las horas de la jornada.
6. **Exportar:** *Exportar* → elige rango y área → CSV, Excel o ZIP con fotos.

¿Quieres ver los reportes poblados sin enrolar a nadie? Carga datos de demostración (20 personas
`DEMO001…DEMO020` con 2 semanas de marcaciones, sin biometría):

```bash
cd backend && uv run python -m app.cli seed-demo          # crear
cd backend && uv run python -m app.cli seed-demo --clear  # borrar
```

## Cómo funciona el reconocimiento

- **Motores** (`FACE_ENGINE` en `.env` o desde *Configuración*):
  - `insightface` (por defecto): pack **buffalo_l**, detector SCRFD + ArcFace ResNet50 (embeddings
    de 512 dimensiones, similitud coseno) sobre onnxruntime en CPU. Solo se cargan detección y
    reconocimiento.
  - `sface` (respaldo): OpenCV **YuNet + SFace** (128 dimensiones). Si InsightFace no carga, el
    sistema arranca con SFace automáticamente y lo avisa en el panel y en `data/logs/app.log`.
  - `fake`: solo para tests.
- **Calidad por frame:** un solo rostro (si hay varios, pide que quede una persona), tamaño mínimo,
  centrado en el óvalo, nitidez (varianza del Laplaciano), iluminación y pose casi frontal. El kiosco
  guía con mensajes como "Acércate un poco", "Mira al frente" o "Falta luz".
- **Identificación 1:N** contra una matriz numpy en memoria (se recarga al enrolar). Se acepta solo
  si la similitud supera el **umbral** del motor, hay **margen** suficiente con el segundo candidato
  (0.06 por defecto) y la identidad se confirma en **3 de 5 frames**. El panel muestra la similitud
  real y el umbral, nunca porcentajes inventados.
- **Prueba de vida activa** (desactivable): reto aleatorio "gira la cabeza a tu izquierda/derecha",
  medido con la posición de la nariz respecto de los ojos (5 landmarks, igual para ambos motores).
  Tiene tiempo límite (7 s), tiene en cuenta que la vista está espejada y verifica en cada frame que
  la identidad no cambie. Hay una interfaz (`PassiveLivenessChecker`) lista para sumar anti-spoofing
  pasivo más adelante.
- **Tipo automático:** si la última marcación es una ENTRADA abierta de menos de `MAX_SHIFT_HOURS`
  (16 h), la nueva es SALIDA; si no, ENTRADA (y la anterior queda INCOMPLETA).
- **Jornadas:** ENTRADA→SALIDA sin cortar por día calendario (un turno que cruza la medianoche
  cuenta en el día de la entrada); varias jornadas del día se suman; horas en decimal y en HH:MM.
- Cada marcación guarda la mejor captura frontal en `data/captures/AAAA/MM/DD/`.

## Calibración

Con varias personas enroladas: *Configuración → Calibración → Calcular calibración*, o bien:

```bash
cd backend && uv run python -m app.cli calibrate
```

Calcula las similitudes genuinas (misma persona) e impostoras (personas distintas), estima FAR y
FRR para umbrales de 0.00 a 1.00 y sugiere el umbral con menor FRR que cumple FAR ≤ 0,1 %. Guarda
en `data/calibration/<motor>_<fecha>/`: `far_frr.csv`, `similitudes.csv`, `grafico.png` (histogramas
+ curvas, útil para el informe) y `resumen.json`. Desde el panel puedes aplicar el umbral sugerido.

> Los pares genuinos salen de las capturas de enrolamiento (misma sesión), así que el FRR real
> puede ser algo mayor. Para el informe conviene enrolar, esperar unos días y volver a calibrar.

## Configuración (`.env`)

| Variable | Por defecto | Qué hace |
|---|---|---|
| `FACE_ENGINE` | `insightface` | `insightface`, `sface` o `fake` |
| `THRESHOLD_INSIGHTFACE` / `THRESHOLD_SFACE` | `0.45` / `0.363` | Umbral de similitud coseno por motor |
| `IDENTIFY_MARGIN` | `0.06` | Margen mínimo entre el 1.º y el 2.º candidato |
| `LIVENESS_ENABLED` | `true` | Prueba de vida por giro de cabeza |
| `DEBOUNCE_SECONDS` | `120` | Anti-rebote por persona |
| `MAX_SHIFT_HOURS` | `16` | Duración máxima de una jornada abierta |
| `FALLBACK_MODE` | `face` | `face` o `code_plus_face` (código + rostro 1:1) |
| `SAVE_FAILED_ATTEMPTS` | `false` | Guardar foto de los intentos fallidos |
| `TIMEZONE` | (sistema) | Zona para mostrar fechas, p. ej. `America/Lima` |
| `CSV_DELIMITER` | `,` | Separador de los CSV |
| `FINGERPRINT_PROVIDER` | `disabled` | `disabled`, `simulated` o `as608` |

Umbrales, anti-rebote, prueba de vida, modo de respaldo y motor también se cambian desde el panel
(quedan guardados en la base y en la auditoría).

## Comandos útiles

Desde `backend/`:

```bash
uv run python -m app.cli check-engine          # estado del motor facial
uv run python -m app.cli reindex [--engine sface]  # regenera plantillas desde las fotos
uv run python -m app.cli calibrate             # calibración FAR/FRR
uv run python -m app.cli download-models       # vuelve a descargar modelos faltantes
uv run python -m app.cli seed-demo [--clear]   # datos de demostración
uv run python -m app.cli fingerprint-diagnose  # diagnóstico del AS608 (v2)
```

## Pruebas

```bash
scripts/test.sh          # pytest + typecheck/lint/build + prueba de humo + E2E
scripts/test.sh quick    # solo pytest y frontend
```

- **pytest** (`backend/tests`, motor `fake`): tipo automático y anti-rebote, cálculo de horas
  (medianoche, varias jornadas, incompletas), tabla multimodal con huella simulada, máquina de
  estados del kiosco (prueba de vida, cambio de identidad, tiempo agotado), exportaciones y
  endpoints. Incluye integración con los motores reales usando rostros de la imagen `t1` de
  InsightFace (se salta sola si faltan modelos).
- **Prueba de humo** (`backend/scripts/smoke_api.py`): servidor aislado, ambos motores, enrolamiento
  con rostros reales, entradas y salidas (huella simulada alta y media), exportación con horas.
- **E2E** (`frontend/e2e`, Playwright + Chromium con cámara falsa): el kiosco obtiene video; el
  panel inicia sesión, lista personas y exporta; y un flujo completo con un video de un rostro real
  (reto de vida, ENTRADA, "ya registrado"). Las capturas quedan en `frontend/e2e/screenshots/`.

## Seguridad y privacidad

- El servidor escucha **solo en 127.0.0.1** y rechaza otros `Host`.
- Las fotos y capturas solo se sirven a sesiones autenticadas del panel (cookie httpOnly,
  SameSite=Strict). El kiosco recibe su propia foto embebida en la respuesta, nunca por URL.
- Los embeddings se guardan **cifrados con Fernet** (`ENCRYPTION_KEY`). `data/` y `.env` quedan con
  permisos restrictivos (700/600). Si la clave se pierde, genera una nueva en `.env` y ejecuta
  `uv run python -m app.cli reindex` (re-crea las plantillas desde las fotos de enrolamiento).
- No se puede enrolar sin consentimiento firmado. *Eliminar datos biométricos* borra plantillas,
  fotos de enrolamiento y huella de la persona; sus marcaciones se conservan.
- Las marcaciones son inmutables: solo se anulan con motivo, y todo queda en la auditoría.

## Licencia de los modelos

Los modelos preentrenados de **InsightFace (buffalo_l) son solo para uso no comercial y de
investigación**. Para este proyecto universitario es válido. **Para uso comercial usa el motor
`sface`** (OpenCV Zoo, Apache-2.0): `FACE_ENGINE=sface` y luego
`uv run python -m app.cli reindex --engine sface`.

## Solución de problemas

**InsightFace no instala o no carga.** Este proyecto no compila el paquete `insightface`: ejecuta
los modelos buffalo_l directamente con onnxruntime, así que solo hacen falta los archivos
`models/buffalo_l/det_10g.onnx` y `w600k_r50.onnx`. Si faltan o están corruptos, el sistema arranca
con SFace y lo indica en el panel. Arreglo: `cd backend && uv run python -m app.cli download-models`
(si la descarga falla, copia esos dos archivos desde `~/.insightface/models/buffalo_l/`) y luego
`uv run python -m app.cli check-engine`.

**Cámara bloqueada o en negro.** Revisa los permisos (sección anterior). Cierra Zoom, Teams o
FaceTime si la están usando. En el kiosco usa *Reintentar* o *Cámara* para elegir otra. Abre
siempre `http://localhost:8000` (no la IP de la red: fuera de localhost el navegador bloquea la
cámara).

**Imagen de lado, de cabeza o verde (celular como cámara: DroidCam, Iriun…).** Usa *Girar imagen*
en el enrolamiento o en el botón *Cámara* del kiosco: gira la vista y también las fotos que se
envían, y queda guardado para esa cámara en ese navegador. Si la imagen es vertical, el recuadro de
enrolamiento también lo es. Gira antes de capturar: una foto de lado da una plantilla mala. Si la
imagen sale toda verde, la app del celular está conectada pero la cámara virtual del programa de la
PC está apagada (en DroidCam: *Iniciar Cámara Virtual*).

**Puerto 8000 ocupado.** `lsof -iTCP:8000 -sTCP:LISTEN` muestra el proceso; ciérralo con
`kill <PID>` o cambia `PORT` en `.env`.

**No me reconoce.** Mira el mensaje de guía (luz, distancia, de frente). Enrola de nuevo con buena
luz frontal. Revisa en *Marcaciones* la similitud real frente al umbral, y calibra.

**El sonido no suena.** Los navegadores bloquean el audio hasta la primera interacción: toca una vez
la pantalla del kiosco o el botón del parlante.

## Huella dactilar (v2): conexión del AS608

La lógica multimodal ya está implementada y probada con el proveedor `simulated`:

| Lectura de huella | Qué pasa |
|---|---|
| Puntaje alto (≥ `FINGERPRINT_HIGH_SCORE`) | Marca por huella (`HUELLA`); la foto se guarda igual para auditoría |
| Puntaje medio | Esa persona es candidata: rostro 1:1 + prueba de vida (`HUELLA+ROSTRO`) |
| Sin coincidencia o mala imagen | Rostro 1:N + prueba de vida, o código + rostro 1:1 si `FALLBACK_MODE=code_plus_face` |
| Sin huella configurada (v1) | Rostro 1:N + prueba de vida (`ROSTRO`) |

**1. Probar la lógica sin hardware.** En `.env`: `FINGERPRINT_PROVIDER=simulated`, reinicia y usa el
botón *Simular huella* del kiosco. En la ficha de cada persona, *Asignar huella simulada*.

**2. Cableado** (AS608 ↔ adaptador USB-TTL CP2102/CH340):

| AS608 | USB-TTL |
|---|---|
| VCC (rojo) | **Verifica el voltaje de tu módulo**: la mayoría es 3.3 V; algunos aceptan 5 V |
| GND (negro) | GND |
| TX (amarillo/verde) | **RX** |
| RX (blanco) | **TX** |

TX y RX van **cruzados**. Si el módulo es de 3.3 V, no lo alimentes con 5 V.

**3. Encontrar el puerto:** con el adaptador conectado, `ls /dev/tty.usb*` (p. ej.,
`/dev/tty.usbserial-0001` o `/dev/tty.wchusbserial110`). Si no aparece, instala el driver del chip
(CH340 suele necesitarlo).

**4. Configurar `.env`:**

```dotenv
FINGERPRINT_PROVIDER=as608
FINGERPRINT_PORT=/dev/tty.usbserial-0001
FINGERPRINT_BAUDRATE=57600
FINGERPRINT_HIGH_SCORE=100
FINGERPRINT_MEDIUM_SCORE=40
```

**5. Diagnóstico:** `cd backend && uv run python -m app.cli fingerprint-diagnose` lista los puertos,
abre el sensor y muestra capacidad y huellas guardadas.

**6. Enrolar huellas** (dos capturas por persona; requiere consentimiento): desde la ficha
(*Enrolar huella*) o por consola:

```bash
uv run python -m app.cli fingerprint-enroll --code U2026001
```

La plantilla se guarda en el sensor y se respalda cifrada en la base. Para restaurar las huellas en
un sensor nuevo: `uv run python -m app.cli fingerprint-restore`. Calibra `FINGERPRINT_HIGH_SCORE` y
`FINGERPRINT_MEDIUM_SCORE` con los puntajes reales que veas en *Marcaciones*.

> El proveedor `as608` está marcado como **experimental**: se escribió sin el hardware disponible.

## Decisiones respecto de la especificación

- **InsightFace sin el paquete `insightface`:** compilarlo exige un compilador C++ y falla a menudo
  en Apple Silicon y Windows. El motor `insightface` carga los mismos modelos buffalo_l (SCRFD +
  ArcFace R50) con onnxruntime y replica su pre y post-procesado (decodificación SCRFD y alineación
  `norm_crop` a 112×112). Las pruebas usan `insightface.data.get_image('t1')` si el paquete está
  instalado y, si no, la misma imagen descargada por el setup en `models/samples/t1.jpg`.
- **Estado `EN_CURSO`:** además de COMPLETA/INCOMPLETA, una ENTRADA abierta dentro del máximo se
  muestra y exporta como "EN CURSO" (no es incompleta todavía).
- **Rango de pitch amplio:** la inclinación vertical medida con 5 landmarks varía mucho según el
  motor (SCRFD ~0.9 vs. YuNet ~0.6 para el mismo rostro), así que la pose "de frente" se decide por
  el giro lateral y el pitch solo descarta casos extremos.
- **Plataforma de desarrollo:** se construyó y verificó en Windows 11 (setup, tests, prueba de humo
  y E2E). Los scripts son bash para macOS y también funcionan en Git Bash. En la Mac, ejecuta
  `scripts/setup.sh`: crea su propio entorno de Python e instala lo necesario para Apple Silicon.

## Estructura

```
backend/app/            FastAPI, servicios, motores faciales, huella, máquina de estados del kiosco
backend/tests/          pytest (motor fake + integración con motores reales)
backend/scripts/        prueba de humo y servidor para E2E
frontend/src/kiosk/     kiosco (cámara, estados, tarjeta de marcación)
frontend/src/admin/     panel de RR.HH.
frontend/e2e/           Playwright
design-system/          design system generado con ui-ux-pro-max
docs/                   SPEC.md (especificación) y DESIGN.md (dirección de diseño)
scripts/                setup.sh, start.sh, dev.sh, test.sh
data/                   (se crea) base SQLite, capturas, fotos de enrolamiento, logs, calibración
models/                 (se crea) modelos ONNX y la imagen de ejemplo
```
