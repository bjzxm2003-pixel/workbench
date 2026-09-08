"""国能e招 招标公告抓取（招标公告频道）。

复用 tender-monitor 验证过的选择器：
  https://www.chnenergybidding.com.cn/bidweb/001/001002/moreinfo.html
"""
from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
LIST_URL = "https://www.chnenergybidding.com.cn/bidweb/001/001002/moreinfo.html"
PAGE_URL = "https://www.chnenergybidding.com.cn/bidweb/001/001002/{page}.html"
LIST_SELECTOR = "li.right-item"
TITLE_SELECTOR = "a.infolink"
DATE_SELECTOR = "span.r"


def _session():
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    return s


def _clean_date(raw: str) -> str:
    """span.r 通常形如 2026-09-08，个别带时间 → 归一为 YYYY-MM-DD。"""
    t = "".join(raw.split())
    m = re.match(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return t


def fetch_announcements(max_pages: int = 30, stop_before: str | None = None) -> list[dict]:
    """从第 1 页起抓列表；列表按日期倒序，遇到早于 stop_before（YYYY-MM-DD）即停止。"""
    out: list[dict] = []
    sess = _session()
    for page in range(1, max_pages + 1):
        url = LIST_URL if page == 1 else PAGE_URL.format(page=page)
        try:
            resp = sess.get(url, timeout=20)
            resp.raise_for_status()
        except Exception as e:  # noqa: BLE001
            print(f"[crawl] page {page} 请求失败: {e}")
            break
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select(LIST_SELECTOR)
        if not items:
            break
        page_done = False
        for it in items:
            a = it.select_one(TITLE_SELECTOR) or it
            title = (a.get("title") or a.get_text(" ", strip=True) or "").strip()
            href = (a.get("href") or "").strip()
            if not title or not href:
                continue
            if href.startswith("/"):
                href = "https://www.chnenergybidding.com.cn" + href
            sp = it.select_one(DATE_SELECTOR)
            date = _clean_date(sp.get_text(" ", strip=True)) if sp else ""
            if stop_before and date and date < stop_before:
                page_done = True
                break
            out.append(
                {
                    "title": title,
                    "url": href,
                    "date": date,
                    "id": hashlib.md5((title + href).encode("utf-8")).hexdigest(),
                }
            )
        print(f"[crawl] page {page}: {len(items)} 条，累计 {len(out)}")
        if page_done or len(items) < 10:
            break
        time.sleep(0.8)
    return out


_OPEN_RE = re.compile(
    r"(?:投标文件递交的截止时间|开标时间|投标截止时间)[^0-9年]{0,24}"
    r"(\d{4})\s*[年./-]\s*(\d{1,2})\s*[月./-]\s*(\d{1,2})\s*日?"
    r"(?:\s*(\d{1,2}):(\d{2})(?::\d{2})?)?"
)


def fetch_open_time(url: str, timeout: float = 6) -> str:
    """尽力从详情页提取开标时间，失败返回 ''（不阻塞主流程）。"""
    try:
        resp = _session().get(url, timeout=timeout)
        resp.encoding = resp.apparent_encoding or "utf-8"
        text = resp.text
    except Exception:  # noqa: BLE001
        return ""
    m = _OPEN_RE.search(text)
    if not m:
        return ""
    y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
    base = f"{y}-{mo:02d}-{d:02d}"
    if m.group(4):
        base += f" {int(m.group(4)):02d}:{m.group(5)}"
    return base
