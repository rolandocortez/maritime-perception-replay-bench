from __future__ import annotations

import subprocess
from typing import Dict


def _run(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(
            cmd,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return ""


def git_info() -> Dict[str, object]:
    status = _run(["git", "status", "--short"])
    return {
        "commit": _run(["git", "rev-parse", "HEAD"]),
        "short_commit": _run(["git", "rev-parse", "--short", "HEAD"]),
        "branch": _run(["git", "branch", "--show-current"]),
        "dirty": bool(status),
        "status_short": status,
        "remote": _run(["git", "remote", "get-url", "origin"]),
    }
