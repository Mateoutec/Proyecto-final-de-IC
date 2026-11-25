# Prueba del proyecto en la laptop Windows

Actualización 31/10: los dos errores de foto y concurrencia fueron corregidos y pasaron 78 pruebas de backend y 30 comprobaciones de integración. En la PC actual la aplicación está arrancada en http://localhost:8001; el panel está en http://localhost:8001/admin. Para arrancar manualmente en ese puerto, desde backend: `uv run python -m app --port 8001`.

## Equipo y preparación

Camino comprobado en este equipo: Windows x64, Python 3.11, navegador Chrome/Edge y reconocimiento en CPU. La laptop destino aún no se ha probado. Aproximadamente 32 GB de RAM es un margen razonable para la demo, no un resultado de benchmark. Confirmar si su procesador es Intel/AMD x64; Windows ARM requiere validación aparte.

Usar cámara integrada o webcam USB. Mantener buena luz frontal y cerrar aplicaciones que estén utilizando esa cámara. Completar la instalación con internet antes de la exposición; después la aplicación funciona localmente.

## Archivos a llevar

Copiar el código (`backend`, `frontend`, `scripts`, `docs`, `.env.example` y README). Conservar `backend/uv.lock` y `frontend/package-lock.json`. Excluir `.venv`, `node_modules`, `.env` y `data` para una instalación nueva sin datos personales ni credenciales compartidas.

Para evitar la descarga de modelos, copiar también:

- `models/buffalo_l/det_10g.onnx`
- `models/buffalo_l/w600k_r50.onnx`
- `models/opencv/face_detection_yunet_2023mar.onnx`
- `models/opencv/face_recognition_sface_2021dec.onnx`
- `models/samples/t1.jpg` (pruebas)

No hace falta llevar `models/buffalo_l.zip`. Los modelos extraídos suman aproximadamente 230 MB. Si se copia `frontend/dist` de la compilación validada, no hace falta Node para arrancar la aplicación; sí se necesita para compilar o modificar el frontend.

## Instalación con PowerShell

Extraer/copiar a una carpeta propia del usuario y abrir PowerShell allí. Ejecutar cada paso individualmente y detenerse si devuelve error.

1. Instalar uv si no existe:

```powershell
winget install --id=astral-sh.uv -e
```

Cerrar y abrir PowerShell para actualizar PATH. Método documentado por [Astral](https://docs.astral.sh/uv/getting-started/installation/).

2. Preparar backend desde la carpeta raíz del proyecto:

```powershell
cd backend
uv python install 3.11
uv sync --frozen
uv run python -m app.cli env-init
```

3. Si NO se copiaron los modelos:

```powershell
uv run python -m app.cli download-models
```

4. Inicializar y verificar:

```powershell
uv run python -m app.cli init-db
uv run python -m app.cli check-engine
```

Exigir `ready: true` y revisar `active`. Debe ser `insightface` o `sface`, nunca `fake`. Si falla importación de ONNX por una DLL, verificar Microsoft Visual C++ Redistributable x64: [requisito oficial de ONNX Runtime](https://onnxruntime.ai/docs/install/). Si se cambia de motor después de enrolar, ejecutar `uv run python -m app.cli reindex` con el motor deseado activo.

5. Solo si falta `frontend/dist/index.html`: instalar Node.js 22 o superior compatible con el proyecto y compilar desde backend:

```powershell
cd ..\frontend
npm.cmd ci
npm.cmd run build
cd ..\backend
```

6. Abrir `.env` en la raíz con un editor para ver la contraseña generada en `ADMIN_PASSWORD`. Configurar `TIMEZONE=America/Lima` antes de arrancar. Conservar `FINGERPRINT_PROVIDER=disabled` para la demo facial y `LIVENESS_ENABLED=true`. No compartir la clave por capturas públicas.

7. Iniciar desde backend:

```powershell
uv run python -m app
```

Mantener esa terminal abierta. Abrir `http://localhost:8000/admin` para administrar y `http://localhost:8000` para el kiosco. Para detener, Ctrl+C. Ejecutar el navegador en esa misma laptop: el servidor escucha en 127.0.0.1, no en la red del aula.

## Ensayo antes de exponer

1. Entrar al panel, crear área y dos personas con su consentimiento. Completar las cinco capturas guiadas por persona con buena luz.
2. Abrir una pestaña de kiosco para la demo. Cada persona se acerca individualmente; verificar nombre, foto, giro de cabeza y ENTRADA. El parche ya vincula la foto a la identidad reconocida; no hace falta recargar entre personas.
3. Repetir inmediatamente: debe mostrar «Ya registrado». Esperar más de 120 segundos para verificar SALIDA y horas. No confundir el anti-rebote con un fallo.
4. Probar una persona no enrolada, ausencia de giro y giro hacia el lado contrario; no deberían generar una marcación válida.
5. Exportar CSV y Excel y comprobar registros y horas.
6. Desconectar internet y repetir una marcación para comprobar la instalación local completa.

No modificar el motor ni ejecutar reindexado mientras alguien está marcando. La huella física, la robustez frente a videos y la precisión real con 20 alumnos siguen pendientes de validación. Ver `REVISION-2026-10-31.md` para el diagnóstico original y el parche.

Estos comandos se derivan del proyecto revisado; aún no se ha realizado una instalación limpia en la laptop del compañero.
