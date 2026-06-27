#!/usr/bin/env python3
import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def resolve_path(raw: str, input_dir: Path) -> Path:
    p = Path(raw)
    if p.exists():
        return p
    q = input_dir / raw
    if q.exists():
        return q
    q = input_dir / "images" / Path(raw).name
    return q


def safe_copy(src: Path, dst: Path) -> bool:
    if not src.exists() or not src.is_file():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def write_manifest_yaml(path: Path, data: Dict[str, Any]) -> None:
    lines = [
        "task_manifest:",
        f"  created_utc: \"{data['created_utc']}\"",
        f"  source_input: \"{data['source_input']}\"",
        f"  export_type: \"{data['export_type']}\"",
        f"  image_count: {data['image_count']}",
        f"  annotation_count: {data['annotation_count']}",
        "  notes:",
        "    - \"Folder is CVAT-ready as an image review task.\"",
        "    - \"annotations.json preserves model predictions, confidence, track metadata, and source linkage.\"",
        "    - \"Images can be uploaded/imported into CVAT; annotations.json can be used as review metadata.\"",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_unstable_tracks(input_dir: Path, output_dir: Path) -> Dict[str, Any]:
    events_data = load_json(input_dir / "track_events.json", {})
    events = events_data.get("events", [])

    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    exported_images = []
    annotations = []

    for event in events:
        event_index = int(event.get("event_index", len(annotations) + 1))
        copied_for_event = []

        image_path_raw = str(event.get("image_path") or "")
        if image_path_raw:
            src = resolve_path(image_path_raw, input_dir)
            dst_name = f"event_{event_index:06d}_{src.name}"
            dst = images_dir / dst_name
            if safe_copy(src, dst):
                copied_for_event.append(dst_name)
                exported_images.append(
                    {
                        "file_name": dst_name,
                        "source_path": image_path_raw,
                        "event_index": event_index,
                        "role": "event_keyframe",
                    }
                )

        clip_dir_raw = str(event.get("clip_dir") or "")
        clip_dir = resolve_path(clip_dir_raw, input_dir) if clip_dir_raw else None

        if clip_dir and clip_dir.exists() and clip_dir.is_dir():
            for src in sorted(clip_dir.glob("*.jpg")):
                dst_name = f"event_{event_index:06d}_context_{src.name}"
                dst = images_dir / dst_name
                if safe_copy(src, dst):
                    copied_for_event.append(dst_name)
                    exported_images.append(
                        {
                            "file_name": dst_name,
                            "source_path": str(src),
                            "event_index": event_index,
                            "role": "context_frame",
                        }
                    )

        annotations.append(
            {
                "event_index": event_index,
                "event_type": event.get("event_type"),
                "track_id": event.get("track_id"),
                "related_track_id": event.get("related_track_id"),
                "frame_index": event.get("frame_index"),
                "stamp_sec": event.get("stamp_sec"),
                "severity": event.get("severity"),
                "class_name": event.get("class_name"),
                "confidence": event.get("confidence"),
                "age": event.get("age"),
                "missed_frames": event.get("missed_frames"),
                "reason": event.get("reason"),
                "bbox": event.get("bbox"),
                "source_image_path": image_path_raw,
                "source_clip_dir": clip_dir_raw,
                "exported_images": copied_for_event,
            }
        )

    return {
        "schema_version": "1.0",
        "export_type": "unstable_tracks_cvat_ready",
        "source_input": str(input_dir),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "images": exported_images,
        "annotations": annotations,
    }


def export_uncertain_frames(input_dir: Path, output_dir: Path) -> Dict[str, Any]:
    predictions = load_json(input_dir / "predictions.json", [])

    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    exported_images = []
    annotations = []

    for row in predictions:
        saved_index = int(row.get("saved_index", len(annotations) + 1))
        image_path_raw = str(row.get("image_file") or "")
        src = resolve_path(image_path_raw, input_dir)
        dst_name = f"uncertain_{saved_index:06d}_{src.name}"
        dst = images_dir / dst_name

        copied = safe_copy(src, dst)
        if copied:
            exported_images.append(
                {
                    "file_name": dst_name,
                    "source_path": image_path_raw,
                    "saved_index": saved_index,
                    "role": "uncertain_frame",
                }
            )

        annotations.append(
            {
                "saved_index": saved_index,
                "source_image_path": image_path_raw,
                "exported_image": dst_name if copied else "",
                "reasons": row.get("reasons", []),
                "metrics": row.get("metrics", {}),
                "detections": row.get("detections", []),
                "image_stamp": row.get("image_stamp", {}),
                "detection_stamp": row.get("detection_stamp", {}),
            }
        )

    return {
        "schema_version": "1.0",
        "export_type": "uncertain_frames_cvat_ready",
        "source_input": str(input_dir),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "images": exported_images,
        "annotations": annotations,
    }


def main():
    parser = argparse.ArgumentParser(description="Export mined samples to a CVAT-ready review folder.")
    parser.add_argument("--input", required=True, help="Input mined folder.")
    parser.add_argument("--output", required=True, help="Output task folder.")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if (input_dir / "track_events.json").exists():
        payload = export_unstable_tracks(input_dir, output_dir)
    elif (input_dir / "predictions.json").exists():
        payload = export_uncertain_frames(input_dir, output_dir)
    else:
        raise SystemExit(
            f"Could not detect mined format in {input_dir}. Expected track_events.json or predictions.json."
        )

    annotations_path = output_dir / "annotations.json"
    manifest_path = output_dir / "task_manifest.yaml"

    annotations_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    write_manifest_yaml(
        manifest_path,
        {
            "created_utc": payload["created_utc"],
            "source_input": payload["source_input"],
            "export_type": payload["export_type"],
            "image_count": len(payload["images"]),
            "annotation_count": len(payload["annotations"]),
        },
    )

    print(f"wrote {output_dir}")
    print(f"images={len(payload['images'])} annotations={len(payload['annotations'])}")
    print(f"annotations={annotations_path}")
    print(f"manifest={manifest_path}")


if __name__ == "__main__":
    main()
