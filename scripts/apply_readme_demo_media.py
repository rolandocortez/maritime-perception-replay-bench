#!/usr/bin/env python3
from pathlib import Path

p = Path("README.md")
text = p.read_text(encoding="utf-8")

block = """### Demo media

<p align="center">
  <img src="assets/readme/multimodal_replay_demo.gif" alt="Multimodal replay demo with visual tracking and acoustic activity" width="860">
</p>

The GIF above is rendered offline from the same local manifest, trained detector, video sample, and audio sample used by the ROS2 replay path. This keeps the public demo frame-aligned while the ROS2 graph remains available for topic-level debugging, metrics, and fault-injection experiments.


Planned full-audio demo: export `demo/video/multimodal_replay_demo.mp4`, upload it as an unlisted video, and link it here with dataset attribution.

"""

if "assets/readme/multimodal_replay_demo.gif" in text:
    print("README already has demo media block")
    raise SystemExit(0)

marker = "### Why this is not just a Python detection script"
if marker in text:
    text = text.replace(marker, block + "\n" + marker, 1)
else:
    text += "\n\n" + block

p.write_text(text, encoding="utf-8")
print("README demo media block inserted")
