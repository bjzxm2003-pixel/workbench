"""招标主表（master_bids）的读写与导出。"""
import json
import io
import csv
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from .config import MASTER_FILE, EXPORT_DIR, ensure_dirs

EXPORT_HEADERS = ["序号", "项目名称", "预计发布公告时间", "发布时间", "开标时间", "投标单位", "状态"]


def empty_master() -> dict:
    return {"updated_at": None, "source": None, "rows": []}


def load_master() -> dict:
    ensure_dirs()
    if MASTER_FILE.exists():
        try:
            data = json.loads(MASTER_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "rows" in data:
                return data
        except Exception:
            pass
    return empty_master()


def save_master(master: dict) -> None:
    ensure_dirs()
    MASTER_FILE.write_text(
        json.dumps(master, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _cell(v):
    """导出单元格安全化"""
    if v is None:
        return ""
    return str(v)


def to_export_rows(rows: list) -> list[list]:
    out = []
    for i, r in enumerate(rows, start=1):
        out.append(
            [
                i,
                _cell(r.get("name")),
                _cell(r.get("expect_publish")),
                _cell(r.get("publish_at")),
                _cell(r.get("open_at")),
                _cell(r.get("bidder")),
                _cell(r.get("status")),
            ]
        )
    return out


def export_xlsx_bytes(rows: list) -> io.BytesIO:
    wb = Workbook()
    ws = wb.active
    ws.title = "招标主表"
    ws.append(EXPORT_HEADERS)
    head_fill = PatternFill("solid", fgColor="16324F")
    for c in range(1, len(EXPORT_HEADERS) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for row in to_export_rows(rows):
        ws.append(row)
    widths = [6, 48, 18, 18, 18, 24, 10]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def export_csv_bytes(rows: list) -> io.BytesIO:
    import csv

    sio = io.StringIO()
    writer = csv.writer(sio)
    writer.writerow(EXPORT_HEADERS)
    for row in to_export_rows(rows):
        writer.writerow(row)
    # BOM 便于 Excel 直接打开中文
    buf = io.BytesIO(("\ufeff" + sio.getvalue()).encode("utf-8"))
    buf.seek(0)
    return buf


def save_export_files(rows: list) -> dict:
    """确认生成后落盘 xlsx/csv（含时间戳与 latest 两份），返回路径相对 data/bidding 展示用。"""
    ensure_dirs()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    paths = {}
    for ext, fn in (("xlsx", export_xlsx_bytes), ("csv", export_csv_bytes)):
        name = f"master_{ts}.{ext}"
        (EXPORT_DIR / name).write_bytes(fn(rows).getvalue())
        # 覆盖 latest，便于固定链接
        (EXPORT_DIR / f"master_latest.{ext}").write_bytes(fn(rows).getvalue())
        paths[ext] = name
    return paths


def export_download(rows: list, fmt: str) -> Path:
    """生成可下载文件（在内存文件中写入临时 latest 名，返回路径）"""
    ensure_dirs()
    name = f"master_latest.{fmt}"
    target = EXPORT_DIR / name
    if fmt == "xlsx":
        target.write_bytes(export_xlsx_bytes(rows).getvalue())
    else:
        target.write_bytes(export_csv_bytes(rows).getvalue())
    return target
