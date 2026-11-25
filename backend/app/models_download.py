"""Descarga de modelos (solo durante el setup; en ejecución no se usa internet)."""

from __future__ import annotations

import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

BUFFALO_URLS = ["https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"]
BUFFALO_FILES = ("det_10g.onnx", "w600k_r50.onnx")
OPENCV_MODELS = {
    "face_detection_yunet_2023mar.onnx": [
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
    ],
    "face_recognition_sface_2021dec.onnx": [
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "https://huggingface.co/opencv/face_recognition_sface/resolve/main/face_recognition_sface_2021dec.onnx",
    ],
}
SAMPLE_URLS = [
    "https://raw.githubusercontent.com/deepinsight/insightface/master/python-package/insightface/data/images/t1.jpg"
]
MIN_SIZES = {
    "det_10g.onnx": 10_000_000,
    "w600k_r50.onnx": 100_000_000,
    "face_detection_yunet_2023mar.onnx": 100_000,
    "face_recognition_sface_2021dec.onnx": 30_000_000,
    "t1.jpg": 50_000,
}


def _ok(path: Path) -> bool:
    return path.exists() and path.stat().st_size >= MIN_SIZES.get(path.name, 1)


def _download(urls: list[str], target: Path) -> None:
    last_error: Exception | None = None
    for url in urls:
        try:
            print(f"  descargando {url}")
            tmp = target.with_suffix(target.suffix + ".part")
            with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, "wb") as fh:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                while chunk := resp.read(1 << 20):
                    fh.write(chunk)
                    done += len(chunk)
                    if total:
                        sys.stdout.write(f"\r  {done * 100 // total:3d}% de {total // 1_000_000} MB")
                        sys.stdout.flush()
            print()
            tmp.replace(target)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"  falló: {exc}")
    raise RuntimeError(f"No se pudo descargar {target.name}: {last_error}")


def ensure_buffalo(models: Path) -> None:
    folder = models / "buffalo_l"
    folder.mkdir(parents=True, exist_ok=True)
    if all(_ok(folder / f) for f in BUFFALO_FILES):
        print("✓ buffalo_l ya está descargado")
        return
    cached = Path.home() / ".insightface" / "models" / "buffalo_l"
    if all(_ok(cached / f) for f in BUFFALO_FILES):
        for f in BUFFALO_FILES:
            shutil.copy2(cached / f, folder / f)
        print(f"✓ buffalo_l copiado desde {cached}")
        return
    print("· Descargando InsightFace buffalo_l (~280 MB, solo se usan detección y reconocimiento)")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "buffalo_l.zip"
        _download(BUFFALO_URLS, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                name = Path(member).name
                if name in BUFFALO_FILES:
                    with zf.open(member) as src, open(folder / name, "wb") as dst:
                        shutil.copyfileobj(src, dst)
    missing = [f for f in BUFFALO_FILES if not _ok(folder / f)]
    if missing:
        raise RuntimeError(f"El zip de buffalo_l no contenía {missing}")
    print("✓ buffalo_l listo")


def ensure_opencv(models: Path) -> None:
    folder = models / "opencv"
    folder.mkdir(parents=True, exist_ok=True)
    for name, urls in OPENCV_MODELS.items():
        target = folder / name
        if _ok(target):
            print(f"✓ {name} ya está descargado")
            continue
        _download(urls, target)
        print(f"✓ {name} listo")


def ensure_sample(models: Path) -> None:
    folder = models / "samples"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "t1.jpg"
    if _ok(target):
        print("✓ imagen de ejemplo t1.jpg ya está descargada")
        return
    _download(SAMPLE_URLS, target)
    print("✓ imagen de ejemplo t1.jpg lista")


def ensure_models(models: Path) -> list[str]:
    errors = []
    for step in (ensure_buffalo, ensure_opencv, ensure_sample):
        try:
            step(models)
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            print(f"✗ {exc}")
    return errors
