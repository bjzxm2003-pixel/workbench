"""③ 招标项目提醒助手（M3）

每日 09:00（北京，GH Actions cron: '0 1 * * *'）或手动：
  1. 读主表，筛选"开标时间 == 明日"的项目
  2. 将 项目名称/开标时间/状态/投标单位/备注/链接 整理成文字
  3. 推送到个人微信（Server酱）；无明日开标时默认不打扰，仅记录运行

用法：python -m jobs.open_reminder [--as-of 2026-09-28] [--no-push|--push]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import storage, wechat  # noqa: E402
from server.config import DATA_DIR  # noqa: E402

BJ_TZ = timezone(timedelta(hours=8))
LAST_RUN_FILE = DATA_DIR / "bidding" / "reminder_last_run.json"


def today_bj() -> str:
    return datetime.now(BJ_TZ).strftime("%Y-%m-%d")


def _open_date(open_at) -> str:
    """'YYYY-MM-DD HH:mm' / 'YYYY-MM-DD' → 'YYYY-MM-DD'；无法解析返回 ''"""
    t = str(open_at or "").strip()
    try:
        return datetime.strptime(t[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def collect_tomorrow_rows(as_of: str | None = None) -> list[dict]:
    base = as_of or today_bj()
    tomorrow = (datetime.strptime(base, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    master = storage.load_master()
    rows = master.get("rows", [])
    items = []
    for i, r in enumerate(rows, start=1):
        if _open_date(r.get("open_at")) == tomorrow:
            items.append({"seq": i, "row": r})
    return items, tomorrow, base


def build_message(items: list[dict], tomorrow: str, master_total: int) -> str:
    lines = [
        f"⏰ **明日开标提醒 · {tomorrow}**",
        "",
        f"主表中明日开标 **{len(items)}** 项，请提前准备：",
        "",
    ]
    for it in items:
        r = it["row"]
        status = r.get("status") or "待登记"
        bidder = r.get("bidder") or "未登记"
        lines += [
            f"**{it['seq']}. {r.get('name', '')}**",
            f"- 开标时间：{r.get('open_at')}",
            f"- 状态：{status}",
            f"- 投标单位：{bidder}",
        ]
        if r.get("remark"):
            lines.append(f"- 备注：{r.get('remark')}")
        if r.get("url"):
            lines.append(f"- 公告：[查看]({r.get('url')})")
        lines.append("")
    lines.append(f"> 主表共 {master_total} 项 · 由工作台 ③ 提醒助手定时发送")
    return "\n".join(lines)


def run_reminder(as_of: str | None = None, push: bool | None = None) -> dict:
    items, tomorrow, base = collect_tomorrow_rows(as_of)
    master = storage.load_master()
    master_total = len(master.get("rows", []))
    names = [it["row"].get("name", "") for it in items]

    push_result = None
    want_push = push if push is not None else wechat.sc_configured()
    if items:
        if want_push:
            push_result = wechat.send_markdown(
                f"⏰ 明日开标提醒 · {tomorrow}（{len(items)} 项）",
                build_message(items, tomorrow, master_total),
            )
        else:
            push_result = {"sent": False, "reason": "推送已禁用（--no-push 或未配置 SCKEY）"}
    else:
        push_result = {"sent": False, "reason": "明日无开标项目，不打扰"}

    summary = {
        "as_of": base,
        "remind_date": tomorrow,
        "count": len(items),
        "names": names,
        "master_total": master_total,
        "push": push_result,
    }
    last = {
        "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "as_of": base,
        "remind_date": tomorrow,
        **summary,
    }
    Path(LAST_RUN_FILE).write_text(json.dumps(last, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main():
    ap = argparse.ArgumentParser(description="招标项目提醒助手")
    ap.add_argument("--as-of", default=None, help="以该日为准算明日（YYYY-MM-DD，默认今日北京时间）")
    ap.add_argument("--push", action="store_true", default=None, help="强制推送")
    ap.add_argument("--no-push", dest="push", action="store_false", help="禁止推送")
    args = ap.parse_args()
    result = run_reminder(as_of=args.as_of, push=args.push)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
