from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import yaml

from .git_info import git_info
from .system_info import system_info


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_run_id(run_name: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean = "".join(ch.lower() if ch.isalnum() else "_" for ch in run_name).strip("_")
    return f"run_{stamp}_{clean or 'run'}"


def rel_or_empty(path: str) -> str:
    if not path:
        return ""
    return str(Path(path))


def build_manifest(args: argparse.Namespace) -> Dict[str, Any]:
    run_id = args.run_id or default_run_id(args.run_name)

    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "run_name": args.run_name,
        "created_utc": now_utc(),
        "project_version": args.project_version,
        "git": git_info(),
        "scenario": {
            "name": args.scenario_name,
            "video_path": rel_or_empty(args.video_path),
            "fault_profile": args.fault_profile,
            "notes": args.scenario_notes,
        },
        "model": {
            "name": args.model_name,
            "runtime": args.model_runtime,
            "artifact_path": rel_or_empty(args.model_artifact_path),
        },
        "ros": {
            "distro": args.ros_distro or os.environ.get("ROS_DISTRO", ""),
            "use_sim_time": args.use_sim_time,
            "launch_file": args.launch_file,
        },
        "artifacts": {
            "run_dir": rel_or_empty(args.artifact_run_dir),
            "bag": rel_or_empty(args.bag),
            "metrics": rel_or_empty(args.metrics),
            "predictions": rel_or_empty(args.predictions),
            "screenshots": rel_or_empty(args.screenshots),
            "report": rel_or_empty(args.report),
            "model_copy": rel_or_empty(args.model_copy),
            "minio_upload_manifest": rel_or_empty(args.minio_upload_manifest),
        },
        "system": system_info(),
        "notes": args.notes,
    }


def write_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def load_yaml(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def basic_validate(manifest: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    required_top = [
        "schema_version",
        "run_id",
        "created_utc",
        "git",
        "scenario",
        "model",
        "ros",
        "artifacts",
        "system",
    ]

    for key in required_top:
        if key not in manifest:
            errors.append(f"missing top-level key: {key}")

    nested_required = {
        "git": ["commit", "branch", "dirty"],
        "scenario": ["name", "video_path", "fault_profile"],
        "model": ["name", "runtime", "artifact_path"],
        "ros": ["distro", "use_sim_time", "launch_file"],
        "artifacts": ["bag", "metrics", "predictions", "screenshots", "report"],
        "system": ["os", "cpu", "ram_gb"],
    }

    for parent, keys in nested_required.items():
        value = manifest.get(parent)
        if not isinstance(value, dict):
            errors.append(f"{parent} must be an object")
            continue

        for key in keys:
            if key not in value:
                errors.append(f"missing key: {parent}.{key}")

    return errors


def validate_with_optional_jsonschema(manifest_path: Path, schema_path: Path) -> List[str]:
    manifest = load_yaml(manifest_path)

    try:
        import jsonschema
    except ModuleNotFoundError:
        return basic_validate(manifest)

    schema = load_json(schema_path)
    try:
        jsonschema.validate(instance=manifest, schema=schema)
    except jsonschema.ValidationError as exc:
        return [str(exc)]

    return []


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a standardized run manifest.")

    parser.add_argument("--output", required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--project-version", default="v0.4")

    parser.add_argument("--scenario-name", default="")
    parser.add_argument("--video-path", default="")
    parser.add_argument("--fault-profile", default="")
    parser.add_argument("--scenario-notes", default="")

    parser.add_argument("--model-name", default="")
    parser.add_argument("--model-runtime", default="")
    parser.add_argument("--model-artifact-path", default="")

    parser.add_argument("--ros-distro", default="")
    parser.add_argument("--use-sim-time", action="store_true")
    parser.add_argument("--launch-file", default="")

    parser.add_argument("--artifact-run-dir", default="")
    parser.add_argument("--bag", default="")
    parser.add_argument("--metrics", default="")
    parser.add_argument("--predictions", default="")
    parser.add_argument("--screenshots", default="")
    parser.add_argument("--report", default="")
    parser.add_argument("--model-copy", default="")
    parser.add_argument("--minio-upload-manifest", default="")

    parser.add_argument("--notes", default="")

    return parser


def validate_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a standardized run manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--schema", default="schemas/run_manifest.schema.json")
    return parser


def main_create() -> None:
    parser = create_parser()
    args = parser.parse_args()

    manifest = build_manifest(args)
    output = Path(args.output)
    write_manifest(output, manifest)

    print(f"wrote {output}")
    print(f"run_id={manifest['run_id']}")
    print(f"git_commit={manifest['git'].get('short_commit', '')}")
    print(f"dirty={manifest['git'].get('dirty', False)}")


def main_validate() -> None:
    parser = validate_parser()
    args = parser.parse_args()

    errors = validate_with_optional_jsonschema(
        manifest_path=Path(args.manifest),
        schema_path=Path(args.schema),
    )

    if errors:
        print("manifest validation failed")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print(f"{args.manifest}: ok")


if __name__ == "__main__":
    main_create()
