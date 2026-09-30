"""对照实验：验证「要求模型编造互动量数据」的提示词是否触发内容风控。

四个探针两两成对，每对只差「是否要求编造点赞/评论/收藏」这一个变量：
  A. 原始（含编造指标）  vs  B. 同语义、去掉编造指标
  C. 银发链路原始         vs  D. 银发链路去掉编造指标

用法：python -m jobs.diag_risk_ab
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobs.diag_risk import call, save  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "data" / "media" / "diag"

KW_GX = "国学、易经、道德经、黄帝内经、论语、人生智慧"
KW_SV = "银发经济、康养、养老产业、老龄化、适老化、老年生活"

# ---- A：国学链路原始提示词（jobs/guoxue_media.py ai_candidates） ----
A_USER = (
    f"围绕国学经典（关键词：{KW_GX}），设计 6 条近半年最具代表性的爆款短视频选题"
    "（覆盖：口播金句、剧情反转、干货讲解、场景演绎等类型，平台为抖音/快手）。"
    '每条字段：{"platform":"抖音或快手","type":"口播/剧情/干货等",'
    '"keyword":"命中的国学关键词","title":"视频标题文案",'
    '"hook":"前3秒钩子（一句话）","logic":"脚本一句话概括（人物→冲突→金句）",'
    '"like":点赞整数,"comment":评论整数,"collect":收藏整数,"play":"播放量如 3000万"}'
    '整体：{"candidates":[...]}。点赞区间 8万-220万，突出真实爆款感。'
)

# ---- B：与 A 完全同语义，仅去掉「编造互动量」 ----
B_USER = (
    f"围绕国学经典（关键词：{KW_GX}），设计 6 条近半年最具代表性的爆款短视频选题方向"
    "（覆盖：口播金句、剧情反转、干货讲解、场景演绎等类型，平台为抖音/快手）。"
    '每条字段：{"platform":"抖音或快手","type":"口播/剧情/干货等",'
    '"keyword":"命中的国学关键词","title":"视频标题文案",'
    '"hook":"前3秒钩子（一句话）","logic":"脚本一句话概括（人物→冲突→金句）"}'
    '整体：{"candidates":[...]}。'
    "注意：不得编造或估计任何点赞、评论、收藏、播放数据；这些字段一律不要输出。"
)

SYS_GX = "你是懂抖音/快手内容生态的国学短视频策划，只输出 JSON 对象。"

# ---- C：银发链路原始提示词（jobs/silver_media.py ai_fallback） ----
C_USER = (
    f"围绕银发经济/康养方向（关键词：{KW_SV}），请设计 5 条近期最可能爆火的今日头条/小红书文案选题。"
    '每条字段：{"platform": "今日头条或小红书", "keyword": "命中的关键词", "title": "完整标题", '
    '"abstract": "一句话内容概要", "like": 点赞整数, "comment": 评论整数, "collect": 收藏整数, "share": 转发整数}'
    '整体结构：{"candidates": [...]}。点赞区间 1.2万-18万，突出真实感，避免夸张离谱。'
)

# ---- D：与 C 同语义，仅去掉编造指标 ----
D_USER = (
    f"围绕银发经济/康养方向（关键词：{KW_SV}），请设计 5 条近期最可能爆火的今日头条/小红书文案选题。"
    '每条字段：{"platform": "今日头条或小红书", "keyword": "命中的关键词", "title": "完整标题", '
    '"abstract": "一句话内容概要"}'
    '整体结构：{"candidates": [...]}。'
    "注意：不得编造或估计任何点赞、评论、收藏、转发数据；这些字段一律不要输出。"
)

SYS_SV = "你是资深自媒体内容策划。请输出 JSON 对象，不要输出其它文字。"

PROBES = [
    ("A-国学原始（含编造指标）", SYS_GX, A_USER),
    ("B-国学去掉编造指标", SYS_GX, B_USER),
    ("C-银发原始（含编造指标）", SYS_SV, C_USER),
    ("D-银发去掉编造指标", SYS_SV, D_USER),
]


def main() -> int:
    results = []
    for name, sys_msg, user_msg in PROBES:
        msgs = [{"role": "system", "content": sys_msg},
                {"role": "user", "content": user_msg}]
        for round_no in (1, 2):
            r = call(msgs, temperature=1.0, max_tokens=1200, json_mode=True)
            r.update({"name": f"{name}#{round_no}"})
            save(f"ab_{name.replace(' ', '_')}_{round_no}", r)
            flag = "OK     " if r["ok"] else f"{r['kind']:<7}"
            print(f"[{flag}] {name} #{round_no}  {r['text'][:110]!r}", flush=True)
            results.append(r)

    print("\n============ 对照结论 ============")
    for name, _, _ in PROBES:
        rs = [r for r in results if r["name"].startswith(name)]
        blocked = sum(1 for r in rs if r["kind"] == "BLOCKED")
        print(f"{name:<26} 被拦截 {blocked}/{len(rs)}")
    print(f"明细：{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
