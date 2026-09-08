"""月招标计划文件解析：xlsx/csv/pdf → 关键词筛查 → 去重 → 主表行。

支持的源表头（含常见别名，大小写/空格不敏感）：
  项目名称 / 预计发布公告时间 / 发布时间 / 开标时间 / 投标单位 / 状态 / 备注
未识别或缺失的列置空，由前端/后续流程补填。
"""
from __future__ import annotations

import io
import re
from datetime import date, datetime

from .config import load_keywords

# 别名映射（顺序即优先级）
HEADER_ALIASES = {
    "name": ["项目名称", "项目名", "名称", "工程名称", "招标项目名称", "招标计划名称", "采购项目名称", "计划名称"],
    "expect_publish": ["预计发布公告时间", "预计公告时间", "预计发布时间", "预计发标时间", "计划公告时间", "计划发布时间"],
    "publish_at": ["发布时间", "公告发布时间", "发布日期", "公告日期", "发标时间", "公告时间"],
    "open_at": ["开标时间", "开标日期", "投标截止时间", "投标截止日期", "截标时间"],
    "bidder": ["投标单位", "投标人", "投标单位名称", "拟投标单位", "投标商"],
    "status": ["状态", "投标状态", "报名状态"],
    "remark": ["备注", "说明", "其他说明", "备注说明"],
}

def _cell(v) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _norm(text) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip().lower()


def _norm_header(text) -> str:
    # 表头：去掉常见括号说明后规范化
    t = re.sub(r"[（(].*?[)）]", "", str(text or ""))
    return _norm(t)


NAME_ALIAS_NORM = {_norm_header(a) for a in HEADER_ALIASES["name"]}
HEADER_CELL_NORMS = {
    _norm_header(a) for aliases in HEADER_ALIASES.values() for a in aliases
} | {"序号"}


def normalize_date_text(s) -> str:
    """把常见中文/斜杠日期格式归一为 YYYY-MM-DD [HH:mm]。无法识别原样返回。"""
    t = str(s or "").strip()
    if not t:
        return t
    m = re.match(
        r"^(\d{4})\s*[年./\-]\s*(\d{1,2})\s*[月./\-]\s*(\d{1,2})\s*日?"
        r"(?:\s*(\d{1,2}):(\d{2}))?$",
        t,
    )
    if m:
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
        base = f"{y}-{mo:02d}-{d:02d}"
        if m.group(4):
            base += f" {int(m.group(4)):02d}:{m.group(5)}"
        return base
    return t


def map_header(row_vals: list) -> dict:
    """把源表头行映射为 {字段: 列下标}；exact 优先，其次别名包含匹配（别名>=4字）。"""
    mapping: dict[str, int] = {}
    normalized = [_norm_header(v) for v in row_vals]
    # pass1 exact
    for field, aliases in HEADER_ALIASES.items():
        for a in aliases:
            key = _norm(a)
            if key in normalized and field not in mapping:
                mapping[field] = normalized.index(key)
    # pass2 包含匹配：仅针对未被 exact 认领的单元格，避免“预计发布公告时间”被“公告时间”二次命中
    claimed = set(mapping.values())
    for field, aliases in HEADER_ALIASES.items():
        if field in mapping:
            continue
        for idx, hv in enumerate(normalized):
            if idx in claimed:
                continue
            for a in aliases:
                if len(_norm(a)) >= 4 and hv and _norm(a) in hv:
                    mapping[field] = idx
                    claimed.add(idx)
                    break
            if field in mapping:
                break
    return mapping


def is_header_row(row_vals: list) -> bool:
    """某行是否像表头：包含 项目名称 或 至少 2 个已识别的字段。"""
    mapped = map_header(row_vals)
    vals = {_norm_header(v) for v in row_vals if _norm_header(v)}
    name_aliases = {_norm(a) for a in HEADER_ALIASES["name"]}
    return bool(vals & name_aliases) or len(mapped) >= 2


def _date_text(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M" if (v.hour or v.minute) else "%Y-%m-%d")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = _cell(str(v))
    return s


def parse_workbook_data(rows: list[list], filename_hint: str = "") -> list[dict]:
    """从二维表数据中提取结构化行。"""
    # 找表头行（前 8 行内）
    header_idx, header_map = None, {}
    for i in range(min(len(rows), 8)):
        vals = rows[i]
        if is_header_row(vals):
            header_idx = i
            header_map = map_header(vals)
            break
    if header_idx is None:
        # 无表头：默认第 0 列是名称，第 1 列是预计发布公告时间
        header_map = {"name": 0, "expect_publish": 1}
        header_idx = -1

    out: list[dict] = []
    for vals in rows[header_idx + 1:]:
        if not vals or not any(str(v).strip() for v in vals):
            continue
        # 跳过分页重复的表头行
        headerish = [v for v in vals if _norm_header(v) in HEADER_CELL_NORMS]
        if len(headerish) >= 2:
            continue
        row = {"source": filename_hint}
        for field, col in header_map.items():
            if col < len(vals):
                if field.endswith("_at") or field in ("expect_publish", "publish_at", "open_at"):
                    row[field] = normalize_date_text(_date_text(vals[col]))
                else:
                    row[field] = _cell(vals[col])
            else:
                row[field] = ""
        name = row.get("name", "")
        if not name:
            continue
        # 名称列落入表头别名（兜底过滤）
        if _norm(name) in NAME_ALIAS_NORM:
            continue
        for f in ("expect_publish", "publish_at", "open_at", "bidder", "status", "remark"):
            row.setdefault(f, "")
        out.append(row)
    return out


def read_xlsx(bytes_: bytes) -> list[dict]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(bytes_), read_only=True, data_only=True)
    for ws in wb.worksheets:
        rows = []
        for r in ws.iter_rows(values_only=True):
            rows.append(["" if v is None else v for v in r])
        parsed = parse_workbook_data(rows, ws.title or "xlsx")
        if parsed:
            return parsed
    return []


