"""Calibración: distribuciones genuina/impostora, FAR/FRR por umbral, umbral sugerido."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np
from sqlalchemy import select

from app.errors import AppError
from app.models import FaceTemplate, Person
from app.services.audit import audit

if TYPE_CHECKING:
    from app.context import AppContext

TARGET_FAR = 0.001


def compute_pairs(groups: dict[int, list[np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    genuine, impostor = [], []
    ids = sorted(groups)
    for pid in ids:
        embs = groups[pid]
        for i in range(len(embs)):
            for j in range(i + 1, len(embs)):
                genuine.append(float(np.dot(embs[i], embs[j])))
    for a_idx, a in enumerate(ids):
        for b in ids[a_idx + 1 :]:
            for ea in groups[a]:
                for eb in groups[b]:
                    impostor.append(float(np.dot(ea, eb)))
    return np.array(genuine), np.array(impostor)


def far_frr_table(genuine: np.ndarray, impostor: np.ndarray) -> list[dict]:
    rows = []
    for t in np.round(np.arange(0.0, 1.0001, 0.01), 2):
        rows.append(
            {
                "threshold": float(t),
                "far": float((impostor >= t).mean()) if impostor.size else 0.0,
                "frr": float((genuine < t).mean()) if genuine.size else 0.0,
            }
        )
    return rows


def suggest_threshold(table: list[dict], genuine: np.ndarray, impostor: np.ndarray) -> dict:
    eer_row = min(table, key=lambda r: abs(r["far"] - r["frr"]))
    candidates = [r for r in table if r["far"] <= TARGET_FAR]
    best = min(candidates, key=lambda r: (r["frr"], r["threshold"])) if candidates else eer_row
    # Entre umbrales con el mismo FRR se elige el más alto: más conservador frente a impostores.
    same_frr = [r for r in candidates if r["frr"] == best["frr"]]
    if same_frr:
        lo = min(r["threshold"] for r in same_frr)
        hi = max(r["threshold"] for r in same_frr)
        mid = round((lo + hi) / 2, 2)
        best = min(table, key=lambda r: abs(r["threshold"] - mid))
    return {
        "suggested_threshold": best["threshold"],
        "suggested_far": best["far"],
        "suggested_frr": best["frr"],
        "eer": round((eer_row["far"] + eer_row["frr"]) / 2, 4),
        "eer_threshold": eer_row["threshold"],
        "target_far": TARGET_FAR,
        "max_impostor": float(impostor.max()) if impostor.size else None,
        "min_genuine": float(genuine.min()) if genuine.size else None,
    }


def run_calibration(ctx: AppContext, actor: str) -> dict:
    engine = ctx.engines.active_name
    if engine is None:
        raise AppError("No hay motor facial activo", status_code=503)
    groups: dict[int, list[np.ndarray]] = defaultdict(list)
    with ctx.session() as db:
        rows = db.execute(
            select(FaceTemplate.person_id, FaceTemplate.embedding_enc)
            .join(Person, Person.id == FaceTemplate.person_id)
            .where(FaceTemplate.engine == engine)
        ).all()
        for person_id, token in rows:
            groups[person_id].append(ctx.cipher.decrypt_embedding(token))
    multi = {pid: e for pid, e in groups.items() if len(e) >= 2}
    if len(groups) < 2 or not multi:
        raise AppError(
            "Para calibrar se necesitan al menos 2 personas enroladas y alguna con 2 o más capturas.",
            status_code=409,
            code="not_enough_data",
        )
    genuine, impostor = compute_pairs(groups)
    table = far_frr_table(genuine, impostor)
    suggestion = suggest_threshold(table, genuine, impostor)
    current = ctx.runtime.threshold_for(engine)
    current_row = min(table, key=lambda r: abs(r["threshold"] - current))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rel_dir = f"calibration/{engine}_{stamp}"
    out_dir = ctx.data_path / rel_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "far_frr.csv", "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["umbral", "FAR", "FRR"])
        for r in table:
            writer.writerow([f"{r['threshold']:.2f}", f"{r['far']:.6f}", f"{r['frr']:.6f}"])
    with open(out_dir / "similitudes.csv", "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(["tipo", "similitud"])
        writer.writerows([["genuina", f"{s:.6f}"] for s in genuine])
        writer.writerows([["impostora", f"{s:.6f}"] for s in impostor])
    _plot(out_dir / "grafico.png", genuine, impostor, table, current, suggestion["suggested_threshold"], engine)
    summary = {
        "engine": engine,
        "people": len(groups),
        "templates": sum(len(v) for v in groups.values()),
        "genuine_pairs": int(genuine.size),
        "impostor_pairs": int(impostor.size),
        "genuine_mean": round(float(genuine.mean()), 4) if genuine.size else None,
        "impostor_mean": round(float(impostor.mean()), 4) if impostor.size else None,
        "current_threshold": current,
        "current_far": current_row["far"],
        "current_frr": current_row["frr"],
        **suggestion,
        "files": {
            "csv": f"{rel_dir}/far_frr.csv",
            "scores": f"{rel_dir}/similitudes.csv",
            "chart": f"{rel_dir}/grafico.png",
        },
        "created_at": stamp,
        "note": "Pares genuinos calculados con las capturas de enrolamiento (misma sesión): FRR real puede ser mayor.",
    }
    (out_dir / "resumen.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    with ctx.session() as db:
        audit(db, actor, "calibracion", "engine", engine, suggested=suggestion["suggested_threshold"], eer=suggestion["eer"])
        db.commit()
    return summary


def latest_calibration(ctx: AppContext) -> dict | None:
    folder = ctx.data_path / "calibration"
    files = sorted(folder.glob("*/resumen.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))


def _plot(path, genuine, impostor, table, current, suggested, engine) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2), dpi=120)
    bins = np.linspace(-0.2, 1.0, 61)
    ax1.hist(impostor, bins=bins, alpha=0.75, color="#B45309", label=f"Impostores (n={impostor.size})", density=True)
    ax1.hist(genuine, bins=bins, alpha=0.75, color="#1E3A5F", label=f"Genuinos (n={genuine.size})", density=True)
    ax1.axvline(current, color="#111827", linestyle="--", linewidth=1.2, label=f"Umbral actual {current:.3f}")
    ax1.axvline(suggested, color="#059669", linewidth=1.6, label=f"Sugerido {suggested:.2f}")
    ax1.set_title(f"Distribución de similitud coseno — {engine}")
    ax1.set_xlabel("Similitud coseno")
    ax1.set_ylabel("Densidad")
    ax1.legend(fontsize=8)
    th = [r["threshold"] for r in table]
    ax2.plot(th, [r["far"] for r in table], color="#B45309", label="FAR (falsa aceptación)")
    ax2.plot(th, [r["frr"] for r in table], color="#1E3A5F", label="FRR (falso rechazo)")
    ax2.axvline(current, color="#111827", linestyle="--", linewidth=1.2)
    ax2.axvline(suggested, color="#059669", linewidth=1.6)
    ax2.set_title("FAR / FRR por umbral")
    ax2.set_xlabel("Umbral")
    ax2.set_ylabel("Tasa")
    ax2.set_ylim(-0.02, 1.02)
    ax2.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
