#!/usr/bin/env python3
import argparse
import csv
import hashlib
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional


RUN_SUBDIRS = [
    "config",
    "bags",
    "metrics",
    "predictions",
    "screenshots",
    "models",
    "reports",
]


INDEX_FIELDS = [
    "run_id",
    "run_name",
    "created_utc",
    "git_commit",
    "git_branch",
    "run_dir",
    "source_reports",
    "source_model",
    "files_copied",
    "bytes_copied",
]


def run_cmd(cmd: List[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def git_commit() -> str:
    return run_cmd(["git", "rev-parse", "HEAD"])


def git_branch() -> str:
    return run_cmd(["git", "branch", "--show-current"])


def safe_name(value: str) -> str:
    cleaned = []
    for ch in value.strip().lower():
        if ch.isalnum():
            cleaned.append(ch)
        elif ch in {"-", "_", ".", " "}:
            cleaned.append("_")
    result = "".join(cleaned).strip("_")
    return result or "run"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except Exception:
        return 0


def copy_file(src: Path, dst: Path) -> Optional[Dict[str, object]]:
    if not src.exists() or not src.is_file():
        return None

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

    return {
        "source": str(src),
        "destination": str(dst),
        "bytes": file_size(dst),
        "sha256": sha256_file(dst),
    }


def copy_tree_files(src_dir: Path, dst_dir: Path) -> List[Dict[str, object]]:
    copied: List[Dict[str, object]] = []

    if not src_dir.exists():
        return copied

    if src_dir.is_file():
        item = copy_file(src_dir, dst_dir / src_dir.name)
        if item:
            copied.append(item)
        return copied

    for src in sorted(src_dir.rglob("*")):
        if not src.is_file():
            continue

        rel = src.relative_to(src_dir)
        item = copy_file(src, dst_dir / rel)
        if item:
            copied.append(item)

    return copied


def write_yaml(path: Path, data: Dict[str, object]) -> None:
    def scalar(value):
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        s = str(value).replace('"', '\\"')
        return f'"{s}"'

    def emit(obj, indent=0):
        lines = []
        prefix = " " * indent

        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, (dict, list)):
                    lines.append(f"{prefix}{key}:")
                    lines.extend(emit(value, indent + 2))
                else:
                    lines.append(f"{prefix}{key}: {scalar(value)}")
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, (dict, list)):
                    lines.append(f"{prefix}-")
                    lines.extend(emit(item, indent + 2))
                else:
                    lines.append(f"{prefix}- {scalar(item)}")
        else:
            lines.append(f"{prefix}{scalar(obj)}")

        return lines

    path.write_text("\n".join(emit(data)) + "\n", encoding="utf-8")


def append_index(index_path: Path, row: Dict[str, object]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    exists = index_path.exists()

    with index_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS)

        if not exists:
            writer.writeheader()

        writer.writerow({key: row.get(key, "") for key in INDEX_FIELDS})


def create_run_bundle(args) -> Path:
    created_utc = datetime.now(timezone.utc).isoformat()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = safe_name(args.run_name)
    run_id = f"run_{stamp}_{run_name}"

    output_root = Path(args.output)
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    for subdir in RUN_SUBDIRS:
        (run_dir / subdir).mkdir(parents=True, exist_ok=True)

    copied: List[Dict[str, object]] = []

    for config_path in args.config or []:
        src = Path(config_path)
        item = copy_file(src, run_dir / "config" / src.name)
        if item:
            copied.append(item)

    if args.source_reports:
        copied.extend(copy_tree_files(Path(args.source_reports), run_dir / "reports"))

    if args.source_metrics:
        copied.extend(copy_tree_files(Path(args.source_metrics), run_dir / "metrics"))

    if args.source_predictions:
        copied.extend(copy_tree_files(Path(args.source_predictions), run_dir / "predictions"))

    if args.source_bag:
        copied.extend(copy_tree_files(Path(args.source_bag), run_dir / "bags"))

    if args.source_screenshots:
        copied.extend(copy_tree_files(Path(args.source_screenshots), run_dir / "screenshots"))

    if args.source_model:
        src_model = Path(args.source_model)
        item = copy_file(src_model, run_dir / "models" / src_model.name)
        if item:
            copied.append(item)

    total_bytes = sum(int(item.get("bytes", 0)) for item in copied)

    manifest = {
        "run_manifest": {
            "schema_version": "1.0",
            "run_id": run_id,
            "run_name": args.run_name,
            "created_utc": created_utc,
            "git_commit": git_commit(),
            "git_branch": git_branch(),
            "run_dir": str(run_dir),
            "source_reports": args.source_reports or "",
            "source_metrics": args.source_metrics or "",
            "source_predictions": args.source_predictions or "",
            "source_bag": args.source_bag or "",
            "source_screenshots": args.source_screenshots or "",
            "source_model": args.source_model or "",
            "notes": args.notes or "",
            "files_copied": len(copied),
            "bytes_copied": total_bytes,
            "copied_files": copied,
        }
    }

    write_yaml(run_dir / "run_manifest.yaml", manifest)

    index_path = output_root.parent / "index.csv"
    append_index(
        index_path,
        {
            "run_id": run_id,
            "run_name": args.run_name,
            "created_utc": created_utc,
            "git_commit": git_commit(),
            "git_branch": git_branch(),
            "run_dir": str(run_dir),
            "source_reports": args.source_reports or "",
            "source_model": args.source_model or "",
            "files_copied": len(copied),
            "bytes_copied": total_bytes,
        },
    )

    return run_dir


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create a local run artifact bundle with manifest and index entry."
    )
    parser.add_argument("--run-name", required=True, help="Human-readable run name.")
    parser.add_argument("--output", default="artifacts/runs", help="Output runs directory.")

    parser.add_argument("--source-reports", default="", help="Report folder or file to copy.")
    parser.add_argument("--source-metrics", default="", help="Metrics folder or file to copy.")
    parser.add_argument("--source-predictions", default="", help="Predictions folder or file to copy.")
    parser.add_argument("--source-bag", default="", help="ROS bag folder or file to copy.")
    parser.add_argument("--source-screenshots", default="", help="Screenshots folder or file to copy.")
    parser.add_argument("--source-model", default="", help="Model file to copy.")

    parser.add_argument(
        "--config",
        action="append",
        default=[],
        help="Config file to include. Can be passed multiple times.",
    )
    parser.add_argument("--notes", default="", help="Optional run notes.")

    return parser.parse_args()


def main():
    args = parse_args()
    run_dir = create_run_bundle(args)

    print(f"created {run_dir}")
    print(f"manifest {run_dir / 'run_manifest.yaml'}")
    print(f"index {run_dir.parent.parent / 'index.csv'}")


if __name__ == "__main__":
    main()
