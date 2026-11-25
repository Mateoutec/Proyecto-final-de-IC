"""Proveedor AS608 por UART (EXPERIMENTAL: aún no probado con hardware).

Usa `adafruit-circuitpython-fingerprint` sobre `pyserial`. Conexión con adaptador
USB-TTL: TX del sensor -> RX del adaptador y RX del sensor -> TX del adaptador.
"""

from __future__ import annotations

import logging
import threading
import time

from app.errors import AppError
from app.fingerprint.base import FingerprintProvider, FingerprintResult, FingerprintStatus

log = logging.getLogger("app.fingerprint.as608")


class AS608Provider(FingerprintProvider):
    name = "as608"
    experimental = True

    def __init__(self, port: str, baudrate: int):
        self.port = port
        self.baudrate = baudrate
        self._lock = threading.Lock()
        self._finger = None
        self._uart = None
        self._error: str | None = None
        self._connect()

    def _connect(self) -> None:
        try:
            import adafruit_fingerprint
            import serial

            self._lib = adafruit_fingerprint
            self._uart = serial.Serial(self.port, baudrate=self.baudrate, timeout=1)
            self._finger = adafruit_fingerprint.Adafruit_Fingerprint(self._uart)
            if self._finger.verify_password() != adafruit_fingerprint.OK:
                raise RuntimeError("el sensor no aceptó la contraseña por defecto")
            self._error = None
            log.info("Sensor AS608 conectado en %s a %s baudios", self.port, self.baudrate)
        except ImportError:
            self._finger = None
            self._error = "Falta la librería: uv sync --extra fingerprint"
        except Exception as exc:  # noqa: BLE001
            self._finger = None
            self._error = f"No se pudo abrir el sensor en {self.port}: {exc}"
            log.warning(self._error)

    def _require(self):
        if self._finger is None:
            self._connect()
        if self._finger is None:
            raise AppError(self._error or "Sensor de huella no disponible", status_code=503, code="fingerprint_offline")
        return self._finger

    def status(self) -> dict:
        info = {
            "provider": self.name,
            "configured": True,
            "experimental": True,
            "port": self.port,
            "baudrate": self.baudrate,
        }
        if self._finger is None:
            self._connect()
        if self._finger is None:
            return {**info, "connected": False, "label": "Sensor desconectado", "detail": self._error}
        try:
            with self._lock:
                self._finger.read_sysparam()
                self._finger.count_templates()
            return {
                **info,
                "connected": True,
                "label": "AS608 conectado (experimental)",
                "detail": f"{self._finger.template_count} huellas en el sensor, capacidad {self._finger.library_size}",
                "templates": self._finger.template_count,
                "capacity": self._finger.library_size,
            }
        except Exception as exc:  # noqa: BLE001
            self._finger = None
            return {**info, "connected": False, "label": "Sensor sin respuesta", "detail": str(exc)}

    def _wait_image(self, finger, timeout_s: float) -> int:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            result = finger.get_image()
            if result == self._lib.OK:
                return result
            if result != self._lib.NOFINGER:
                return result
            time.sleep(0.1)
        return self._lib.NOFINGER

    def scan(self, timeout_s: float) -> FingerprintResult:
        finger = self._require()
        with self._lock:
            result = self._wait_image(finger, timeout_s)
            if result == self._lib.NOFINGER:
                return FingerprintResult(FingerprintStatus.NO_FINGER, detail="No se detectó un dedo")
            if result != self._lib.OK or finger.image_2_tz(1) != self._lib.OK:
                return FingerprintResult(FingerprintStatus.BAD_IMAGE, detail="Imagen de huella deficiente")
            if finger.finger_search() != self._lib.OK:
                return FingerprintResult(FingerprintStatus.NO_MATCH, score=0.0, detail="Huella sin coincidencia")
            return FingerprintResult(
                FingerprintStatus.MATCH, slot=int(finger.finger_id), score=float(finger.confidence)
            )

    def enroll(self, slot: int, timeout_s: float = 20.0) -> bytes | None:
        """Enrolamiento con dos capturas; devuelve la plantilla para respaldarla en la base."""
        finger = self._require()
        lib = self._lib
        with self._lock:
            for buffer_slot in (1, 2):
                log.info("Huella: coloca el dedo (captura %s de 2)", buffer_slot)
                if self._wait_image(finger, timeout_s) != lib.OK:
                    raise AppError("No se pudo capturar la huella a tiempo", status_code=408)
                if finger.image_2_tz(buffer_slot) != lib.OK:
                    raise AppError("Imagen de huella deficiente; vuelve a intentarlo")
                if buffer_slot == 1:
                    log.info("Huella: retira el dedo")
                    deadline = time.monotonic() + timeout_s
                    while finger.get_image() != lib.NOFINGER and time.monotonic() < deadline:
                        time.sleep(0.1)
            if finger.create_model() != lib.OK:
                raise AppError("Las dos capturas no coinciden; vuelve a intentarlo")
            if finger.store_model(slot) != lib.OK:
                raise AppError(f"No se pudo guardar la huella en la posición {slot}")
            try:
                data = finger.get_fpdata("char", 1)
                return bytes(data)
            except Exception as exc:  # noqa: BLE001
                log.warning("No se pudo descargar la plantilla para respaldo: %s", exc)
                return None

    def delete(self, slot: int) -> None:
        finger = self._require()
        with self._lock:
            finger.delete_model(slot)

    def restore(self, slot: int, template: bytes) -> None:
        finger = self._require()
        with self._lock:
            finger.send_fpdata(list(template), "char", 1)
            if finger.store_model(slot, 1) != self._lib.OK:
                raise AppError(f"No se pudo restaurar la huella en la posición {slot}")

    def close(self) -> None:
        if self._uart is not None:
            try:
                self._uart.close()
            except Exception:  # noqa: BLE001
                pass


def list_serial_ports() -> list[dict]:
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    return [{"device": p.device, "description": p.description} for p in list_ports.comports()]
