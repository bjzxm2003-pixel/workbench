"""候选清单维护自检：判断今天该不该补链接。

用法：
  python -m jobs.check_candidates          # 只读本地报告与清单，不联网
  python -m jobs.check_candidates --live   # 顺带回源核实一遍清单（较慢）

依据清单头部的维护节奏规则，逐条给出结论：
  ① 今天是否已达「下次建议补充」日期
  ② 最新报告的「24-48 小时窗口内」是否 <= 2 条
  ③ 清单里"窗口内"分组的链接是否不足 4 条
满足任一条即提示需要补充。
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobs.toutiao_copy import CANDIDATE_FILE, REPORT_DIR, candidate_urls, parse_article  # noqa: E402

BJ = timezone(timedelta(hours=8))
WINDOW_MIN_LINKS = 4


def _header_text() -> str:
    return CANDIDATE_FILE.read_text(encoding="utf-8")


def next_refresh_date() -> str | None:
    m = re.search(r"下次建议补充[：:]\s*(\d{4}-\d{2}-\d{2})", _header_text())
    return m.group(1) if m else None


def fresh_group_count() -> int:
    """统计所有「窗口内」分组里带 ✅ 标记的链接数。

    按语义识别分组头（形如 "# —— xxx ——"，含“窗口内”即为窗口分组），
    因此「新增并已核实（窗口内）」与「上一批仍在窗口内」会合并统计；
    遇到「已出窗」等其他分组即停止计数。
    """
    collecting = False
    n = 0
    for line in _header_text().splitlines():
        if line.startswith("#") and "——" in line:
            collecting = "窗口内" in line.replace("——", "")
            continue
        if collecting and "toutiao.com" in line and "✅" in line:
            n += 1
    return n


def latest_report_window() -> tuple[str, int] | None:
    """从最新报告里读「落在 24-48 小时窗口内：N 条」。"""
    files = sorted(REPORT_DIR.glob("toutiao_copy_*.md"))
    if not files:
        return None
    latest = files[-1]
    m = re.search(r"落在 24-48 小时窗口内[：:]\s*\*\*(\d+)\*\*", latest.read_text(encoding="utf-8"))
    return (latest.name, int(m.group(1))) if m else (latest.name, -1)


def main() -> int:
    live = "--live" in sys.argv
    today = datetime.now(BJ).strftime("%Y-%m-%d")
    print(f"候选清单维护自检 · 今天 {today}（北京）\n" + "=" * 52)

    need = []

    # ① 日期是否到期
    due = next_refresh_date()
    if due:
        overdue = today >= due
        print(f"[{'需补充' if overdue else '尚可  '}] ① 下次建议补充：{due}"
              f"（今天 {today}，{'已到期' if overdue else '未到期'}）")
        if overdue:
            need.append("已达建议补充日期")
    else:
        print("[注意  ] ① 清单头部没有「下次建议补充」日期，建议补上")

    # ② 清单里窗口内的链接够不够（按分组的"✅"标记，秒回）
    marked = fresh_group_count()
    bad = marked < WINDOW_MIN_LINKS
    print(f"[{'需补充' if bad else '尚可  '}] ② 清单「窗口内」分组已标记 ✅ 的链接：{marked}"
          f"（阈值 {WINDOW_MIN_LINKS}）{'（不足，该补了）' if bad else ''}")
    if bad:
        need.append(f"清单窗口内链接仅 {marked} 条")

    # ③ 实测：回源核实清单里到底还有几条在 48h 内（最权威，但慢）
    if live:
        urls = candidate_urls()
        print(f"\n--- 联网回源核实（{len(urls)} 条，稍慢）---")
        inwin = 0
        for u in urls:
            r = parse_article(u)
            if r:
                h = r.get("pub_hours")
                if h is not None and h <= 48:
                    inwin += 1
                    print(f"  ✅ {r['pub_rel']:>8} {r['title'][:38]}")
        print(f"  实测仍在 48h 窗口内：{inwin} 条")
        if inwin < WINDOW_MIN_LINKS:
            need.append(f"实测窗口内仅 {inwin} 条")
        else:
            # 实测够用则撤销仅由"标记数"得出的结论，避免误报
            need = [x for x in need if "清单窗口内链接" not in x]
    else:
        rep = latest_report_window()
        if rep:
            name, n = rep
            print(f"[ 参考 ] ③ 最新报告 {name} 的窗口内条数：{n}"
                  f"（仅供参考：报告可能早于本次清单更新，加 --live 看实测）")

    print("\n" + "=" * 52)
    if need:
        print("结论：需要补充候选链接 —— " + "；".join(need))
        print("做法：搜近两日头条文章 → 逐条 parse_article 核实 → 更新清单与「下次建议补充」日期")
        return 1
    print("结论：暂不需要补充。下次自检或报告窗口数掉到 2 条以下时再补。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
