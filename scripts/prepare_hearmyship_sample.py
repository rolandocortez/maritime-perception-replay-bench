#!/usr/bin/env python3
"""Prepare one local HearMyShip paired audio/video sample.

This script intentionally does not download or commit the dataset.
It selects one local video/audio pair, places symlinks or copies under
data/multimodal/hearmyship/prepared/<sample_id>/, and writes a manifest.yaml.

Typical usage:

  python scripts/prepare_hearmyship_sample.py \
    --dataset-root /path/to/HearMyShip \
    --sample-id demo_001 \
    --video /path/to/video.mp4 \
    --audio /path/to/audio.wav \
    --output data/multimodal/hearmyship/prepared/demo_001 \
    --force

If --video/--audio are omitted, the script searches --dataset-root for
files whose path contains --sample-id.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import wave
from typing import Any

import yaml


VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv"}
AUDIO_EXTS = {".wav", ".flac", ".aif", ".aiff"}
METADATA_EXTS = {".yaml", ".yml", ".json", ".csv", ".txt"}


CITATION = (
    "Shipton, M., Obradović, J., Ferreira, F. et al. "
    "A Database of Underwater Radiated Noise from Small Vessels in the Coastal Area. "
    "Scientific Data 12, 289 (2025)."
)


def repo_root() -> Path:
    try:
        raw = subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
        return Path(raw)
    except Exception:
        return Path.cwd()


def to_repo_rel(path: Path, root: Path) -> str:
    """Return a repo-relative path without dereferencing symlinks.

    This is intentional: prepared samples may store video/audio as symlinks
    under data/multimodal/hearmyship/prepared/<sample_id>/, and the manifest
    should point to that prepared path rather than the raw download target.
    """
    try:
        if path.is_absolute():
            return str(path.relative_to(root))
        return str(path)
    except Exception:
        return str(path)


def find_candidates(root: Path, sample_id: str, exts: set[str]) -> list[Path]:
    if not root.exists():
        return []
    sample_key = sample_id.lower()
    candidates: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in exts:
            continue
        haystack = str(p).lower()
        if sample_key in haystack:
            candidates.append(p)
    return sorted(candidates)


def choose_file(explicit: str | None, root: Path, sample_id: str, exts: set[str], label: str) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.exists():
            raise SystemExit(f"{label} file not found: {p}")
        return p

    matches = find_candidates(root, sample_id, exts)
    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        print(f"Found multiple {label} candidates for sample_id={sample_id!r}:", file=sys.stderr)
        for item in matches[:30]:
            print(f"  {item}", file=sys.stderr)
        raise SystemExit(f"Pass --{label} explicitly to disambiguate.")

    examples = sorted([p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in exts])[:30]
    print(f"No {label} file found containing sample_id={sample_id!r}.", file=sys.stderr)
    if examples:
        print(f"Some {label} files found under dataset root:", file=sys.stderr)
        for item in examples:
            print(f"  {item}", file=sys.stderr)
    raise SystemExit(f"Pass --{label} explicitly.")


def safe_link_or_copy(src: Path, dst: Path, *, copy_file: bool, force: bool) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        if not force:
            raise SystemExit(f"Output already exists: {dst}. Use --force to replace.")
        if dst.is_dir() and not dst.is_symlink():
            shutil.rmtree(dst)
        else:
            dst.unlink()

    if copy_file:
        shutil.copy2(src, dst)
    else:
        dst.symlink_to(src.resolve())


def ffprobe_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                "-show_format",
                str(path),
            ],
            text=True,
        )
        return json.loads(raw)
    except Exception:
        return None


def parse_rate(rate: str | None) -> float | None:
    if not rate:
        return None
    if "/" in rate:
        a, b = rate.split("/", 1)
        try:
            b_float = float(b)
            if b_float == 0:
                return None
            return float(a) / b_float
        except Exception:
            return None
    try:
        return float(rate)
    except Exception:
        return None


def video_info(path: Path) -> dict[str, Any]:
    info = ffprobe_json(path)
    result: dict[str, Any] = {
        "duration_sec": None,
        "fps": None,
        "width": None,
        "height": None,
    }
    if not info:
        return result

    fmt = info.get("format") or {}
    try:
        result["duration_sec"] = float(fmt.get("duration")) if fmt.get("duration") is not None else None
    except Exception:
        pass

    streams = info.get("streams") or []
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video_stream:
        result["width"] = video_stream.get("width")
        result["height"] = video_stream.get("height")
        result["fps"] = parse_rate(video_stream.get("avg_frame_rate")) or parse_rate(video_stream.get("r_frame_rate"))

    return result


def audio_info(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "duration_sec": None,
        "sample_rate_hz": None,
        "channels": None,
    }

    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                result["sample_rate_hz"] = rate
                result["channels"] = wf.getnchannels()
                result["duration_sec"] = frames / float(rate) if rate else None
                return result
        except Exception:
            pass

    info = ffprobe_json(path)
    if not info:
        return result

    fmt = info.get("format") or {}
    try:
        result["duration_sec"] = float(fmt.get("duration")) if fmt.get("duration") is not None else None
    except Exception:
        pass

    streams = info.get("streams") or []
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if audio_stream:
        try:
            result["sample_rate_hz"] = int(audio_stream["sample_rate"])
        except Exception:
            pass
        result["channels"] = audio_stream.get("channels")

    return result


def read_metadata(path: Path | None) -> dict[str, Any]:
    if not path:
        return {}
    if not path.exists():
        raise SystemExit(f"Metadata file not found: {path}")

    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix == ".csv":
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        return {"csv_rows": rows[:10], "csv_row_count": len(rows)}
    return {"text": path.read_text(encoding="utf-8", errors="replace")[:4000]}


def maybe_metadata_candidate(root: Path, sample_id: str) -> Path | None:
    matches = find_candidates(root, sample_id, METADATA_EXTS)
    return matches[0] if matches else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare one local HearMyShip paired audio/video sample.")
    parser.add_argument("--dataset-root", required=True, help="Local root of downloaded/extracted HearMyShip data.")
    parser.add_argument("--sample-id", required=True, help="Sample identifier, e.g. demo_001 or the dataset record ID.")
    parser.add_argument("--output", required=True, help="Prepared output folder, usually data/multimodal/hearmyship/prepared/<sample_id>.")
    parser.add_argument("--video", help="Explicit local video file. Recommended if auto-search is ambiguous.")
    parser.add_argument("--audio", help="Explicit local audio file. Recommended if auto-search is ambiguous.")
    parser.add_argument("--metadata", help="Optional local metadata file.")
    parser.add_argument("--copy", action="store_true", help="Copy video/audio instead of symlinking them.")
    parser.add_argument("--force", action="store_true", help="Replace existing output files.")
    parser.add_argument("--start-sec", type=float, default=0.0)
    parser.add_argument("--end-sec", type=float, default=None)
    parser.add_argument("--audio-offset-sec", type=float, default=0.0)
    parser.add_argument("--sync-confidence", default="dataset_metadata_or_manual")
    parser.add_argument("--vessel-type", default="unknown_or_dataset_label")
    parser.add_argument("--vessel-speed-mps", type=float, default=None)
    parser.add_argument("--vessel-length-m", type=float, default=None)
    parser.add_argument("--fps", type=float, default=None, help="Override video FPS in manifest.")
    parser.add_argument("--sample-rate-hz", type=int, default=None, help="Override audio sample rate in manifest.")
    args = parser.parse_args()

    root = repo_root()
    dataset_root = Path(args.dataset_root).expanduser()
    output_dir = Path(args.output)
    if not output_dir.is_absolute():
        output_dir = root / output_dir

    video_src = choose_file(args.video, dataset_root, args.sample_id, VIDEO_EXTS, "video")
    audio_src = choose_file(args.audio, dataset_root, args.sample_id, AUDIO_EXTS, "audio")

    metadata_path = Path(args.metadata).expanduser() if args.metadata else maybe_metadata_candidate(dataset_root, args.sample_id)
    metadata = read_metadata(metadata_path) if metadata_path else {}

    video_dst = output_dir / ("video" + video_src.suffix.lower())
    audio_dst = output_dir / ("audio" + audio_src.suffix.lower())

    safe_link_or_copy(video_src, video_dst, copy_file=args.copy, force=args.force)
    safe_link_or_copy(audio_src, audio_dst, copy_file=args.copy, force=args.force)

    vinfo = video_info(video_src)
    ainfo = audio_info(audio_src)

    end_sec = args.end_sec
    if end_sec is None:
        durations = [x for x in [vinfo.get("duration_sec"), ainfo.get("duration_sec")] if x]
        end_sec = min(durations) if durations else 12.0
        end_sec = min(end_sec, 12.0)

    manifest = {
        "sample_id": args.sample_id,
        "dataset": "HearMyShip / Science Data Bank",
        "license_review_required": True,
        "video": {
            "path": to_repo_rel(video_dst, root),
            "source_path": str(video_src.resolve()),
            "start_sec": float(args.start_sec),
            "end_sec": float(end_sec),
            "fps": args.fps if args.fps is not None else vinfo.get("fps"),
            "duration_sec": vinfo.get("duration_sec"),
            "width": vinfo.get("width"),
            "height": vinfo.get("height"),
        },
        "audio": {
            "path": to_repo_rel(audio_dst, root),
            "source_path": str(audio_src.resolve()),
            "start_sec": float(args.start_sec),
            "end_sec": float(end_sec),
            "sample_rate_hz": args.sample_rate_hz if args.sample_rate_hz is not None else ainfo.get("sample_rate_hz"),
            "duration_sec": ainfo.get("duration_sec"),
            "channels": ainfo.get("channels"),
        },
        "sync": {
            "audio_to_video_offset_sec": float(args.audio_offset_sec),
            "confidence": args.sync_confidence,
            "notes": "Positive offset means audio starts after video.",
        },
        "vessel": {
            "type": args.vessel_type,
            "speed_mps": args.vessel_speed_mps,
            "length_m": args.vessel_length_m,
            "notes": "Filled from dataset metadata if available.",
        },
        "attribution": {
            "citation": CITATION,
            "source": "HearMyShip / Science Data Bank",
            "raw_data_rights": "remain with original authors/source",
            "redistribution_note": "Review dataset license before publishing derived GIF/MP4/WAV assets.",
        },
    }

    metadata_out = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "script": "scripts/prepare_hearmyship_sample.py",
        "sample_id": args.sample_id,
        "dataset_root": str(dataset_root.resolve()),
        "source_video": str(video_src.resolve()),
        "source_audio": str(audio_src.resolve()),
        "source_metadata": str(metadata_path.resolve()) if metadata_path else None,
        "copy_mode": "copy" if args.copy else "symlink",
        "video_info": vinfo,
        "audio_info": ainfo,
        "metadata_preview": metadata,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifest.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (output_dir / "metadata.yaml").write_text(yaml.safe_dump(metadata_out, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (output_dir / "README_LOCAL.txt").write_text(
        "Local HearMyShip prepared sample. Do not commit raw/prepared media files unless license review explicitly allows it.\\n",
        encoding="utf-8",
    )

    print(f"prepared sample: {output_dir}")
    print(f"manifest: {output_dir / 'manifest.yaml'}")
    print(f"metadata: {output_dir / 'metadata.yaml'}")
    print()
    print("Next checks:")
    print(f"  git check-ignore -v {to_repo_rel(video_dst, root)}")
    print(f"  git check-ignore -v {to_repo_rel(audio_dst, root)}")


if __name__ == "__main__":
    main()
