#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import wave
from pathlib import Path

import cv2
import numpy as np
import yaml


def repo_path(s: str, root: Path) -> Path:
    p = Path(s)
    return p if p.is_absolute() else root / p


def read_wav_mono(path: Path):
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        data = w.readframes(w.getnframes())

    if sw == 1:
        x = (np.frombuffer(data, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sw == 2:
        x = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    elif sw == 3:
        raw = np.frombuffer(data, dtype=np.uint8).reshape(-1, 3)
        y = raw[:, 0].astype(np.int32) | (raw[:, 1].astype(np.int32) << 8) | (raw[:, 2].astype(np.int32) << 16)
        y = np.where(y & 0x800000, y | ~0xFFFFFF, y)
        x = y.astype(np.float32) / float(2**23)
    elif sw == 4:
        x = np.frombuffer(data, dtype=np.int32).astype(np.float32) / float(2**31)
    else:
        raise SystemExit(f"Unsupported wav sample width: {sw}")

    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    x = np.nan_to_num(x)
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak > 0:
        x = x / peak
    return x.astype(np.float32), sr


def rms(audio, sr, t, window=0.25):
    c = int(t * sr)
    h = max(1, int(window * sr / 2))
    a = max(0, c - h)
    b = min(len(audio), c + h)
    if b <= a:
        return 0.0
    return float(np.sqrt(np.mean(audio[a:b] ** 2)))


def make_spec(audio, sr, max_freq=8000):
    n = 1024
    hop = 256
    if len(audio) < n:
        audio = np.pad(audio, (0, n - len(audio)))
    cols = []
    for start in range(0, len(audio) - n + 1, hop):
        chunk = audio[start:start+n] * np.hanning(n)
        cols.append(np.abs(np.fft.rfft(chunk)))
    S = np.array(cols).T if cols else np.zeros((n//2+1, 1))
    freqs = np.fft.rfftfreq(n, 1.0 / sr)
    S = S[freqs <= max_freq, :]
    S = 20 * np.log10(S + 1e-6)
    S = np.clip(S, -90, -10)
    img = ((S + 90) / 80 * 255).astype(np.uint8)
    return cv2.applyColorMap(img, cv2.COLORMAP_VIRIDIS)


def draw_box(img, box, label, color=(50, 255, 80)):
    x1, y1, x2, y2 = box
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 3)
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)
    cv2.rectangle(img, (x1, max(0, y1 - th - 12)), (min(img.shape[1]-1, x1 + tw + 10), y1), color, -1)
    cv2.putText(img, label, (x1 + 5, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (20, 20, 20), 2)


def degrade(frame):
    blur = cv2.GaussianBlur(frame, (17, 17), 0)
    dark = cv2.convertScaleAbs(blur, alpha=0.58, beta=-35)
    haze = np.full_like(dark, (190, 190, 190))
    return cv2.addWeighted(dark, 0.88, haze, 0.12, 0)


def parse_window(s):
    if not s:
        return None
    a, b = [float(x.strip()) for x in s.split(",", 1)]
    return min(a, b), max(a, b)


def run(cmd):
    print("+", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--output-dir", default="demo/video")
    ap.add_argument("--readme-assets-dir", default="assets/readme")
    ap.add_argument("--duration-sec", type=float, default=7.0)
    ap.add_argument("--start-sec", type=float, default=0.0)
    ap.add_argument("--output-fps", type=float, default=10.0)
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--panel-height", type=int, default=260)
    ap.add_argument("--degrade-window", default="")
    ap.add_argument("--make-gif", action="store_true")
    ap.add_argument("--gif-width", type=int, default=860)
    ap.add_argument("--gif-fps", type=int, default=8)
    args = ap.parse_args()

    root = Path.cwd()
    manifest = yaml.safe_load(repo_path(args.manifest, root).read_text(encoding="utf-8"))
    sample_id = str(manifest.get("sample_id", "demo_sample"))
    video = repo_path(manifest["video"]["path"], root)
    audio_path = repo_path(manifest["audio"]["path"], root)
    model_path = repo_path(args.model, root)

    from ultralytics import YOLO
    model = YOLO(str(model_path))

    audio, sr = read_wav_mono(audio_path)
    spec = make_spec(audio, sr)
    activity_probe = [rms(audio, sr, t) for t in np.linspace(0, min(args.duration_sec, len(audio)/sr), 80)]
    threshold = float(np.percentile(activity_probe, 35)) if activity_probe else 0.002

    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"Could not open {video}")
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    source_duration = total / src_fps if total else args.duration_sec
    duration = min(args.duration_sec, max(0.1, source_duration - args.start_sec))

    out_dir = repo_path(args.output_dir, root)
    assets_dir = repo_path(args.readme_assets_dir, root)
    out_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    video_h = int(args.width * 9 / 16)
    out_h = video_h + args.panel_height
    silent = out_dir / "multimodal_replay_demo_silent.mp4"
    mp4 = out_dir / "multimodal_replay_demo.mp4"
    gif = assets_dir / "multimodal_replay_demo.gif"
    preview = assets_dir / "multimodal_replay_demo_preview.jpg"
    panel_png = assets_dir / "multimodal_fusion_panel.png"

    writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*"mp4v"), args.output_fps, (args.width, out_h))
    degrade_win = parse_window(args.degrade_window)

    n = int(duration * args.output_fps)
    wrote = 0
    last_box = None
    last_t = -999.0
    last_conf = 0.0

    for i in range(n):
        t = args.start_sec + i / args.output_fps
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * src_fps))
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.resize(frame, (args.width, video_h))
        display = frame.copy()

        degraded = degrade_win and degrade_win[0] <= (t - args.start_sec) <= degrade_win[1]
        if degraded:
            display = degrade(display)

        result = model.predict(display, imgsz=args.imgsz, conf=args.conf, device=args.device, verbose=False)[0]
        best = None
        if result.boxes is not None and len(result.boxes) > 0:
            for xyxy, cf in zip(result.boxes.xyxy.cpu().numpy(), result.boxes.conf.cpu().numpy()):
                x1, y1, x2, y2 = [int(round(v)) for v in xyxy]
                x1, x2 = max(0, x1), min(args.width - 1, x2)
                y1, y2 = max(0, y1), min(video_h - 1, y2)
                area = max(1, x2-x1) * max(1, y2-y1)
                score = float(cf) * math.sqrt(area)
                if best is None or score > best[0]:
                    best = (score, (x1, y1, x2, y2), float(cf))

        act = rms(audio, sr, t)
        acoustic_active = act >= threshold
        status = "visual_track_with_acoustic_context"
        vis_conf = 0.0

        if best is not None:
            _, box, vis_conf = best
            last_box = box
            last_t = t
            last_conf = vis_conf
            draw_box(display, box, f"Track 01 boat {vis_conf:.2f}")
        elif acoustic_active and last_box is not None and (t - last_t) < 1.2:
            status = "track_retained_with_acoustic_support"
            vis_conf = last_conf * 0.6
            draw_box(display, last_box, "Track 01 retained | acoustic support", (0, 210, 255))
        else:
            status = "visual_searching"

        if degraded:
            cv2.rectangle(display, (0, 0), (args.width, 40), (25, 25, 25), -1)
            cv2.putText(display, "visual degradation: blur / low contrast", (14, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255,255,255), 2)

        panel = np.zeros((args.panel_height, args.width, 3), dtype=np.uint8)
        panel[:, :] = (22, 22, 22)
        margin = 18
        spec_h = int(args.panel_height * 0.52)
        spec_w = args.width - 2 * margin
        spec_img = cv2.flip(spec, 0)
        spec_img = cv2.resize(spec_img, (spec_w, spec_h))
        panel[margin:margin+spec_h, margin:margin+spec_w] = spec_img
        cursor_x = margin + int(np.clip((t-args.start_sec) / max(0.001, duration), 0, 1) * spec_w)
        cv2.line(panel, (cursor_x, margin), (cursor_x, margin + spec_h), (255,255,255), 2)

        wave_y = margin + spec_h + 42
        wave_h = args.panel_height - wave_y - 16
        cv2.rectangle(panel, (margin, wave_y), (margin+spec_w, wave_y+wave_h), (35,35,35), -1)
        segment = audio[:min(len(audio), int(duration * sr))]
        if len(segment) > 0:
            xs = np.linspace(0, len(segment)-1, spec_w).astype(int)
            vals = segment[xs]
            mid = wave_y + wave_h//2
            amp = int(wave_h * 0.42)
            pts = np.array([[margin+i2, int(mid - vals[i2]*amp)] for i2 in range(spec_w)], dtype=np.int32)
            cv2.polylines(panel, [pts], False, (190, 220, 255), 1)
        cv2.line(panel, (cursor_x, wave_y), (cursor_x, wave_y+wave_h), (255,255,255), 2)

        active_text = "active" if acoustic_active else "low"
        color = (70, 255, 110) if acoustic_active else (0, 170, 255)
        lines = [
            f"sample: {sample_id}",
            f"visual confidence: {vis_conf:.2f}",
            f"acoustic support: {active_text} | score={act:.4f} threshold={threshold:.4f}",
            f"fusion status: {status}",
        ]
        x_text = max(430, int(args.width * 0.53))
        y_text = 36
        for line in lines:
            c = color if "acoustic support" in line else (245,245,245)
            cv2.putText(panel, line, (x_text, y_text), cv2.FONT_HERSHEY_SIMPLEX, 0.62, c, 2)
            y_text += 30

        canvas = np.vstack([display, panel])
        writer.write(canvas)
        if i == max(1, n//2):
            cv2.imwrite(str(preview), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
            cv2.imwrite(str(panel_png), panel, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])
        wrote += 1

    writer.release()
    cap.release()
    if wrote == 0:
        raise SystemExit("No frames rendered")

    if shutil.which("ffmpeg"):
        run(["ffmpeg", "-y", "-i", str(silent), "-ss", str(args.start_sec), "-t", str(duration), "-i", str(audio_path), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(mp4)])
        if args.make_gif:
            palette = out_dir / "palette.png"
            run(["ffmpeg", "-y", "-i", str(mp4), "-vf", f"fps={args.gif_fps},scale={args.gif_width}:-1:flags=lanczos,palettegen", str(palette)])
            run(["ffmpeg", "-y", "-i", str(mp4), "-i", str(palette), "-filter_complex", f"fps={args.gif_fps},scale={args.gif_width}:-1:flags=lanczos[x];[x][1:v]paletteuse", str(gif)])
    else:
        print("ffmpeg missing: wrote silent mp4 only")
        mp4 = silent

    print("wrote:")
    print(silent)
    print(mp4)
    print(preview)
    print(panel_png)
    if args.make_gif:
        print(gif)


if __name__ == "__main__":
    main()
