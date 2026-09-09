"""⑤ 国学经典自媒体助手（M5）

每日 16:00（北京，GH Actions cron: '0 8 * * *'）或手动：
  1. 选题候选：抖音/快手爆款数据公开接口不可用（反爬/需登录）→ 由 DeepSeek 按近期趋势模拟
     "代表性爆款短视频"（口播/剧情/干货类，指标标注为 AI 预估）
  2. Top3 → LLM 逐条拆解：前 3 秒看点 / 脚本推进逻辑 / 成功要素（完播·点赞·评论）
  3. 取第 1 名改编为 ≤1 分钟抖音脚本：主题融合"国学经典 × 个人成长/商业智慧"，
     输出 标题/钩子(0-3s)/逐字口播稿/分镜表/字幕·音乐·音色建议/发布建议
  4. 报告存 data/media/reports/guoxue_YYYY-MM-DD.md，推送摘要到个人微信

注意：本助手产出"创作包"，短视频成片需人工在 剪映/即梦 等工具合成（见报告尾部说明）。

用法：python -m jobs.guoxue_media [--date YYYY-MM-DD] [--no-push|--push]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import wechat  # noqa: E402
from server.config import DATA_DIR, load_media_keywords  # noqa: E402
from server.llm import deepseek_json, llm_configured, LLMError  # noqa: E402

BJ_TZ = timezone(timedelta(hours=8))
REPORT_DIR = DATA_DIR / "media" / "reports"
LAST_RUN_FILE = DATA_DIR / "media" / "guoxue_last_run.json"


def today_bj() -> str:
    return datetime.now(BJ_TZ).strftime("%Y-%m-%d")


def _save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _metric(it: dict) -> str:
    if it.get("sim"):
        return f"模拟点赞 {it.get('like')}"
    return f"热度 {it.get('metric') or '—'}"


def ai_candidates(keywords: list[str]) -> list[dict]:
    """AI 模拟近期国学好物/智慧向爆款短视频选题（平台爆款指标不可公开抓取）。"""
    kw = "、".join(keywords)
    out = deepseek_json(
        [
            {"role": "system", "content": "你是懂抖音/快手内容生态的国学短视频策划，只输出 JSON 对象。"},
            {
                "role": "user",
                "content": (
                    f"围绕国学经典（关键词：{kw}），设计 6 条近半年最具代表性的爆款短视频选题"
                    "（覆盖：口播金句、剧情反转、干货讲解、场景演绎等类型，平台为抖音/快手）。"
                    '每条字段：{"platform":"抖音或快手","type":"口播/剧情/干货等",'
                    '"keyword":"命中的国学关键词","title":"视频标题文案",'
                    '"hook":"前3秒钩子（一句话）","logic":"脚本一句话概括（人物→冲突→金句）",'
                    '"like":点赞整数,"comment":评论整数,"collect":收藏整数,"play":"播放量如 3000万"}'
                    '整体：{"candidates":[...]}。点赞区间 8万-220万，突出真实爆款感。'
                ),
            },
        ],
        temperature=1.0,
        max_tokens=2200,
    )
    items = []
    for c in (out or {}).get("candidates") or []:
        items.append(
            {
                "title": str(c.get("title", "")).strip(),
                "platform": str(c.get("platform", "抖音")),
                "type": str(c.get("type", "口播")),
                "keyword": str(c.get("keyword", "")),
                "hook": str(c.get("hook", "")).strip(),
                "logic": str(c.get("logic", "")).strip(),
                "like": int(c.get("like") or 0),
                "comment": int(c.get("comment") or 0),
                "collect": int(c.get("collect") or 0),
                "play": str(c.get("play", "")),
                "sim": True,
            }
        )
    return [i for i in items if i["title"]][:5]


def analyze_top3(top3: list[dict]) -> list[dict]:
    payload = [
        {
            "idx": i,
            "platform": it["platform"],
            "type": it.get("type", ""),
            "title": it["title"],
            "hook": it.get("hook", ""),
            "logic": it.get("logic", ""),
        }
        for i, it in enumerate(top3, 1)
    ]
    out = deepseek_json(
        [
            {"role": "system", "content": "你是爆款短视频拆解专家，只输出 JSON 对象。"},
            {
                "role": "user",
                "content": (
                    "请逐条拆解以下 3 条国学爆款短视频（与输入同序）。每条结构："
                    '{"idx":序号,"hook_points":["前3秒最抓人的2-3个看点，各一句话"],'
                    '"script_flow":["还原其脚本/剧情推进逻辑，3-5步，各一句话"],'
                    '"success":["完播/点赞/评论高的原因分析，3-4条：情绪共鸣/反转/干货/视觉等"]}'
                    f'整体：{{"analyses":[...]}}。输入：{json.dumps(payload, ensure_ascii=False)}'
                ),
            },
        ],
        temperature=0.7,
        max_tokens=2400,
    )
    analyses = {a.get("idx"): a for a in (out or {}).get("analyses") or []}
    return [analyses.get(i, {}) for i in range(1, len(top3) + 1)]


def adapt_script(item: dict, keywords: list[str]) -> dict:
    kw = "、".join(keywords)
    out = deepseek_json(
        [
            {"role": "system", "content": "你是国学×短视频编剧（擅长把国学智慧讲成现代人爱看的抖音内容），只输出 JSON 对象。"},
            {
                "role": "user",
                "content": (
                    f"基于以下参考爆款的结构，为抖音创作一条 55-60 秒的改编短视频脚本。"
                    f"主题要求：融合【{kw}】中的国学经典 × 个人成长/商业智慧（如：道德经·柔弱胜刚强→谈判/职场低谷、"
                    "易经·潜龙勿用→蛰伏期、论语·君子和而不同→团队管理，任选并自由发挥）。"
                    '输出字段：{"title":"视频封面标题/文案","hook":"0-3秒：画面+口播（决定完播）",'
                    '"script":"完整口播逐字稿（约240-300字，用\\n分段，含金句收尾与互动引导）",'
                    '"storyboard":[{"t":"0-3s","scene":"画面/景别/运镜","text":"口播或字幕"}...]（8-10镜覆盖全片）,'
                    '"style":{"captions":"字幕样式建议","bgm":"配乐情绪建议","voice":"音色/语速建议"},'
                    '"post":{"cover":"封面大字建议","topic":"#话题 3-5个","best_time":"最佳发布时间与理由",'
                    '"cta":"评论区置顶引导语"}}'
                    f"参考爆款：{json.dumps(item, ensure_ascii=False)}"
                ),
            },
        ],
        temperature=0.9,
        max_tokens=3600,
    )
    return {
        "title": str(out.get("title", "")).strip(),
        "hook": str(out.get("hook", "")).strip(),
        "script": str(out.get("script", "")).strip(),
        "storyboard": out.get("storyboard") or [],
        "style": out.get("style") or {},
        "post": out.get("post") or {},
    }


def build_report(date_str: str, candidates: list, top3: list, analyses: list, adapted: dict, kw: str) -> str:
    L = [
        f"# 📜 国学经典 · 爆款短视频拆解与改编脚本（{date_str}）",
        "",
        f"> 关键词：{kw}",
        "> 数据源：抖音/快手公开接口不可用（需登录/反爬），本期选题为 **DeepSeek 趋势模拟**，点赞/播放等指标为模型预估（创作参考）。",
        "",
        "---",
        "",
        "## 一、Top 3 爆款短视频拆解",
        "",
    ]
    for i, it in enumerate(top3, 1):
        a = analyses[i - 1] if i - 1 < len(analyses) else {}
        L.append(f"### 第 {i} 名 · 《{it['title']}》")
        L += [
            f"- 平台/类型：{it.get('platform')} · {it.get('type')} · {_metric(it)} · 关键词：{it.get('keyword', '')}",
            f"- 参考钩子：{it.get('hook', '—')}",
            f"- 参考脚本一句话：{it.get('logic', '—')}",
        ]
        hooks = a.get("hook_points") or []
        if hooks:
            L.append("")
            L.append("**① 提炼核心看点（最吸引人的前 3 秒）**")
            L += [f"- {h}" for h in hooks]
        flows = a.get("script_flow") or []
        if flows:
            L.append("")
            L.append("**② 解析视频脚本（口播/剧情推进逻辑）**")
            L += [f"{j}. {f}" for j, f in enumerate(flows, 1)]
        succ = a.get("success") or []
        if succ:
            L.append("")
            L.append("**③ 分析成功要素（完播/点赞/评论）**")
            L += [f"- {s}" for s in succ]
        L.append("")
        L.append("---")
        L.append("")
    L += ["## 二、改编短视频脚本（≤60s · 抖音 · 国学经典 × 个人成长/商业智慧）", ""]
    if adapted.get("title"):
        L += ["**封面标题：**", f"> {adapted['title']}", ""]
    if adapted.get("hook"):
        L += ["**0-3 秒钩子：**", f"> {adapted['hook']}", ""]
    if adapted.get("script"):
        L += ["**口播逐字稿：**", "", adapted["script"], ""]
    sb = adapted.get("storyboard") or []
    if sb:
        L += ["**分镜表：**", "", "| 时间 | 画面/景别 | 口播/字幕 |", "| --- | --- | --- |"]
        for s in sb:
            L.append(f"| {s.get('t','')} | {str(s.get('scene','')).replace('|','\\|')} | {str(s.get('text','')).replace('|','\\|')} |")
        L.append("")
    st = adapted.get("style") or {}
    if st:
        L += ["**风格建议：**"]
        L += [f"- {k}：{v}" for k, v in st.items()]
        L.append("")
    pt = adapted.get("post") or {}
    if pt:
        L += ["**发布建议：**"]
        for k, v in pt.items():
            L.append(f"- {k}：{v}")
    L += ["", "---", "", "> **短视频成片**：本脚本为创作包，请在剪映/即梦等工具中按分镜表配音、配字幕与音乐合成后发布抖音。", ""]
    return "\n".join(L)


def digest_md(date_str: str, top3: list, adapted: dict, report_rel: str) -> str:
    L = [f"📜 **国学爆款日报 · {date_str}**", ""]
    L.append("**今日 Top3（AI 模拟）**")
    for i, it in enumerate(top3, 1):
        L.append(f"{i}. 《{it['title']}》 · {it.get('platform')} · {it.get('type')}")
    L.append("")
    L.append("**✍️ 改编短视频（国学×成长/商业）**")
    L.append(f"> 标题：{adapted.get('title') or '—'}")
    hook = (adapted.get("hook") or "").replace("\n", " ")
    L.append(f"> 前3秒：{hook[:120]}")
    script = (adapted.get("script") or "").replace("\n", " ")
    if len(script) > 360:
        script = script[:360] + "……"
    L.append(f"> 口播：{script}")
    L.append("")
    L.append(f"完整拆解+分镜表见工作台「国学自媒体」页（{report_rel}）")
    return "\n".join(L)


def run_guoxue(date_str: str | None = None, push: bool | None = None) -> dict:
    if not llm_configured():
        raise LLMError("未配置 DEEPSEEK_API_KEY：M5 需要大模型拆解与脚本创作")
    d = date_str or today_bj()
    keywords = load_media_keywords("guoxue")
    kw_text = "、".join(keywords)

    cands = ai_candidates(keywords)
    if not cands:
        raise LLMError("AI 选题生成失败，请重试")
    cands = sorted(cands, key=lambda x: x.get("like") or 0, reverse=True)
    top3 = cands[:3]
    analyses = analyze_top3(top3)
    adapted = adapt_script(top3[0], keywords)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report(d, cands, top3, analyses, adapted, kw_text)
    report_rel = f"data/media/reports/guoxue_{d}.md"
    (REPORT_DIR / f"guoxue_{d}.md").write_text(report, encoding="utf-8")
    # 结构化产物：供 jobs/video_render.py 一键成片使用
    (REPORT_DIR / f"guoxue_{d}.json").write_text(
        json.dumps({"date": d, "keywords": keywords, "top3": top3, "adapted": adapted}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    push_result = None
    if push or (push is None and wechat.sc_configured()):
        push_result = wechat.send_markdown(f"📜 国学爆款日报 · {d}", digest_md(d, top3, adapted, report_rel))

    result = {
        "date": d,
        "candidates": len(cands),
        "top3": [
            {"title": it["title"], "platform": it.get("platform"), "type": it.get("type"), "metric": _metric(it)}
            for it in top3
        ],
        "adapted_title": adapted.get("title"),
        "report_file": report_rel,
        "push": push_result,
    }
    _save_json(
        LAST_RUN_FILE,
        {"last_run": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"), **result},
    )
    return result


def main():
    ap = argparse.ArgumentParser(description="国学经典自媒体助手")
    ap.add_argument("--date", default=None)
    ap.add_argument("--push", action="store_true", default=None)
    ap.add_argument("--no-push", dest="push", action="store_false")
    args = ap.parse_args()
    result = run_guoxue(date_str=args.date, push=args.push)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
