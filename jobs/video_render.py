"""🎬 国学短视频一键成片：分镜表 → 画面 + 配音 + 字幕 + 音乐 → MP4（≤60s）

读取 data/media/reports/guoxue_<date>.json，为每镜生成 1080x1920 竖屏画面与
edge-tts 中文配音，自动按预算压缩语句，合成拼接输出 MP4 + 封面 PNG + .srt 字幕。

用法：
  python -m jobs.video_render --date 2026-09-09
      [--voice zh-CN-YunxiNeural] [--bgm 路径] [--target 56] [--out 输出目录]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import imageio_ffmpeg  # noqa: E402

from server.config import DATA_DIR  # noqa: E402

REPORT_DIR = DATA_DIR / "media" / "reports"
VIDEO_DIR = DATA_DIR / "media" / "videos"
TMP_DIR = DATA_DIR / "media" / ".tmp_render"

FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]
DEFAULT_VOICE = "zh-CN-YunxiNeural"
MIN_SEG, MAX_SEG = 2.4, 9.0
W, H = 1080, 1920


def _font(size: int):
    from PIL import ImageFont

    for f in FONT_CANDIDATES:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _load_artifact(date: str) -> dict:
    f = REPORT_DIR / f"guoxue_{date}.json"
    if not f.exists():
        raise FileNotFoundError(f"缺少结构化产物 {f}（请先运行 python -m jobs.guoxue_media --date {date}）")
    return json.loads(f.read_text(encoding="utf-8"))


def tts_segment(text: str, out: Path, voice: str) -> float:
    """生成配音 mp3，返回带停顿的实际时长（秒）。"""
    import edge_tts

    async def _go():
        await edge_tts.Communicate(text, voice, rate="-6%").save(str(out))

    asyncio.run(_go())
    r = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(out), "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r"time=(\d+):(\d+):([\d.]+)", r.stderr)
    if m:
        return max(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) + 0.35, MIN_SEG)
    return 5.0


def _wrap(text: str, limit: int = 11) -> list[str]:
    lines = []
    for raw in text.split("\n"):
        raw = raw.strip()
        while len(raw) > limit:
            lines.append(raw[:limit])
            raw = raw[limit:]
        if raw:
            lines.append(raw)
    return lines


def draw_scene(idx: int, total: int, lines: list[str], out: Path, *, cover: bool = False, title: str = ""):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), "#070b16")
    dr = ImageDraw.Draw(img)
    top, bot = (12, 18, 36), (4, 6, 13)
    for y in range(H):
        k = y / H
        dr.line([(0, y), (W, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * k) for i in range(3)))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for r in range(700, 320, -12):
        gd.ellipse((W // 2 - r, 430 - r, W // 2 + r, 430 + r), fill=(120, 190, 255, max(2, int(20 * (r - 320) / 380))))
    img.paste(glow, (0, 0), glow)
    p = 60
    for x0, y0, x1, y1 in [
        (p, p, p + 90, p + 6), (p, p, p + 6, p + 90),
        (W - p - 90, p, W - p, p + 6), (W - p - 6, p, W - p, p + 90),
        (p, H - p - 6, p + 90, H - p), (p, H - p - 90, p + 6, H - p),
        (W - p - 90, H - p - 6, W - p, H - p), (W - p - 6, H - p - 90, W - p, H - p),
    ]:
        dr.rectangle([x0, y0, x1, y1], fill=(224, 240, 255))
    f_lab = _font(34)
    dr.text((W // 2, 210), "国学经典 · 每日一悟", font=f_lab, fill=(150, 190, 255), anchor="mm")
    y = 620 if (cover or idx == 1) else 700
    if title:
        f_t = _font(62)
        for tl in _wrap(title, 14)[:3]:
            dr.text((W // 2, y), tl, font=f_t, fill=(255, 224, 176), anchor="mm")
            y += 88
        y += 66
    f_body = _font(72)
    f_sub = _font(60)
    for i, ln in enumerate(lines[:7]):
        f = f_body if (i == 0 and len(lines) > 1) else f_sub
        c = (255, 206, 120) if (i == 0 and len(lines) > 1) else (236, 243, 255)
        dr.text((W // 2, y), ln, font=f, fill=c, anchor="mm")
        y += 102
    dr.text((W // 2, H - 150), f"📜 国学经典 · {idx}/{total}", font=_font(30), fill=(110, 140, 200), anchor="mm")
    img.save(out)


def _prep_scenes(adapted: dict) -> list[dict]:
    sb = adapted.get("storyboard") or []
    if sb:
        return [
            {"label": str(s.get("t", f"第{i}镜")), "text": "".join(str(s.get("text", "")).split())}
            for i, s in enumerate(sb, 1)
            if str(s.get("text", "") or "").strip()
        ]
    parts = re.split(r"(?<=[。！？])", (adapted.get("script") or "").replace("\n", ""))
    return [{"label": f"第{i}镜", "text": "".join(p.split())} for i, p in enumerate([x for x in parts if x.strip()], 1)]


def _trim_to_sentence(text: str, keep: int) -> str:
    """从尾部向 keep 字符处回退到句末标点。"""
    head = text[:keep]
    for ch in "。！？；":
        i = head.rfind(ch)
        if i > keep // 2:
            return text[: i + 1]
    return head


def render(date: str, voice: str = DEFAULT_VOICE, bgm: str | None = None,
           target: float = 56.0, out_dir: Path | None = None) -> dict:
    artifact = _load_artifact(date)
    adapted = artifact.get("adapted", {})
    title = (adapted.get("title") or "国学经典").strip()
    scenes = _prep_scenes(adapted)
    if not scenes:
        raise ValueError("分镜内容为空，无法成片")

    out_dir = out_dir or VIDEO_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    for f in TMP_DIR.iterdir():
        if f.is_file():
            f.unlink()
    exe = imageio_ffmpeg.get_ffmpeg_exe()

    # ---- 预算内规划：配音 + 必要时压缩/删尾镜 ----
    for scene in scenes:
        scene["text"] = scene["text"][:110]
    plan: list[dict] = []
    total = 0.0
    for _ in range(18):
        if not scenes:
            break
        recs = []
        subtotal = 0.0
        for s in scenes:
            key = s["text"]
            audio = TMP_DIR / f"a{abs(hash(key)) % 99999:05d}.mp3"
            if not audio.exists():
                audio.unlink(missing_ok=True)
                dur = tts_segment(key, audio, voice)
            else:
                dur = max(min(len(key) / 4.1 + 0.4, MAX_SEG), MIN_SEG)
            dur = min(dur, MAX_SEG)
            recs.append({"scene": s, "audio": audio, "dur": dur})
            subtotal += dur
        total = subtotal
        if total <= target or len(scenes) <= 1:
            plan = recs
            break
        longest = max(scenes, key=lambda s: len(s["text"]))
        if len(longest["text"]) > 26:
            longest["text"] = _trim_to_sentence(longest["text"], len(longest["text"]) - 16)
        else:
            scenes.pop()
    if not plan:
        raise RuntimeError("成片规划失败（无可用分镜）")
    print(f"[render] 规划 {len(plan)} 镜 · 预计 {total:.1f}s（目标 ≤{target}s）")

    # ---- 逐镜画面 + 配音编码 ----
    seg_files = []
    for i, r in enumerate(plan, 1):
        seg = r["scene"]
        png = TMP_DIR / f"p{i:02d}.png"
        draw_scene(i, len(plan), _wrap(seg["text"], 11), png, title=title if i == 1 else "")
        seg_mp4 = TMP_DIR / f"s{i:02d}.mp4"
        rr = subprocess.run(
            [exe, "-y", "-loop", "1", "-i", str(png), "-i", str(r["audio"]),
             "-t", f"{r['dur']:.2f}", "-r", "25",
             "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
             "-shortest", str(seg_mp4)],
            capture_output=True, text=True,
        )
        if rr.returncode != 0:
            raise RuntimeError(f"片段 {i} 合成失败: {rr.stderr[-400:]}")
        seg_files.append(str(seg_mp4))

    list_file = TMP_DIR / "list.txt"
    list_file.write_text("".join(f"file '{p}'\n" for p in seg_files), encoding="utf-8")
    raw = out_dir / f"guoxue_{date}_raw.mp4"
    rr = subprocess.run(
        [exe, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-ar", "44100", "-ac", "2", str(raw)],
        capture_output=True, text=True,
    )
    if rr.returncode != 0:
        raise RuntimeError(f"拼接失败: {rr.stderr[-400:]}")

    cover = out_dir / f"guoxue_{date}_cover.png"
    hook = (adapted.get("hook") or "").strip()
    draw_scene(0, len(plan), _wrap(hook or "点击播放，读懂老祖宗的智慧", 10), cover, cover=True, title=title)

    bgm_path = bgm or (DATA_DIR / "media" / "bgm.mp3")
    final = out_dir / f"guoxue_{date}.mp4"
    if Path(bgm_path).exists():
        rr = subprocess.run(
            [exe, "-y", "-i", str(raw), "-stream_loop", "-1", "-i", str(bgm_path),
             "-filter_complex",
             "[0:a]volume=1.0[vo];[1:a]volume=0.15,afade=t=out:st=2:d=3[bg];[vo][bg]amix=inputs=2:duration=first:dropout_transition=3[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", str(final)],
            capture_output=True, text=True,
        )
        if rr.returncode != 0:
            shutil.copy(raw, final)
    else:
        shutil.copy(raw, final)
    raw.unlink(missing_ok=True)

    # ---- 字幕 srt ----
    srt = out_dir / f"guoxue_{date}.srt"
    t0 = 0.0
    with srt.open("w", encoding="utf-8") as f:
        for i, r in enumerate(plan, 1):
            a, b = t0, t0 + r["dur"]

            def ts(x):
                mm = int(x // 60)
                ss = x % 60
                return f"00:{mm:02d}:{ss:06.3f}".replace(".", ",")

            f.write(f"{i}\n{ts(a)} --> {ts(b)}\n{r['scene']['text']}\n\n")
            t0 = b

    return {
        "ok": True,
        "date": date,
        "video": str(final.relative_to(DATA_DIR)),
        "cover": str(cover.relative_to(DATA_DIR)),
        "srt": str(srt.relative_to(DATA_DIR)),
        "segments": len(plan),
        "duration_s": round(t0, 2),
        "target_s": target,
        "bytes": final.stat().st_size,
    }


def main():
    ap = argparse.ArgumentParser(description="国学短视频一键成片")
    ap.add_argument("--date", default=None)
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--bgm", default=None)
    ap.add_argument("--target", type=float, default=56.0)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if not args.date:
        files = sorted(REPORT_DIR.glob("guoxue_*.json"))
        if not files:
            print("未找到 guoxue 产物，请先运行 guoxue_media")
            sys.exit(1)
        args.date = Path(files[-1]).stem.replace("guoxue_", "")
    out_dir = Path(args.out) if args.out else None
    print(json.dumps(render(args.date, voice=args.voice, bgm=args.bgm, target=args.target, out_dir=out_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
