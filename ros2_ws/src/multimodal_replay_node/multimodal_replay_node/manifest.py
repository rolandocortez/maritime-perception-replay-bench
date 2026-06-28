from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PairedReplayManifest:
    path: Path
    sample_id: str
    dataset: str
    license_review_required: bool
    video_path: Path
    audio_path: Path
    video_start_sec: float
    video_end_sec: float
    audio_start_sec: float
    audio_end_sec: float
    audio_to_video_offset_sec: float
    video_fps: float | None
    vessel_type: str
    vessel_speed_mps: float | None
    vessel_length_m: float | None
    raw: dict[str, Any]


def _resolve_media_path(value: str, manifest_path: Path) -> Path:
    p = Path(value).expanduser()
    if p.is_absolute():
        return p

    cwd_candidate = Path.cwd() / p
    if cwd_candidate.exists():
        return cwd_candidate

    return manifest_path.parent / p


def load_manifest(path: str | Path) -> PairedReplayManifest:
    manifest_path = Path(path).expanduser()
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest not found: {manifest_path}")

    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}

    video = data.get("video") or {}
    audio = data.get("audio") or {}
    sync = data.get("sync") or {}
    vessel = data.get("vessel") or {}

    video_path = _resolve_media_path(video["path"], manifest_path)
    audio_path = _resolve_media_path(audio["path"], manifest_path)

    if not video_path.exists():
        raise FileNotFoundError(f"video path not found: {video_path}")
    if not audio_path.exists():
        raise FileNotFoundError(f"audio path not found: {audio_path}")

    return PairedReplayManifest(
        path=manifest_path,
        sample_id=str(data.get("sample_id", manifest_path.parent.name)),
        dataset=str(data.get("dataset", "unknown")),
        license_review_required=bool(data.get("license_review_required", True)),
        video_path=video_path,
        audio_path=audio_path,
        video_start_sec=float(video.get("start_sec", 0.0) or 0.0),
        video_end_sec=float(video.get("end_sec", 0.0) or 0.0),
        audio_start_sec=float(audio.get("start_sec", 0.0) or 0.0),
        audio_end_sec=float(audio.get("end_sec", 0.0) or 0.0),
        audio_to_video_offset_sec=float(sync.get("audio_to_video_offset_sec", 0.0) or 0.0),
        video_fps=float(video["fps"]) if video.get("fps") else None,
        vessel_type=str(vessel.get("type", "unknown")),
        vessel_speed_mps=vessel.get("speed_mps"),
        vessel_length_m=vessel.get("length_m"),
        raw=data,
    )
