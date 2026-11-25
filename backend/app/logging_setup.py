"""Logs rotativos en data/logs/."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_configured_dir: Path | None = None


def setup_logging(log_dir: Path, level: str = "INFO") -> None:
    global _configured_dir
    if _configured_dir == log_dir:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        if getattr(handler, "_asistencia", False):
            root.removeHandler(handler)
    file_handler = RotatingFileHandler(log_dir / "app.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    file_handler._asistencia = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(_FORMAT))
        console._asistencia = True  # type: ignore[attr-defined]
        root.addHandler(console)
    logging.getLogger("multipart").setLevel(logging.WARNING)
    logging.getLogger("matplotlib").setLevel(logging.WARNING)
    _configured_dir = log_dir
