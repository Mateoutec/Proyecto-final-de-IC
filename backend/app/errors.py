"""Errores de la aplicación con mensajes en español."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("app.errors")


class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str | None = None, **extra: Any):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.extra = extra


class NotFound(AppError):
    def __init__(self, message: str = "Recurso no encontrado"):
        super().__init__(message, status_code=404, code="not_found")


_HTTP_MESSAGES = {
    401: "Debes iniciar sesión en el panel",
    403: "No tienes permiso para esta acción",
    404: "Recurso no encontrado",
    405: "Método no permitido",
    413: "El archivo es demasiado grande",
}

_VALIDATION_MESSAGES = {
    "missing": "es obligatorio",
    "string_too_short": "es demasiado corto",
    "string_too_long": "es demasiado largo",
    "int_parsing": "debe ser un número entero",
    "float_parsing": "debe ser un número",
    "bool_parsing": "debe ser verdadero o falso",
    "date_from_datetime_parsing": "debe ser una fecha válida (AAAA-MM-DD)",
    "date_parsing": "debe ser una fecha válida (AAAA-MM-DD)",
    "datetime_parsing": "debe ser una fecha y hora válidas",
    "datetime_from_date_parsing": "debe ser una fecha y hora válidas",
    "literal_error": "tiene un valor no permitido",
    "greater_than_equal": "es menor que el mínimo permitido",
    "less_than_equal": "supera el máximo permitido",
    "value_error": "tiene un valor inválido",
    "json_invalid": "no es un JSON válido",
}


def _describe_validation(exc: RequestValidationError) -> str:
    parts = []
    for err in exc.errors()[:4]:
        loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
        field = ".".join(loc) or "solicitud"
        msg = _VALIDATION_MESSAGES.get(err.get("type", ""), err.get("msg", "es inválido"))
        if err.get("type") == "value_error" and err.get("ctx", {}).get("error"):
            msg = str(err["ctx"]["error"])
        parts.append(f"'{field}' {msg}")
    return "Datos inválidos: " + "; ".join(parts)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError):
        body = {"detail": exc.message, "code": exc.code, **exc.extra}
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": _describe_validation(exc), "code": "validation"})

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, str) and exc.detail not in ("Not Found", "Method Not Allowed") else None
        message = detail or _HTTP_MESSAGES.get(exc.status_code, "Error en la solicitud")
        return JSONResponse(status_code=exc.status_code, content={"detail": message, "code": f"http_{exc.status_code}"})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        log.exception("Error no controlado en %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Error interno del servidor. Revisa data/logs/app.log.", "code": "internal"},
        )
