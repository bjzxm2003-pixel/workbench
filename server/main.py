"""工作台本地后端：月招标计划筛选助手（M1）与主表接口"""
import json
import uuid
from datetime import datetime

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from . import parser, storage, wechat
from .config import load_keywords

app = FastAPI(title="个人工作台 Backend", version="0.1.0")

# 上传预检缓存：token -> {rows, summary, filename}（本地单用户，内存足够）
CANDIDATES: dict[str, dict] = {}


def _process_rows(filename: str, content: bytes) -> dict:
    """解析 → 筛查去重 → 预览 → 建立确认会话（不落盘）。"""
    try:
        rows = parser.parse_file(filename, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = parser.filter_and_dedupe(rows)
    preview = parser.master_from_rows(result["rows"])["rows"]
    token = uuid.uuid4().hex
    CANDIDATES[token] = {"rows": preview, "summary": result["summary"], "filename": filename}
    return {"token": token, "summary": result["summary"], "preview": preview, "filename": filename}


@app.get("/api/health")
def health():
    master = storage.load_master()
    return {
        "ok": True,
        "keywords": load_keywords(),
        "sc_configured": wechat.sc_configured(),
        "master_count": len(master.get("rows", [])),
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------- 主表 ----------
@app.get("/api/bids/master")
def get_master():
    master = storage.load_master()
    rows = master.get("rows", [])
    return {
        "rows": rows,
        "count": len(rows),
        "updated_at": master.get("updated_at"),
        "source": "master" if rows else "empty",
    }


@app.post("/api/bids/master/upload")
async def upload_master_file(file: UploadFile = File(...)):
    """上传 → 解析 → 关键词筛查去重 → 返回预检预览（不落盘）"""
    raw = await file.read()
    return _process_rows(file.filename or "upload.xlsx", raw)


@app.post("/api/bids/master/preview-sample")
def preview_sample():
    """用内置样例文件跑一遍预检（联调/演示用）。"""
    from pathlib import Path

    from .config import SAMPLES_DIR

    files = sorted(Path(SAMPLES_DIR).glob("*"))
    files = [f for f in files if f.suffix.lower() in (".pdf", ".xlsx", ".xlsm", ".csv")]
    if not files:
        raise HTTPException(status_code=404, detail="data/samples/ 下暂无样例文件")
    path = files[0]
    return _process_rows(path.name, path.read_bytes())


@app.post("/api/bids/master/confirm")
def confirm_master(payload: dict):
    """确认：把预检结果写入主表（覆盖式，月度计划为权威源）→ 导出 → 可选推送"""
    token = (payload or {}).get("token", "")
    push = bool((payload or {}).get("push", False))
    cand = CANDIDATES.pop(token, None)
    if not cand:
        raise HTTPException(status_code=404, detail="预检会话不存在或已过期，请重新上传")
    rows = cand["rows"]
    master = {
        "updated_at": storage.stamp(),
        "source": cand.get("filename") or "月度计划",
        "rows": rows,
    }
    storage.save_master(master)
    exports = storage.save_export_files(rows)
    push_result = None
    if push:
        title = f"月招标计划筛选结果（{len(rows)} 项）"
        md = wechat.build_table_markdown(master)
        push_result = wechat.send_markdown(title, md)
    return {
        "count": len(rows),
        "updated_at": master["updated_at"],
        "exports": exports,
        "push": push_result,
        "summary": cand["summary"],
    }


@app.post("/api/bids/master/update")
def update_row(payload: dict):
    """状态登记写回：按项目名更新 投标单位/状态/备注。"""
    name = str((payload or {}).get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="缺少项目名称")
    master = storage.load_master()
    idx = parser.find_row(master.get("rows", []), name)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"主表中未找到项目「{name}」，请先上传月计划或等待日招标接入")
    row = master["rows"][idx]
    if "status" in payload:
        status = str(payload["status"] or "").strip()
        if status not in ("已投", "在投", "放弃", ""):
            raise HTTPException(status_code=400, detail="状态仅支持：已投 / 在投 / 放弃")
        row["status"] = status
    if "bidder" in payload:
        row["bidder"] = str(payload["bidder"] or "").strip()
    if "remark" in payload:
        row["remark"] = str(payload["remark"] or "").strip()
    master["updated_at"] = storage.stamp()
    storage.save_master(master)
    return {"ok": True, "row": row, "updated_at": master["updated_at"]}


@app.get("/api/bids/master/file")
def master_file(fmt: str = "xlsx"):
    """下载主表导出文件（xlsx / csv）"""
    master = storage.load_master()
    rows = master.get("rows", [])
    if fmt not in ("xlsx", "csv"):
        raise HTTPException(status_code=400, detail="format 仅支持 xlsx / csv")
    path = storage.export_download(rows, fmt)
    media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if fmt == "xlsx" else "text/csv; charset=utf-8"
    name = f"招标主表_{datetime.now().strftime('%Y%m%d')}.{fmt}"
    return FileResponse(path, media_type=media, filename=name)


# ---------- M2：日招标项目筛选助手（手动触发/状态） ----------
@app.get("/api/jobs/daily/status")
def daily_status():
    from pathlib import Path

    from .config import DATA_DIR

    last_file = DATA_DIR / "bidding" / "daily_last_run.json"
    last = None
    if last_file.exists():
        try:
            last = json.loads(last_file.read_text(encoding="utf-8"))
        except Exception:
            last = None
    return {
        "sc": wechat.sc_configured(),
        "keywords": load_keywords(),
        "schedule": "每日 18:00（北京）· GitHub Actions cron '0 10 * * *'",
        "last_run": last,
    }


@app.post("/api/jobs/daily/run")
def daily_run(payload: dict | None = None):
    """立即运行一次日筛选：抓取当日→筛查→合并主表→导出→（可选）推送"""
    from jobs.daily_bidding import run_daily

    push = None
    if isinstance(payload, dict) and "push" in payload:
        push = bool(payload.get("push"))
    return run_daily(push=push)


# ---------- M3：招标项目提醒助手（手动触发/状态） ----------
@app.get("/api/jobs/reminder/status")
def reminder_status():
    from pathlib import Path

    from .config import DATA_DIR

    last_file = DATA_DIR / "bidding" / "reminder_last_run.json"
    last = None
    if last_file.exists():
        try:
            last = json.loads(last_file.read_text(encoding="utf-8"))
        except Exception:
            last = None
    return {
        "sc": wechat.sc_configured(),
        "schedule": "每日 09:00（北京）· GitHub Actions cron '0 1 * * *'",
        "last_run": last,
    }


@app.post("/api/jobs/reminder/run")
def reminder_run(payload: dict | None = None):
    """立即执行明日开标提醒（测试/手动）"""
    from jobs.open_reminder import run_reminder

    push = None
    if isinstance(payload, dict) and "push" in payload:
        push = bool(payload.get("push"))
    return run_reminder(push=push)


# ---------- M4：银发康养自媒体助手 ----------
@app.get("/api/jobs/silver/status")
def silver_status():
    from pathlib import Path

    from .config import DATA_DIR, load_media_keywords
    from .llm import llm_configured

    last = None
    last_file = DATA_DIR / "media" / "silver_last_run.json"
    if last_file.exists():
        try:
            last = json.loads(last_file.read_text(encoding="utf-8"))
        except Exception:
            last = None
    return {
        "sc": wechat.sc_configured(),
        "llm": llm_configured(),
        "keywords": load_media_keywords("silver"),
        "schedule": "每日 17:00（北京）· GitHub Actions cron '0 9 * * *'",
        "last_run": last,
    }


@app.post("/api/jobs/silver/run")
def silver_run(payload: dict | None = None):
    """立即生成今日银发康养日报（热榜采集 + LLM 拆解改写 + 可选推送）"""
    from jobs.silver_media import run_silver

    push = None
    if isinstance(payload, dict) and "push" in payload:
        push = bool(payload.get("push"))
    return run_silver(push=push)


@app.get("/api/jobs/silver/report")
def silver_report(date: str):
    """读取某日报告原文（date=YYYY-MM-DD）"""
    from pathlib import Path

    from .config import DATA_DIR

    f = DATA_DIR / "media" / "reports" / f"silver_{date}.md"
    if not f.exists():
        raise HTTPException(status_code=404, detail=f"无 {date} 的银发康养日报")
    return {"date": date, "markdown": f.read_text(encoding="utf-8")}