def read_csv(bytes_: bytes) -> list[dict]:
    import csv

    text = None
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = bytes_.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError("CSV 编码无法识别（尝试 utf-8 / gb18030）")
    rows = [[c.strip() for c in line] for line in csv.reader(io.StringIO(text)) if any(c.strip() for c in line)]
    return parse_workbook_data(rows, "csv")


def read_pdf(bytes_: bytes) -> list[dict]:
    """PDF：优先尝试 pdfplumber 表格抽取；失败则 pypdf 文本行启发式解析。"""
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(bytes_)) as pdf:
            table_rows: list[list] = []
            for page in pdf.pages:
                for tbl in page.extract_tables() or []:
                    for r in tbl:
                        table_rows.append(["" if c is None else c for c in r])
            if table_rows:
                parsed = parse_workbook_data(table_rows, "pdf-table")
                if parsed:
                    return parsed
            # 无表格线 → 按文本行拆列（以多个空格为分隔的近似表）
            text_rows: list[list] = []
            for page in pdf.pages:
                txt = page.extract_text() or ""
                for line in txt.splitlines():
                    cols = re.split(r"\s{2,}", line.strip())
                    if cols:
                        text_rows.append(cols)
            return parse_workbook_data(text_rows, "pdf-text")
    except Exception:
        raise ValueError("PDF 解析失败：文件可能为扫描图片，请提供 Excel/CSV 版本")


def parse_file(filename: str, content: bytes) -> list[dict]:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in ("xlsx", "xlsm"):
        return read_xlsx(content)
    if ext == "csv":
        return read_csv(content)
    if ext == "pdf":
        return read_pdf(content)
    raise ValueError(f"不支持的文件类型 .{ext}（支持 xlsx / csv / pdf）")


def filter_and_dedupe(rows: list[dict], keywords: list[str] | None = None) -> dict:
    """关键词筛查 + 按项目名去重，返回汇总。"""
    keywords = keywords or load_keywords()
    kws_low = [k.casefold() for k in keywords]

    matched: list[dict] = []
    seen: dict[str, int] = {}
    dup_dropped = 0

    for r in rows:
        name = _cell(r.get("name"))
        if not name:
            continue
        name_low = name.casefold()
        hits = [keywords[i] for i, k in enumerate(kws_low) if k in name_low]
        if not hits:
            continue
        # 去子串重复命中：EPC 命中时不再单列 PC
        hits = [
            kw
            for kw in hits
            if not any(len(k2) > len(kw) and kw.casefold() in k2.casefold() for k2 in hits)
        ]
        key = _norm(name)
        if key in seen:
            dup_dropped += 1
            continue
        seen[key] = 1
        r["keywords"] = hits
        r["matched_kw"] = "、".join(hits)
        matched.append(r)

    summary = {
        "raw": len(rows),
        "matched": len(matched),
        "dup_dropped": dup_dropped,
        "final": len(matched),
        "keywords": keywords,
        "keyword_hits": {k: sum(1 for r in matched if k in (r.get("keywords") or [])) for k in keywords},
    }
    return {"rows": matched, "summary": summary}


def master_from_rows(rows: list[dict]) -> dict:
    """构建主表存储结构（只保留可见/内部字段，空值归一）。"""
    clean = []
    for r in rows:
        clean.append(
            {
                "name": _cell(r.get("name")),
                "expect_publish": _cell(r.get("expect_publish")),
                "publish_at": _cell(r.get("publish_at")),
                "open_at": _cell(r.get("open_at")),
                "bidder": _cell(r.get("bidder")),
                "status": _cell(r.get("status")),
                "remark": _cell(r.get("remark")),
                "keywords": list(r.get("keywords") or []),
                "source": _cell(r.get("source") or "月度计划"),
            }
        )
    return {"rows": clean}


def find_row(rows: list[dict], name: str) -> int | None:
    key = _norm(name)
    for i, r in enumerate(rows):
        if _norm(r.get("name")) == key:
            return i
    return None
