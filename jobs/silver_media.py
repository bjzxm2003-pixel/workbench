"""④ 银发康养自媒体助手（M4）

每日 17:00（北京，GH Actions cron: '0 9 * * *'）或手动：
  1. 采集候选：今日头条热榜实时话题按关键词（银发经济/康养/养老产业…）过滤（真实热度）
  2. 不足 3 条时由 DeepSeek 按近期趋势模拟补齐（明确标注"AI 趋势模拟"，不冒充真实数据）
  3. Top3（真实按热度，模拟按点赞）→ DeepSeek 四步拆解：提炼标题/核心内容/文案框架/三个改写方向
  4. 取第 1 名改写 1 篇今日头条文案（标题/正文/标签）
  5. 报告存 data/media/reports/，并推送摘要+改写稿到个人微信（SCKEY 可选）

用法：python -m jobs.silver_media [--date YYYY-MM-DD] [--no-push|--push]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from server import wechat  # noqa: E402
from server.config import DATA_DIR, load_media_keywords  # noqa: E402
from server.llm import deepseek_json, llm_configured, LLMError  # noqa: E402

BJ_TZ = timezone(timedelta(hours=8))
HOT_URL = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

REPORT_DIR = DATA_DIR / "media" / "reports"
LAST_RUN_FILE = DATA_DIR / "media" / "silver_last_run.json"


def today_bj() -> str:
    return datetime.now(BJ_TZ).strftime("%Y-%m-%d")


def _save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_last():
    if LAST_RUN_FILE.exists():
        try:
            return json.loads(LAST_RUN_FILE.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


# ---------------- 采集 ----------------
def fetch_hot(keywords: list[str]) -> list[dict]:
    """今日头条热榜：关键词命中 → 真实条目（metric=热度，非点赞）。"""
    try:
        r = requests.get(HOT_URL, headers={"User-Agent": UA}, timeout=12)
        r.raise_for_status()
        data = (r.json().get("data") or [])
    except Exception:
        return []
    kws_low = [k.casefold() for k in keywords]
    out = []
    for it in data:
        title = str(it.get("Title") or "").strip()
        if not title:
            continue
        hit = [k for k in keywords if k.casefold() in title.casefold()]
        if not hit:
            continue
        url = str(it.get("Url") or "")
        if url.startswith("/"):
            url = "https://www.toutiao.com" + url
        out.append(
            {
                "title": title,
                "platform": "今日头条热榜",
                "metric_label": "热度",
                "metric": it.get("HotValue"),
                "like": None,
                "url": url,
                "sim": False,
                "keyword": hit[0],
            }
        )
    return out


def ai_fallback(need: int, keywords: list[str]) -> list[dict]:
    """AI 趋势模拟补齐（明确标注 sim=True，指标为模型预估）。"""
    kw = "、".join(keywords)
    out = deepseek_json(
        [
            {
                "role": "system",
                "content": "你是资深自媒体内容策划。请输出 JSON 对象，不要输出其它文字。",
            },
            {
                "role": "user",
                "content": (
                    f"围绕银发经济/康养方向（关键词：{kw}），请设计 {need + 2} 条近期最可能爆火的今日头条/小红书文案选题。"
                    '每条字段：{"platform": "今日头条或小红书", "keyword": "命中的关键词", "title": "完整标题", '
                    '"abstract": "一句话内容概要", "like": 点赞整数, "comment": 评论整数, "collect": 收藏整数, "share": 转发整数}'
                    '整体结构：{"candidates": [...]}。点赞区间 1.2万-18万，突出真实感，避免夸张离谱。'
                ),
            },
        ],
        temperature=1.0,
        max_tokens=2000,
    )
    cands = (out or {}).get("candidates") or []
    items = []
    for c in cands[: need + 4]:
        items.append(
            {
                "title": str(c.get("title", "")).strip(),
                "platform": str(c.get("platform", "今日头条")),
                "metric_label": "模拟点赞",
                "metric": None,
                "like": int(c.get("like") or 0),
                "comment": int(c.get("comment") or 0),
                "collect": int(c.get("collect") or 0),
                "share": int(c.get("share") or 0),
                "abstract": str(c.get("abstract", "")).strip(),
                "url": "",
                "sim": True,
                "keyword": str(c.get("keyword", "")),
            }
        )
    return [i for i in items if i["title"]]


# ---------------- LLM 分析与改写 ----------------
def analyze_top3(top3: list[dict]) -> list[dict]:
    payload = []
    for i, it in enumerate(top3, 1):
        payload.append(
            {
                "idx": i,
                "platform": it["platform"],
                "title": it["title"],
                "abstract": it.get("abstract", ""),
                "metric": (it.get("metric") if it["metric"] is not None else it.get("like")),
            }
        )
    out = deepseek_json(
        [
            {"role": "system", "content": "你是爆款文案拆解专家，只输出 JSON 对象。"},
            {
                "role": "user",
                "content": (
                    "请逐篇拆解下列 3 篇银发/康养爆款（输出与输入同序）。"
                    '每篇结构：{"idx":序号,"title_hooks":["2-3个标题亮点，各一句话"],'
                    '"core":["3-5句核心内容概括"],"framework":{"open":"开头手法一句话",'
                    '"body":"正文结构手法一句话","close":"结尾手法一句话"},'
                    '"angles":["3个不同的改写方向，各一句话"]}'
                    f'整体：{{"analyses":[...]}}。输入：{json.dumps(payload, ensure_ascii=False)}'
                ),
            },
        ],
        temperature=0.7,
        max_tokens=2600,
    )
    analyses = {a.get("idx"): a for a in (out or {}).get("analyses") or []}
    return [analyses.get(i, {}) for i in range(1, len(top3) + 1)]


def rewrite_best(item: dict) -> dict:
    out = deepseek_json(
        [
            {"role": "system", "content": "你是今日头条爆款文案作者，熟悉银发经济领域，只输出 JSON 对象。"},
            {
                "role": "user",
                "content": (
                    "基于下面的参考选题，原创改写一篇适合发布在今日头条的中文爆款文案。"
                    '要求：标题直击情绪/痛点（含数字或强对比更佳）；正文 700-1000 字，'
                    "首段 3 句内抓人，结构清晰有共鸣；结尾带互动引导；输出："
                    '{"title":"新标题","body":"完整正文（用\\n分段）","tags":["#银发经济","#康养"...]}'
                    f"参考选题：{json.dumps(item, ensure_ascii=False)}"
                ),
            },
        ],
        temperature=0.9,
        max_tokens=3200,
    )
    return {
        "title": str(out.get("title", "")).strip(),
        "body": str(out.get("body", "")).strip(),
        "tags": out.get("tags") or [],
    }


# ---------------- 报告与推送 ----------------
def metric_of(it: dict) -> str:
    if it["sim"]:
        return f"模拟点赞 {it.get('like')}"
    return f"热度 {it.get('metric') or '—'}"


def build_report(date_str: str, real: list, sim: list, top3: list, analyses: list, rewrite: dict) -> str:
    L = [
        f"# 🧓 银发康养 · 爆款拆解与改写日报（{date_str}）",
        "",
        f"> 关键词：{'、'.join(load_media_keywords('silver'))}",
        f"> 数据源：今日头条热榜命中 **{len(real)}** 条（真实热度）；不足部分由 AI 按近期趋势模拟 **{len(sim)}** 条补齐。",
        "> 说明：平台不公开精确点赞数，真实条目按热榜热度排序，模拟条目指标为模型预估（创作参考，勿当真实数据引用）。",
        "",
        "---",
        "",
        "## 一、Top 3 爆款分析",
        "",
    ]
    for i, it in enumerate(top3, 1):
        a = analyses[i - 1] if i - 1 < len(analyses) else {}
        src = "（AI 趋势模拟）" if it["sim"] else ""
        L.append(f"### 第 {i} 名 · 《{it['title']}》{src}")
        L.append(f"- 平台/来源：{it['platform']} · {metric_of(it)} · 关键词：{it.get('keyword', '')}")
        L.append(f"- 链接：{it['url'] or '（模拟选题无链接）'}")
        hooks = a.get("title_hooks") or []
        if hooks:
            L.append("")
            L.append("**① 提炼标题（亮点与吸睛关键词）**")
            L += [f"- {h}" for h in hooks]
        cores = a.get("core") or []
        if cores:
            L.append("")
            L.append("**② 梳理核心内容**")
            L += [f"{j}. {c}" for j, c in enumerate(cores, 1)]
        fw = a.get("framework") or {}
        if fw:
            L.append("")
            L.append("**③ 解析文案框架**")
            L += [f"- 开头：{fw.get('open', '—')}", f"- 正文：{fw.get('body', '—')}", f"- 结尾：{fw.get('close', '—')}"]
        angles = a.get("angles") or []
        if angles:
            L.append("")
            L.append("**④ 提供改写建议（3 个角度）**")
            L += [f"{j}. {x}" for j, x in enumerate(angles, 1)]
        L.append("")
        L.append("---")
        L.append("")
    L += ["## 二、改写文案（今日头条投稿用）", ""]
    if rewrite.get("title"):
        L.append(f"### 标题：{rewrite['title']}")
    if rewrite.get("tags"):
        L.append("")
        L.append(" ".join(rewrite.get("tags", [])))
    if rewrite.get("body"):
        L.append("")
        L.append(rewrite["body"])
    L.append("")
    return "\n".join(L)


def digest_md(date_str: str, top3: list, rewrite: dict, report_rel: str) -> str:
    L = [f"🧓 **银发康养爆款日报 · {date_str}**", ""]
    L.append("**今日 Top3（热度/模拟指标）**")
    for i, it in enumerate(top3, 1):
        mark = "（AI 模拟）" if it["sim"] else ""
        L.append(f"{i}. 《{it['title']}》{mark} · {metric_of(it)}")
    L.append("")
    L.append("**✍️ 改写文案标题**")
    L.append(f"> {rewrite.get('title') or '—'}")
    body = (rewrite.get("body") or "").replace("\n", " ")
    if len(body) > 420:
        body = body[:420] + "……"
    L.append("")
    L.append(f"> {body}")
    L.append("")
    L.append(f"完整四步拆解与全文见工作台「银发康养」页（{report_rel}）")
    return "\n".join(L)


# ---------------- 主流程 ----------------
def run_silver(date_str: str | None = None, push: bool | None = None) -> dict:
    if not llm_configured():
        raise LLMError("未配置 DEEPSEEK_API_KEY：请填写 server/.env 后重启，M4 需要大模型完成拆解与改写")
    d = date_str or today_bj()
    keywords = load_media_keywords("silver")

    real = fetch_hot(keywords)
    sim = []
    need = max(3 - len(real), 0)
    if need > 0:
        sim = ai_fallback(need, keywords)
    pool_real = sorted(real, key=lambda x: x.get("metric") or 0, reverse=True)
    pool_sim = sorted(sim, key=lambda x: x.get("like") or 0, reverse=True)
    top3 = (pool_real + pool_sim)[:3]
    if not top3:
        raise LLMError("未能获取任何候选（热榜无命中且模拟失败）")

    analyses = analyze_top3(top3)
    rewrite = rewrite_best(top3[0])

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report(d, real, sim, top3, analyses, rewrite)
    report_rel = f"data/media/reports/silver_{d}.md"
    (DATA_DIR / "media" / "reports" / f"silver_{d}.md").write_text(report, encoding="utf-8")

    push_result = None
    if push or (push is None and wechat.sc_configured()):
        push_result = wechat.send_markdown(
            f"🧓 银发康养爆款日报 · {d}",
            digest_md(d, top3, rewrite, report_rel),
        )

    top_summary = [{"title": it["title"], "platform": it["platform"], "sim": it["sim"], "metric": metric_of(it)} for it in top3]
    result = {
        "date": d,
        "real": len(real),
        "sim": len(sim),
        "top3": top_summary,
        "rewrite_title": rewrite.get("title"),
        "report_file": report_rel,
        "push": push_result,
    }
    _save_json(
        LAST_RUN_FILE,
        {"last_run": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"), **result},
    )
    return result


def main():
    ap = argparse.ArgumentParser(description="银发康养自媒体助手")
    ap.add_argument("--date", default=None)
    ap.add_argument("--push", action="store_true", default=None)
    ap.add_argument("--no-push", dest="push", action="store_false")
    args = ap.parse_args()
    result = run_silver(date_str=args.date, push=args.push)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
