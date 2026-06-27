#!/usr/bin/env python3
import argparse
import hashlib
import json
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List


def require_boto3():
    try:
        import boto3
        from botocore.exceptions import ClientError
        return boto3, ClientError
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing optional dependency: boto3\n"
            "Install it in your venv with:\n"
            "  python -m pip install boto3\n"
        ) from exc


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def iter_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            yield path


def content_type_for(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def ensure_bucket(client, bucket: str, client_error) -> None:
    try:
        client.head_bucket(Bucket=bucket)
        return
    except client_error:
        client.create_bucket(Bucket=bucket)


def make_client(args):
    boto3, client_error = require_boto3()

    access_key = (
        args.access_key
        or os.environ.get("MINIO_ROOT_USER")
        or os.environ.get("AWS_ACCESS_KEY_ID")
        or "minioadmin"
    )
    secret_key = (
        args.secret_key
        or os.environ.get("MINIO_ROOT_PASSWORD")
        or os.environ.get("AWS_SECRET_ACCESS_KEY")
        or "minioadmin"
    )

    client = boto3.client(
        "s3",
        endpoint_url=args.endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=args.region,
    )

    return client, client_error


def upload_run(args) -> Dict[str, object]:
    run_dir = Path(args.run_dir).resolve()

    if not run_dir.exists() or not run_dir.is_dir():
        raise SystemExit(f"run-dir does not exist or is not a directory: {run_dir}")

    prefix = args.prefix.strip("/")
    if not prefix:
        prefix = f"runs/{run_dir.name}"

    files = list(iter_files(run_dir))
    planned = []

    for path in files:
        rel = path.relative_to(run_dir)
        key = f"{prefix}/{rel.as_posix()}"
        planned.append(
            {
                "source": str(path),
                "relative_path": rel.as_posix(),
                "bucket": args.bucket,
                "key": key,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "content_type": content_type_for(path),
            }
        )

    upload_manifest = {
        "schema_version": "1.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_run_dir": str(run_dir),
        "bucket": args.bucket,
        "prefix": prefix,
        "endpoint_url": args.endpoint_url,
        "file_count": len(planned),
        "bytes_total": sum(int(item["bytes"]) for item in planned),
        "objects": planned,
    }

    manifest_path = run_dir / "minio_upload_manifest.json"
    if not args.dry_run:
        manifest_path.write_text(json.dumps(upload_manifest, indent=2, sort_keys=True), encoding="utf-8")
        rel = manifest_path.relative_to(run_dir)
        planned.append(
            {
                "source": str(manifest_path),
                "relative_path": rel.as_posix(),
                "bucket": args.bucket,
                "key": f"{prefix}/{rel.as_posix()}",
                "bytes": manifest_path.stat().st_size,
                "sha256": sha256_file(manifest_path),
                "content_type": "application/json",
            }
        )

    if args.dry_run:
        return upload_manifest

    client, client_error = make_client(args)

    if args.create_bucket:
        ensure_bucket(client, args.bucket, client_error)

    uploaded = []

    for item in planned:
        source_path = Path(str(item["source"]))
        client.upload_file(
            Filename=str(source_path),
            Bucket=args.bucket,
            Key=str(item["key"]),
            ExtraArgs={
                "ContentType": str(item["content_type"]),
                "Metadata": {
                    "sha256": str(item["sha256"]),
                    "relative_path": str(item["relative_path"]),
                    "source": "maritime-perception-replay-bench",
                },
            },
        )
        uploaded.append(item)

    result = {
        **upload_manifest,
        "file_count": len(uploaded),
        "bytes_total": sum(int(item["bytes"]) for item in uploaded),
        "objects": uploaded,
    }

    manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")

    if args.list_after:
        response = client.list_objects_v2(Bucket=args.bucket, Prefix=f"{prefix}/")
        listed = response.get("Contents", [])
        result["listed_after_upload"] = [
            {"key": obj.get("Key"), "size": obj.get("Size")} for obj in listed
        ]

    return result


def parse_args():
    parser = argparse.ArgumentParser(
        description="Upload a local run artifact bundle to MinIO/S3-compatible storage."
    )
    parser.add_argument("--run-dir", required=True, help="Local artifact run directory.")
    parser.add_argument("--bucket", required=True, help="Destination bucket name.")
    parser.add_argument("--prefix", default="", help="Optional object prefix. Defaults to runs/<run_dir_name>.")

    parser.add_argument("--endpoint-url", default="http://localhost:9000")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--access-key", default="")
    parser.add_argument("--secret-key", default="")

    parser.add_argument("--no-create-bucket", dest="create_bucket", action="store_false")
    parser.set_defaults(create_bucket=True)

    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-after", action="store_true")

    return parser.parse_args()


def main():
    args = parse_args()
    result = upload_run(args)

    print(f"bucket={result['bucket']}")
    print(f"prefix={result['prefix']}")
    print(f"files={result['file_count']}")
    print(f"bytes={result['bytes_total']}")

    if args.dry_run:
        print("dry_run=true")
    else:
        print("upload_complete=true")
        print(f"upload_manifest={Path(args.run_dir) / 'minio_upload_manifest.json'}")


if __name__ == "__main__":
    main()
