from __future__ import annotations

import os
import platform
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


def _ram_gb() -> float:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return round((pages * page_size) / (1024 ** 3), 2)
    except Exception:
        return 0.0


def _cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return platform.processor()


def system_info() -> Dict[str, object]:
    gpu = _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    return {
        "os": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu": _cpu_model(),
        "cpu_count": os.cpu_count() or 0,
        "ram_gb": _ram_gb(),
        "gpu": gpu,
    }
