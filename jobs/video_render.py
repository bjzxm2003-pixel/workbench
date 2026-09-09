"""🎬 国学短视频一键成片 v2（水墨风 · 磁性男声 · 按分镜时长）

读取 data/media/reports/guoxue_<date>.json：
  - 字幕：去标点、自适应字号完整换行显示（不截断）
  - 画面：宣纸水墨风（米色底 + 远山淡墨 + 朱印 + 竖排大标题）
  - 配音：edge-tts zh-CN-YunjianNeural（磁性男声，rate +2% / pitch -4Hz）
  - 时长：每镜 = max(配音时长, 分镜窗跨度)，不限总长；语速更快、停顿更短
输出 1080x1920 竖屏 MP4 + 封面 PNG + .srt

用法：python -m jobs.video_render --date 2026-09-09
      [--voice zh-CN-YunjianNeural] [--bgm 路径] [--out 输出目录]
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

# 字体候选：楷体优先（书法感），其次宋体（古籍感）
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Kaiti.ttc",
    "/System/Library/Fonts/Supplemental/STKaiti.ttc",
    "/System/Library/Fonts/Songti.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
]
DEFAULT_VOICE = "zh-CN-YunjianNeural"  # 云健：磁性男声
RATE, PITCH = "+2%", "-4Hz"
MIN_SEG, MAX_SEG = 1.6, 16.0
W, H = 1080, 1920
PUNCT = "。，、！？；：“”‘’《》〈〉·…—～（）!?.,;:()\"'"


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
    import edge_tts

    async def _go():
        await edge_tts.Communicate(text, voice, rate=RATE, pitch=PITCH).save(str(out))

    asyncio.run(_go())
    r = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(out), "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = re.search(r"time=(\d+):(\d+):([\d.]+)", r.stderr)
    if m:
        return max(int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)), MIN_SEG)
    return 4.0


def clean_caption(text: str) -> str:
    """去掉字幕标点与空白（保留汉字/数字/字母）。"""
    return re.sub(rf"[{re.escape(PUNCT)}\s]+", "", text)


def _clean_lines(text: str, max_chars_per_line: int = 13) -> list[str]:
    t = clean_caption(text)
    if not t:
        return ["……"]
    lines = []
    while len(t) > max_chars_per_line:
        lines.append(t[:max_chars_per_line])
        t = t[max_chars_per_line:]
    if t:
        lines.append(t)
    return lines


def _planned_span(label: str) -> float | None:
    """从分镜窗 '8-15s' 解析相对秒数。"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", label or "")
    if m:
        span = float(m.group(2)) - float(m.group(1))
        if 1.0 <= span <= 14.0:
            return span
    return None


# ---------------- 水墨画帧 ----------------
def _ink_canvas():
    from PIL import Image, ImageDraw

    # 宣纸底（米白带轻微颗粒明暗）
    img = Image.new("RGB", (W, H), "#efe9dc")
    px = img.load()
    for y in range(0, H, 4):
        for x in range(0, W, 4):
            v = ((x * 31 + y * 17) % 13) - 6
            c0, c1, c2 = px[x, y]
            px[x, y] = (max(0, min(255, c0 + v)), max(0, min(255, c1 + v)), max(0, min(255, c2 + v)))
    dr = ImageDraw.Draw(img)
    # 右侧纵向淡墨 + 底部远山
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    # 墨晕山（右侧两座 + 底部一排）
    def mountains(color, alpha, pts):
        sd.polygon(pts, fill=(*color, alpha))

    mountains((70, 75, 82), 40, [(880, 800), (1050, 620), (1150, 900)])
    mountains((90, 95, 100), 55, [(700, 1050), (1000, 720), (1200, 1100)])
    mountains((40, 45, 52), 90, [(60, 1750), (520, 1320), (1050, 1750)])
    mountains((20, 22, 28), 70, [(760, 1920), (1050, 1460), (1250, 1920)])
    img.paste(shade, (0, 0), shade)
    dr = ImageDraw.Draw(img)
    return img, dr


def _fit_font(dr, text, start, max_w, max_h_lines, line_gap, per_line=13):
    """逐级缩小字号直到整段可在区域内放下，保证字幕完整。"""
    size = start
    from PIL import ImageFont

    while size > 28:
        f = _font(size)
        lines = _clean_lines(text, per_line)
        widths = [dr.textlength(l, font=f) for l in lines]
        used = sum(
            dr.textbbox((0, 0), l, font=f)[3] - dr.textbbox((0, 0), l, font=f)[1] for l in lines
        ) + line_gap * (len(lines) - 1)
        if max(widths) <= max_w and used <= max_h_lines and len(lines) <= max_h_lines // (size // 8 + 1) + 2:
            return f, lines
        size -= 6
        per_line = max(8, per_line - 1)
    return _font(30), _clean_lines(text, 8)[:6]


