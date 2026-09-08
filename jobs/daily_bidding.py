"""② 日招标项目筛选助手（M2）

每日 18:00（北京，GH Actions cron: '0 10 * * *'）或手动：
  1. 抓取国能e招当日招标公告
  2. 关键词筛查（EPC/PC/施工/风电/煤电/光伏/电缆）
  3. 尽力提取详情页开标时间
  4. 与主表按规范化项目名合并（已存在→补 发布时间/开标时间；不存在→追加行）
  5. 写入主表、导出 xlsx/csv、推送新增/更新表到个人微信（Server酱）

用法：python -m jobs.daily_bidding [--date 2026-09-08] [--no-push|--push]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import parser, storage, wechat  # noqa: E402
from server.config import DATA_DIR, load_keywords  # noqa: E402
from jobs.crawl_bidding import fetch_announcements, fetch_open_time  # noqa: E402

BJ_TZ = timezone(timedelta(hours=8))
HISTORY_FILE = DATA_DIR / "bidding" / "daily_history.json"
LAST_RUN_FILE = DATA_DIR / "bidding" / "daily_last_run.json"


def today_bj() -> str:
    return datetime.now(BJ_TZ).strftime("%Y-%m-%d")


def load_json(path, default):
    if Path(path).exists():
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return default
    return default


def save_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def run_daily(target_date: str | None = None, push: bool | None = None, max_pages: int = 30) -> dict:
    date_str = target_date or today_bj()
    keywords = load_keywords()

    notes: list[str] = []
    announcements = fetch_announcements(max_pages=max_pages, stop_before=date_str)
    notes.append(f"抓取列表 {len(announcements)} 条")
    fresh = [a for a in announcements if a["date"] == date_str]
    notes.append(f"{date_str} 当日 {len(fresh)} 条")

    matched: list[dict] = []
    for a in fresh:
        hits = parser.match_keywords(a["title"], keywords)
        if not hits:
            continue
        a["keywords"] = hits
        matched.append(a)

    history = load_json(HISTORY_FILE, [])
    history_set = set(history)
    new_matched = [a for a in matched if a["id"] not in history_set]
    notes.append(f"关键词命中 {len(matched)} 条，历史去重后新增 {len(new_matched)} 条")

    # 详情页开标时间（尽力而为）
    for a in new_matched:
        a["open_at"] = fetch_open_time(a["url"])

    # 与主表合并
    master = storage.load_master()
    rows = master.get("rows", [])
    idx_of = {parser.norm_name(r.get("name")): i for i, r in enumerate(rows)}
    added, updated = [], []
    for a in new_matched:
        key = parser.norm_name(a["title"])
        if key in idx_of:
            r = rows[idx_of[key]]
            r["publish_at"] = a["date"] or r.get("publish_at", "")
            if a.get("open_at"):
                r["open_at"] = a["open_at"]
            if not r.get("keywords"):
                r["keywords"] = a["keywords"]
            if not r.get("url"):
                r["url"] = a["url"]
            r["status"] = r.get("status") or ""
            updated.append({"name": r["name"], "publish_at": r["publish_at"], "open_at": r["open_at"]})
        else:
            rows.append(
                {
                    "name": a["title"],
                    "expect_publish": "",
                    "publish_at": a["date"],
                    "open_at": a.get("open_at", ""),
                    "bidder": "",
                    "status": "",
                    "remark": "",
                    "keywords": a["keywords"],
                    "source": "国能e招",
                    "url": a["url"],
                }
            )
            added.append(rows[-1])

    if added or updated:
        master["updated_at"] = storage.stamp()
        master["rows"] = rows
        storage.save_master(master)
        storage.save_export_files(rows)
        notes.append(f"主表合并：新增 {len(added)}，补全 {len(updated)}，现共 {len(rows)} 项")

    # 记录历史（仅已处理的新增项）
    if new_matched:
        history.extend(a["id"] for a in new_matched)
        save_json(HISTORY_FILE, history)

    # 推送：新增/更新项表
    push_result = None
    want_push = push if push is not None else wechat.sc_configured()
    if want_push and (added or updated):
        md_lines = [f"**{date_str} 国能e招 关键词筛选（命中 {len(matched)} 条 / 新增 {len(added)}）**", ""]
        if added:
            md_lines += [
                "**🆕 新增并入主表：**",
                "| 序号 | 项目名称 | 发布时间 | 开标时间 | 链接 |",
                "| --- | --- | --- | --- | --- |",
            ]
            for i, r in enumerate(added, 1):
                nm = r["name"].replace("|", "\\|")
                md_lines.append(
                    f"| {i} | {nm} | {r.get('publish_at') or '—'} | {r.get('open_at') or '待定'} | [查看]({r.get('url', '')}) |"
                )
        if updated:
            md_lines += ["", f"**🔄 已存在项目补全：{len(updated)} 项（主表内更新 发布时间/开标时间）**"]
        md_lines += ["", f"> 主表现在共 {len(rows)} 项 · 完整表格见工作台/附件"]
        push_result = wechat.send_markdown(f"日招标筛选 · 新增 {len(added)} / 补全 {len(updated)}（{date_str}）", "\n".join(md_lines))
    elif want_push:
        push_result = {"sent": False, "reason": "今日无新增命中项，未推送"}

    summary = {
        "date": date_str,
        "crawled": len(announcements),
        "fresh": len(fresh),
        "matched": len(matched),
        "history_skipped": len(matched) - len(new_matched),
        "added": len(added),
        "updated": len(updated),
        "master_total": len(rows),
        "push": push_result,
        "notes": notes,
        "added_items": added,
    }
    last = {
        "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "date": date_str,
        "summary": {k: v for k, v in summary.items() if k != "added_items"},
    }
    save_json(LAST_RUN_FILE, last)
    return summary


def main():
    ap = argparse.ArgumentParser(description="日招标项目筛选助手")
    ap.add_argument("--date", default=None, help="目标日期 YYYY-MM-DD（默认今日，北京时间）")
    ap.add_argument("--push", action="store_true", default=None, help="强制推送")
    ap.add_argument("--no-push", dest="push", action="store_false", help="禁止推送")
    args = ap.parse_args()
    result = run_daily(target_date=args.date, push=args.push)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
