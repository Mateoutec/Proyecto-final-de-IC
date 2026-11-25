"""`python -m app`: arranca el servidor SIEMPRE en 127.0.0.1."""

from __future__ import annotations

import argparse

import uvicorn

from app.config import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor de asistencia biométrica")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--reload", action="store_true", help="recarga automática (desarrollo)")
    args = parser.parse_args()
    settings = Settings()
    port = args.port or settings.port
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        reload=args.reload,
        reload_dirs=["app"] if args.reload else None,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