def draw_scene(idx: int, total: int, text: str, out: Path, *, cover: bool = False, title: str = ""):
    from PIL import ImageDraw

    img, dr = _ink_canvas()
    # 顶部竖排小标签
    lab = _font(40)
    dr.text((W - 190, 260), "国学经典", font=lab, fill=(120, 30, 30), anchor="mm")
    # 太阳/红日
    from PIL import Image

    sun = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sun)
    sd.ellipse((W - 330, 120, W - 160, 290), fill=(198, 78, 66, 130))
    img.paste(sun, (0, 0), sun)
    # 正文区
    dr = ImageDraw.Draw(img)
    center_x = W // 2 - 60  # 右侧留出竖排标签空间
    top = 560 if cover else 620
    if title and (cover or idx == 1):
        tf, tl = _fit_font(dr, clean_caption(title), 96, 760, 400, 30, 12)
        yy = top
        for l in tl:
            dr.text((center_x, yy), l, font=tf, fill=(30, 26, 20), anchor="mm")
            yy += 112
        top = yy + 90
    f, lines = _fit_font(dr, text, 92, 780, H - top - 420, 40, 13)
    yy = max(top + 40, H // 2 - (len(lines) * 150) // 2)
    for l in lines:
        dr.text((center_x, yy), l, font=f, fill=(34, 30, 24), anchor="mm")
        yy += 150
    # 朱印
    stamp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    std = ImageDraw.Draw(stamp)
    sx0, sy0 = center_x - 40, H - 330
    std.rectangle([sx0, sy0, sx0 + 200, sy0 + 200], outline=(196, 60, 50, 255), width=10)
    std.text((sx0 + 100, sy0 + 100), "悟", font=_font(130), fill=(196, 60, 50, 235), anchor="mm")
    img.paste(stamp, (0, 0), stamp)
    # 页码
    dr.text((W - 190, H - 240), f"{idx:02d}/{total:02d}", font=_font(44), fill=(120, 60, 50), anchor="mm")
    img.save(out)


# ---------------- 主流程 ----------------
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


def render(date: str, voice: str = DEFAULT_VOICE, bgm: str | None = None,
           out_dir: Path | None = None) -> dict:
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

    plan = []
    for i, sc in enumerate(scenes, 1):
        text = clean_caption(sc["text"])[:150]
        if not text:
            continue
        audio = TMP_DIR / f"a{i:03d}.mp3"
        audio_dur = tts_segment(text, audio, voice)
        planned = _planned_span(sc.get("label")) or 0.0
        dur = min(max(planned, audio_dur), MAX_SEG)
        plan.append({"i": i, "text": text, "audio": audio, "dur": dur})
    if not plan:
        raise RuntimeError("成片规划失败（无可用分镜）")
    total = sum(p["dur"] for p in plan)
    print(f"[render] 规划 {len(plan)} 镜 · 预计 {total:.1f}s（配音口播约 {sum(min(p['dur'], 8) for p in plan):.0f}s）")

    seg_files = []
    for r in plan:
        png = TMP_DIR / f"p{r['i']:03d}.png"
        draw_scene(r["i"], len(plan), r["text"], png, title=title if r["i"] == 1 else "")
        seg_mp4 = TMP_DIR / f"s{r['i']:03d}.mp4"
        rr = subprocess.run(
            [exe, "-y", "-loop", "1", "-i", str(png), "-i", str(r["audio"]),
             "-t", f"{r['dur']:.2f}", "-r", "25",
             "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "128k",
             "-shortest", str(seg_mp4)],
            capture_output=True, text=True,
        )
        if rr.returncode != 0:
            raise RuntimeError(f"片段 {r['i']} 合成失败: {rr.stderr[-400:]}")
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

    hook = clean_caption(adapted.get("hook") or "")
    cover = out_dir / f"guoxue_{date}_cover.png"
    draw_scene(0, len(plan), hook or "点击播放 读懂老祖宗的智慧", cover, cover=True, title=title)

    bgm_path = bgm or (DATA_DIR / "media" / "bgm.mp3")
    final = out_dir / f"guoxue_{date}.mp4"
    if Path(bgm_path).exists():
        rr = subprocess.run(
            [exe, "-y", "-i", str(raw), "-stream_loop", "-1", "-i", str(bgm_path),
             "-filter_complex",
             "[0:a]volume=1.0[vo];[1:a]volume=0.14,afade=t=out:st=2:d=2[bg];[vo][bg]amix=inputs=2:duration=first:dropout_transition=2[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", str(final)],
            capture_output=True, text=True,
        )
        if rr.returncode != 0:
            shutil.copy(raw, final)
    else:
        shutil.copy(raw, final)
    raw.unlink(missing_ok=True)

    srt = out_dir / f"guoxue_{date}.srt"
    t0 = 0.0
    with srt.open("w", encoding="utf-8") as f:
        for r in plan:
            a, b = t0, t0 + r["dur"]

            def ts(x):
                mm = int(x // 60)
                ss = x % 60
                return f"00:{mm:02d}:{ss:06.3f}".replace(".", ",")

            f.write(f"{r['i']}\n{ts(a)} --> {ts(b)}\n{r['text']}\n\n")
            t0 = b

    return {
        "ok": True,
        "date": date,
        "video": str(final.relative_to(DATA_DIR)),
        "cover": str(cover.relative_to(DATA_DIR)),
        "srt": str(srt.relative_to(DATA_DIR)),
        "segments": len(plan),
        "duration_s": round(t0, 2),
        "voice": voice,
        "bytes": final.stat().st_size,
    }


def main():
    ap = argparse.ArgumentParser(description="国学短视频一键成片（水墨风）")
    ap.add_argument("--date", default=None)
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--bgm", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    if not args.date:
        files = sorted(REPORT_DIR.glob("guoxue_*.json"))
        if not files:
            print("未找到 guoxue 产物，请先运行 guoxue_media")
            sys.exit(1)
        args.date = Path(files[-1]).stem.replace("guoxue_", "")
    out_dir = Path(args.out) if args.out else None
    print(json.dumps(render(args.date, voice=args.voice, bgm=args.bgm, out_dir=out_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
