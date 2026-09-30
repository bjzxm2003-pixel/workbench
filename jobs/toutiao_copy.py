"""⑥ 今日头条文案助手（M6 · 国学 × 银发康养）

每日 23:00（北京，GH Actions cron: '0 15 * * *'）或手动：
  1. 真实数据：抓今日头条热榜（真实热度值），按「钱 / 健康」痛点词过滤出可关联条目
  2. 证据核实：对候选文章 URL 抓取页面，提取**真实标题 + 发布时间**（用于"近24-48小时"判断）
  3. LLM 提炼：国学 3 条 + 银发康养 3 条爆款主题（标题/核心思想/爆款理由/切入角度）
  4. LLM 成稿：国学 3 篇 + 康养 3 篇今日头条纯文字文案（不插图）
  5. 落盘：报告 data/media/reports/toutiao_copy_<date>.md + 数据底表 toutiao_data_<date>.csv
  6. 推送：6 条标题 + 报告路径到微信（SCKEY 可选）

**数据诚信约束（与 M4/M5 的"模拟指标"做法不同，本助手一律不造互动量）**：
  - 平台不公开阅读/点赞/评论/收藏/转发，本助手**从不输出任何互动量数字**
  - 热榜条目只有真实热度值；文章条目只有"标题 + 发布时间"是硬证据
  - 拿不到热榜/证据时，明说局限，但**至少仍产出 1 条主题**，不伪造数据

轻资产约束：提示词显式禁止养老院/养老地产/养老理财/大额加盟/保健品囤货等重资产选题。

可选：配置 TOUTIAO_SEARCH_API（SearchApi/Tavily 风格）可自动发现更多近期文章；
      或在 data/media/toutiao_candidates.txt 每行写一个头条文章链接，任务会逐个核实标题与时间。

用法：python -m jobs.toutiao_copy [--date YYYY-MM-DD] [--no-push|--push]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from server import wechat  # noqa: E402
from server.config import DATA_DIR, load_media_keywords  # noqa: E402
from server.llm import deepseek_json, llm_configured, LLMBlocked, LLMError  # noqa: E402

BJ_TZ = timezone(timedelta(hours=8))
HOT_URL = "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
UA_PC = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)

REPORT_DIR = DATA_DIR / "media" / "reports"
LAST_RUN_FILE = DATA_DIR / "media" / "toutiao_last_run.json"
CANDIDATE_FILE = DATA_DIR / "media" / "toutiao_candidates.txt"
GEN_CACHE = DATA_DIR / "media" / ".toutiao_gen_cache.json"

# 两个赛道从同一份证据池里各取所需
TRACKS = {
    "guoxue": {
        "label": "国学",
        "kws": ["国学", "易经", "道德经", "黄帝内经", "论语", "人生智慧", "传统文化", "历史"],
        "focus": (
            "「普通人如何变富有、如何翻身、如何不焦虑」等现实痛点，用国学/传统文化做内容载体。"
            "可用素材：范蠡商道（三聚三散、贵出如粪土）、史记·货殖列传（无财作力/少有斗智/既饶争时）、"
            "《大学》生财有大道、《荀子·劝学》善假于物、孔子重信、王阳明心学知行合一、寒门逆袭典故"
        ),
    },
    "silver": {
        "label": "银发康养",
        "kws": ["银发", "康养", "养老", "老龄", "适老", "养生", "中医", "药食同源", "男性健康", "抗衰"],
        "focus": (
            "药食同源、男性健康、抗老抗衰、智慧养老等方向。"
            "可用素材：《黄帝内经》（上古天真论、四气调神）、《伤寒杂病论》的调养思路、"
            "节气食养、居家适老小物、轻服务"
        ),
    },
}

HEALTH_DISCLAIMER = "（本文为健康科普，不替代诊疗。如有不适，请及时到正规医疗机构就诊。）"

# 被内容风控拦截的条目（不中断整轮，如实记录并写进报告）
BLOCKED: list[dict] = []


def _record_block(stage: str, track: str, e: LLMError, *, label: str = "") -> None:
    BLOCKED.append(
        {
            "stage": stage,
            "track": track,
            "label": label,
            "request_id": getattr(e, "request_id", ""),
            "log_file": getattr(e, "log_file", ""),
            "detail": str(e)[:200],
            "at": datetime.now(BJ_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    print(f"[warn] {track} {stage} 被内容风控拦截（已跳过，继续跑其余条目）：{str(e)[:160]}", file=sys.stderr)

# 相对时间 → 小时数（用于判断是否落在 24-48h 窗口）
REL_UNITS = {"分钟": 1 / 60, "小时": 1, "天": 24, "周": 24 * 7, "个月": 24 * 30, "年": 24 * 365}


def today_bj() -> str:
    return datetime.now(BJ_TZ).strftime("%Y-%m-%d")


def _save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def fmt_hot(value) -> str:
    """热榜 HotValue 有时是字符串，统一安全格式化（不编造、不报错）。"""
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value or "—")


def _rel_hours(text: str) -> float | None:
    """'16小时前' / '2天前' / '刚刚' → 小时数；无法解析返回 None。"""
    t = str(text or "").strip()
    if not t:
        return None
    if "刚刚" in t:
        return 0.0
    m = re.search(r"(\d+)\s*(分钟|小时|天|周|个月|年)前", t)
    if not m:
        return None
    return int(m.group(1)) * REL_UNITS.get(m.group(2), 0.0)


TITLE_MIN, TITLE_MAX = 8, 20


def title_width(s: str) -> int:
    """标题长度：CJK/全角按 1 计，ASCII 按 0.5 计（贴近平台字数口径）。"""
    w = 0.0
    for ch in str(s or "").strip():
        w += 1.0 if ord(ch) > 0x2E80 else 0.5
    return int(w + 0.5)


def fit_title(title: str, fallback: str = "") -> str:
    """确保标题落在 8-20 字：超长先按标点取第一个分句，仍超长则硬截断。"""
    t = str(title or "").strip().rstrip("｜|")
    if not t:
        t = str(fallback or "").strip()
    if title_width(t) > TITLE_MAX:
        parts = [p for p in re.split(r"[，,。！!？?；;、]", t) if p.strip()]
        # 取「不超过上限的最大前缀分句组合」
        acc = ""
        for p in parts:
            cand = acc + p
            if acc and title_width(cand + "？") > TITLE_MAX:
                break
            if title_width(cand) > TITLE_MAX:
                break
            acc = cand
        t = acc or t
    if title_width(t) > TITLE_MAX:
        t = t[:TITLE_MAX]
    if title_width(t) < TITLE_MIN and fallback and title_width(fallback) >= TITLE_MIN:
        t = str(fallback).strip()
    return t.strip()


# ---------------- 一、真实热榜 ----------------
def fetch_hot() -> list[dict]:
    """今日头条热榜：真实热度值（HotValue），非互动量。"""
    try:
        r = requests.get(HOT_URL, headers={"User-Agent": UA_PC}, timeout=15)
        r.raise_for_status()
        return r.json().get("data") or []
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 热榜抓取失败：{e}", file=sys.stderr)
        return []


def hit_keywords(title: str, keywords: list[str]) -> list[str]:
    return [k for k in keywords if k.casefold() in title.casefold()]


def collect_hot_items(hot: list[dict], keywords: list[str]) -> list[dict]:
    """把热榜条目转成证据条目（只保留命中痛点词的）。"""
    out = []
    for it in hot:
        title = str(it.get("Title") or "").strip()
        if not title:
            continue
        hit = hit_keywords(title, keywords)
        if not hit:
            continue
        url = str(it.get("Url") or "")
        if url.startswith("/"):
            url = "https://www.toutiao.com" + url
        # 热榜链接带大量埋点参数，截断到 ? 之前，报告/CSV 更干净
        url = url.split("?", 1)[0]
        out.append(
            {
                "kind": "hot",
                "title": title,
                "hot": it.get("HotValue"),
                "label": it.get("Label") or "",
                "keyword": hit[0],
                "url": url,
                "pub_rel": "今日实时",
                "pub_hours": 0.0,
                "author": "",
                "verified": True,
                "note": "今日头条热榜真实热度值",
            }
        )
    return sorted(out, key=lambda x: x.get("hot") or 0, reverse=True)


# ---------------- 二、文章证据核实 ----------------
def parse_article(url: str) -> dict | None:
    """抓取头条文章页，提取真实标题 + 发布时间（JS 渲染页只有这两项可核）。

    两个必须的取数细节（都已实测验证）：
      1. www.toutiao.com 对 requests 返回混淆 JS（无正文、无 title）；
         m.toutiao.com 返回真实 HTML —— 所以统一改写到 m 域。
      2. 页面声明 ISO-8859-1 但实际 UTF-8，不强制 encoding 会中文乱码致正则全失配。
    """
    m = re.search(r"toutiao\.com/((?:article|w|video)/\d+)", url)
    aid = re.search(r"/(\d+)", m.group(1)).group(1) if m else ""
    fetch_url = f"https://m.toutiao.com/{m.group(1)}/" if m else url
    try:
        resp = requests.get(fetch_url, headers={"User-Agent": UA_MOBILE}, timeout=20)
        resp.encoding = "utf-8"
        html = resp.text
    except Exception as e:  # noqa: BLE001
        print(f"[warn] 文章抓取失败 {url}: {e}", file=sys.stderr)
        return None
    if not html:
        return None
    ti = re.findall(r"<title>(.*?)</title>", html, re.S)
    title = ""
    if ti:
        import html as _html

        title = _html.unescape(ti[0]).replace(" - 今日头条", "").strip()
        # 微头条（/w/）的 <title> 会把正文一起带进来，只取首行作为标题
        title = title.split("\n")[0].strip()
    if not title or title in {"今日头条", "404 Not Found"}:
        return None

    body = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.S)
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))

    rel_m = re.search(r"(刚刚|\d+\s*(?:分钟|小时|天|周|个月|年)前)", txt)
    abs_m = re.search(r"(\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2})", txt)
    pub_rel = rel_m.group(1) if rel_m else (abs_m.group(1) if abs_m else "未能核实")
    hours = _rel_hours(pub_rel)
    if hours is None and abs_m:
        try:
            dt = datetime.strptime(abs_m.group(1), "%Y-%m-%d %H:%M").replace(tzinfo=BJ_TZ)
            hours = (datetime.now(BJ_TZ) - dt).total_seconds() / 3600
        except ValueError:
            hours = None

    author_m = re.search(r"打开APP APP内打开 (.{2,30}?) 关注", txt)
    return {
        "kind": "article",
        "id": aid,
        "title": title,
        "url": url,
        "pub_rel": pub_rel,
        "pub_hours": hours,
        "author": author_m.group(1).strip() if author_m else "",
        "hot": None,
        "label": "",
        "keyword": "",
        "verified": True,
        "note": "标题与发布时间已核实；互动量不可得",
    }


def candidate_urls() -> list[str]:
    """候选文章链接：本地清单文件 + 可选搜索 API。"""
    urls: list[str] = []
    if CANDIDATE_FILE.exists():
        for line in CANDIDATE_FILE.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "toutiao.com" in s:
                urls.append(s)
    urls += _search_api_urls()
    # 去重保序
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _search_api_urls() -> list[str]:
    """可选：TOUTIAO_SEARCH_API 返回 {organic_results|results:[{link|url}]} 时抽取链接。"""
    api = os.environ.get("TOUTIAO_SEARCH_API", "").strip()
    if not api:
        return []
    queries = ["今日头条 国学 普通人 翻身 财富", "今日头条 银发康养 养生 男性健康"]
    out: list[str] = []
    for q in queries:
        try:
            r = requests.get(api, params={"q": q}, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as e:  # noqa: BLE001
            print(f"[warn] 搜索 API 调用失败：{e}", file=sys.stderr)
            continue
        items = data.get("organic_results") or data.get("results") or []
        for it in items:
            link = str(it.get("link") or it.get("url") or "")
            if "toutiao.com" in link:
                out.append(link)
    return out


def gather_evidence(hot_kws: list[str], max_articles: int = 12) -> tuple[list[dict], list[dict]]:
    """返回 (热榜证据, 文章证据)。"""
    hot_hits = collect_hot_items(fetch_hot(), hot_kws)
    articles: list[dict] = []
    seen_titles = {h["title"] for h in hot_hits}
    for url in candidate_urls()[: max_articles * 2]:
        if len(articles) >= max_articles:
            break
        item = parse_article(url)
        if item and item["title"] not in seen_titles:
            seen_titles.add(item["title"])
            articles.append(item)
    articles.sort(key=lambda x: (x.get("pub_hours") is None, x.get("pub_hours") or 0))
    return hot_hits, articles


def recent_window(articles: list[dict], hours: int = 48) -> list[dict]:
    return [a for a in articles if a.get("pub_hours") is not None and a["pub_hours"] <= hours]


# ---------------- 三、LLM：主题与文案 ----------------
def topic_prompt(track: str, evidence: str, n: int) -> str:
    cfg = TRACKS[track]
    if track == "guoxue":
        scope = (
            "本赛道只做三件事：赚钱、翻身、破焦虑。\n"
            "**不要**写健康/疾病/养生类主题（那是另一个赛道的内容）。\n"
        )
    else:
        scope = (
            "本赛道写：药食同源、男性健康、抗老抗衰、智慧养老。\n"
            "**不要**写财富/股票/房贷类主题（那是另一个赛道的内容）。\n"
        )
    return (
        f"你是今日头条资深内容策划，深耕{cfg['label']}赛道。\n"
        f"赛道方向：{cfg['focus']}\n"
        f"{scope}\n"
        f"以下是今天真实抓取到的证据（热榜条目含真实热度值；文章条目含真实标题与发布时间）：\n{evidence}\n\n"
        f"请为「{cfg['label']}」赛道提炼 {n} 条爆款主题。\n"
        "硬性约束：\n"
        f"1. 标题 8-20 个字，口语化、有痛点、能让人想点开；\n"
        "2. 必须扎根**长期存在的现实痛点**，经典只做载体，不要空谈经典；\n"
        "3. 热榜是**趋势信号**，不是选题本身：不要围绕当天政策/行情/单条热点造题，\n"
        "   也不得复述任何政策条款、金额、点位、涨幅等易失真细节；\n"
        "4. 绝对不要编造任何事实：阅读量/点赞/评论/互动量/研究结论/统计数字一律不得出现；\n"
        "5. 轻资产方向：严**禁**养老院/养老地产/床位/养老理财/大额加盟/保健品囤货等重资产或投资类选题；\n"
        "6. 不要照抄证据里的标题，要重新组合角度。\n\n"
        "输出 JSON：{\"topics\":[{\"title\":\"主题标题\",\"core\":\"核心思想，2-4句\","
        "\"why\":\"爆款理由，2-3句\",\"angle\":\"建议切入角度，1-2句\"}]}"
    )


def extract_topics(tracks: list[str], evidence_by_track: dict, n: int = 3) -> dict:
    out: dict[str, list] = {}
    for track in tracks:
        try:
            data = deepseek_json(
                [
                    {"role": "system", "content": "你是爆款选题策划专家，只输出 JSON 对象。"},
                    {"role": "user", "content": topic_prompt(track, evidence_by_track[track], n)},
                ],
                temperature=0.9,
                max_tokens=2000,
            )
        except LLMBlocked as e:
            _record_block("主题提炼", track, e)
            data = {}
        except LLMError as e:
            print(f"[warn] {track} 主题提炼失败：{e}", file=sys.stderr)
            data = {}
        topics = []
        for t in (data or {}).get("topics") or []:
            title = str(t.get("title", "")).strip()
            if not title:
                continue
            topics.append(
                {
                    "title": fit_title(title),
                    "core": str(t.get("core", "")).strip(),
                    "why": str(t.get("why", "")).strip(),
                    "angle": str(t.get("angle", "")).strip(),
                }
            )
        out[track] = topics[:n]
    return out


def write_articles(track: str, topics: list[dict], n: int = 3) -> list[dict]:
    """每个主题各写 1 篇今日头条纯文字文案。"""
    cfg = TRACKS[track]
    health = track == "silver"
    arts: list[dict] = []
    for i, t in enumerate(topics[:n], 1):
        extra = (
            "健康类内容必须有边界：不做诊断、不承诺疗效、不提具体药物剂量、不指导具体用药；"
            f"结尾固定加上这句提示：{HEALTH_DISCLAIMER}"
            if health
            else "可以引用经典原文，但引用要准确，不要杜撰出处。"
        )
        try:
            out = deepseek_json(
                [
                    {"role": "system", "content": f"你是今日头条{cfg['label']}赛道爆款文案作者，只输出 JSON 对象。"},
                    {
                        "role": "user",
                        "content": (
                            "请基于下面的主题，原创一篇可直接发布在今日头条的中文纯文字文案（不要插图、不要分镜表）。\n"
                            f"主题标题：{t['title']}\n核心思想：{t['core']}\n切入角度：{t['angle']}\n\n"
                            "要求：\n"
                            "1. 正文 800-1100 字，首段 3 句内必须出现具体场景；\n"
                            "2. 口语化、有共鸣、多短句，段落之间用空行；\n"
                            "3. 结尾用一句提问引导评论互动；\n"
                            f"4. {extra}\n"
                            "5. **严禁编造任何事实**，包括：阅读量/点赞/评论/研究结论/百分比/统计数字；"
                            "也**不得虚构个人经历或他人案例**（不许写「我身边一个老哥」「有个朋友」「前几天遇到一位」这类"
                            "看起来很真实的假故事），不许假装有专家/医生/机构背书；\n"
                            "   需要举例时，用「很多人都有过这种感觉」「你可以想想自己」这类**不冒充具体事实**的写法；\n"
                            "6. 标题可微调得更有吸引力，但必须保持 8-20 字。\n\n"
                            '输出 JSON：{"title":"最终标题","body":"完整正文（用\\n\\n分段）"}'
                        ),
                    },
                ],
                temperature=0.95,
                max_tokens=4000,
            )
        except LLMBlocked as e:
            _record_block("成稿", track, e, label=t.get("title", ""))
            continue
        except LLMError as e:
            print(f"[warn] {track} 第{i}篇成稿失败：{e}", file=sys.stderr)
            continue
        body = str(out.get("body", "")).strip()
        title = fit_title(str(out.get("title", "")), fallback=t["title"])
        if not body:
            continue
        if health and "不替代诊疗" not in body:
            body = body + "\n\n*" + HEALTH_DISCLAIMER + "*"
        arts.append({"title": title, "body": body, "from_topic": t["title"]})
    return arts


# ---------------- 四、报告与落盘 ----------------
def _evidence_text(items: list[dict], limit: int = 40) -> str:
    lines = []
    for it in items[:limit]:
        if it["kind"] == "hot":
            lines.append(f"- [热榜|真实热度 {it['hot']}] {it['title']}")
        else:
            lines.append(f"- [文章|{it['pub_rel']}] {it['title']}  {it['url']}")
    return "\n".join(lines) if lines else "（今日无可核实证据）"


def build_report(
    date_str: str,
    hot_hits: list[dict],
    articles: list[dict],
    topics: dict,
    articles_out: dict,
    run_at: str | None = None,
) -> str:
    recent = recent_window(articles)
    run_at = run_at or datetime.now(BJ_TZ).strftime("%Y-%m-%d %H:%M")
    L = [
        f"# 今日头条文案包｜国学 × 银发康养（{date_str}）",
        "",
        "> 本报告由「今日头条文案助手」每日 23:00 自动生成。",
        f"> **实际生成时间：{run_at}（北京）**。任务在北京时间 23:00 运行，跨零点后 `date` 归属自然日次一日，",
        "> 因此报告日期可能比实际运行日晚一天——**热榜与发布时间以抓取时刻为准**。",
        f"> 数据源：今日头条热榜实时抓取（真实热度值）；文章条目为页面核实的真实标题 + 发布时间。",
        "> **数据诚信声明：平台不公开阅读/点赞/评论/收藏/转发，本报告从不输出任何互动量数字。**",
        "",
        "---",
        "",
        "## 〇、数据核实情况",
        "",
        f"- 热榜命中痛点词条目：**{len(hot_hits)}** 条（真实热度值）",
        f"- 已核实文章条目：**{len(articles)}** 条（标题 + 发布时间已核）",
        f"- 其中落在 24-48 小时窗口内：**{len(recent)}** 条",
        "",
    ]
    if BLOCKED:
        L += [
            f"> ⚠️ **本次有 {len(BLOCKED)} 个条目被模型服务方内容风控拦截**（`Content Exists Risk`），",
            "> 已按要求跳过并继续生成其余条目。被拦请求的完整原文已落盘至 `data/media/blocked/`，",
            "> 可在新会话中据此二分定位触发片段；被拦条目不冒充已生成内容。",
            "",
            "| 阶段 | 赛道 | 条目 | request_id |",
            "|---|---|---|---|",
        ]
        L += [
            f"| {b['stage']} | {b['track']} | {b.get('label') or '（整轮）'} | "
            f"{b.get('request_id') or '未返回'} |"
            for b in BLOCKED
        ]
        L.append("")
    if hot_hits:
        L += ["### 1. 今日热榜命中（真实热度值）", "", "| 热榜标题 | 热度值 |", "|---|---|"]
        L += [f"| {it['title']} | {fmt_hot(it['hot'])} |" for it in hot_hits[:20]]
        L.append("")
    else:
        L += ["> ⚠️ 今日热榜未命中任何痛点词（或抓取失败）。**局限说明**：热榜是实时变动的，", "> 国学/康养并非每日都有热点上榜，本报告主题将更多依赖文章证据与经典母题推演。", ""]

    if articles:
        L += ["### 2. 已核实文章（真实标题 + 发布时间）", ""]
        if recent:
            L += [f"**A. 24-48 小时窗口内（{len(recent)} 条）**", "", "| 标题 | 发布时间 | 链接 |", "|---|---|---|"]
            L += [f"| {a['title']} | {a['pub_rel']} | {clean_url(a['url'])} |" for a in recent]
            L.append("")
        older = [a for a in articles if a not in recent]
        if older:
            L += ["**B. 更早条目（供母题参考）**", "", "| 标题 | 发布时间 | 链接 |", "|---|---|---|"]
            L += [f"| {a['title']} | {a['pub_rel']} | {clean_url(a['url'])} |" for a in older[:15]]
            L.append("")
    else:
        L += ["> ⚠️ 未配置搜索 API 且候选清单为空，今日无文章级证据。",
              "> 可设置 `TOUTIAO_SEARCH_API`，或在 `data/media/toutiao_candidates.txt` 每行写一个头条链接。", ""]

    L += [
        "### 3. 数据可信度声明（必读）",
        "",
        "1. **互动量未能核实**：头条文章页为 JS 渲染，源码不含阅读/点赞/评论/收藏/转发计数；",
        "   公开搜索接口返回 `count: 0`（反爬）。因此本报告**不提供任何互动量数字**。",
        "2. 热榜的 `热度值` 是平台公开的真实指标，但它**不是**阅读/点赞量，两者不可混用。",
        "3. 标题与发布时间来自真实页面抓取，可复现；**排序为运营判断，不是平台官方榜单**。",
        "4. 小红书未直连（需登录、无公开接口），本报告不含小红书数据。",
        "",
        "---",
        "",
    ]

    for track in ("guoxue", "silver"):
        label = TRACKS[track]["label"]
        L += [f"## 一、{label}赛道 · 爆款主题" if track == "guoxue" else f"## 二、{label}赛道 · 爆款主题", ""]
        tps = topics.get(track) or []
        if not tps:
            L += ["> ⚠️ 本次未能提炼出主题（LLM 调用失败），请查看运行日志。", ""]
        for i, t in enumerate(tps, 1):
            L += [
                f"### 主题 {i}",
                f"- **标题（{len(t['title'])}字）**：{t['title']}",
                f"- **核心思想**：{t['core']}",
                f"- **爆款理由**：{t['why']}",
                f"- **建议切入角度**：{t['angle']}",
                "",
            ]
        L += ["---", ""]

    L += ["## 三、今日头条文案正文", ""]
    for track, sec in (("guoxue", "国学赛道"), ("silver", "银发康养赛道")):
        L += [f"### {sec}", ""]
        arts = articles_out.get(track) or []
        if not arts:
            L += ["> ⚠️ 本次未能生成文案（LLM 调用失败），请查看运行日志。", ""]
        for i, a in enumerate(arts, 1):
            L += [f"#### 文案 {i}｜{a['title']}", "", a["body"], "", "---", ""]

    L += [
        "## 四、发布前检查清单",
        "",
        "1. 文中是否出现任何互动量数字？（出现即删）",
        "2. 健康类是否保留文末就医提示？",
        "3. 是否出现养老投资/加盟/理财/保健品囤货引导？（出现即删）",
        "4. 标题是否有一句能让人「想反驳」或「想代入」？",
        "",
        f"*本文件由「今日头条文案助手」生成于 {run_at}（北京）。*",
    ]
    return "\n".join(L)


def clean_url(url: str) -> str:
    """去掉头条链接的埋点查询参数（干净、可点、便于 CSV 阅读）。"""
    return str(url or "").split("?", 1)[0]


def write_csv(path: Path, hot_hits: list[dict], articles: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["核实时间", "来源", "标题原文", "热度值", "发布时间", "数据状态", "链接"])
        for it in hot_hits:
            w.writerow(["", "今日头条热榜", it["title"], it["hot"], "今日实时", "热度值为真实数据", clean_url(it["url"])])
        for a in articles:
            w.writerow(["", "今日头条文章", a["title"], "", a["pub_rel"], "标题与发布时间已核实；互动量未能核实", clean_url(a["url"])])


def digest_md(date_str: str, topics: dict, articles_out: dict, report_rel: str) -> str:
    L = [f"📰 **今日头条文案包 · {date_str}**", ""]
    for track in ("guoxue", "silver"):
        label = TRACKS[track]["label"]
        L.append(f"**【{label}】6 条中的 3 条主题**")
        for i, t in enumerate((topics.get(track) or [])[:3], 1):
            L.append(f"{i}. {t['title']}")
        arts = articles_out.get(track) or []
        for i, a in enumerate(arts[:3], 1):
            L.append(f"   ✍️ 文案{i}：{a['title']}")
        L.append("")
    L.append(f"完整正文见：`{report_rel}`")
    L.append("（本任务不输出任何互动量数字：平台不公开）")
    return "\n".join(L)


# ---------------- 主流程 ----------------
def run_toutiao(date_str: str | None = None, push: bool | None = None, from_cache: bool = False) -> dict:
    d = date_str or today_bj()
    run_at = datetime.now(BJ_TZ).strftime("%Y-%m-%d %H:%M")

    if from_cache and GEN_CACHE.exists():
        # 只重渲染报告，不重新调用 LLM（用于修文案格式/模板时复用已有生成结果）
        cached = json.loads(GEN_CACHE.read_text(encoding="utf-8"))
        if date_str is None or cached.get("date") == d:
            d = cached.get("date") or d
            run_at = cached.get("run_at") or run_at
            hot_hits = cached.get("hot_hits") or []
            articles = cached.get("articles") or []
            topics = {k: [t for t in (v or [])] for k, v in (cached.get("topics") or {}).items()}
            articles_out = cached.get("articles_out") or {}
            # 恢复被拦条目，保证重渲染报告时风控提示不丢失（幂等）
            BLOCKED.clear()
            BLOCKED.extend(cached.get("blocked") or [])
            # 缓存里存的是 LLM 原始输出，重渲染时补做标题规范化（幂等）
            for tps in topics.values():
                for t in tps:
                    t["title"] = fit_title(t.get("title", ""))
            for arts in articles_out.values():
                for a in arts:
                    a["title"] = fit_title(a.get("title", ""), fallback=a.get("from_topic", ""))
            print(f"[info] 复用缓存 {GEN_CACHE.name}（不调用 LLM）")
        else:
            from_cache = False

    if not from_cache:
        if not llm_configured():
            raise LLMError("未配置 DEEPSEEK_API_KEY：请在 server/.env 或 GitHub Secrets 中填写")
        BLOCKED.clear()  # 同一进程内可能多次调用，避免跨轮累积

        hot_kws = load_media_keywords("toutiao")
        hot_hits, articles = gather_evidence(hot_kws)
        recent = recent_window(articles)
        print(f"[info] 热榜命中 {len(hot_hits)} 条；文章核实 {len(articles)} 条（24-48h: {len(recent)}）")

        # 两个赛道共用证据池，但各自挑与自身相关的部分
        evidence_by_track = {}
        for track, cfg in TRACKS.items():
            pool = [a for a in articles if hit_keywords(a["title"], cfg["kws"])]
            if not pool:
                pool = articles[:10]  # 证据少时给全量，让模型自行判断相关性
            evidence_by_track[track] = _evidence_text(hot_hits + pool)

        topics = extract_topics(list(TRACKS), evidence_by_track, 3)
        articles_out = {}
        for track in TRACKS:
            tps = topics.get(track) or []
            if not tps:
                continue
            articles_out[track] = write_articles(track, tps, 3)

        total_topics = sum(len(v or []) for v in topics.values())
        total_arts = sum(len(v or []) for v in articles_out.values())
        if total_topics == 0 and total_arts == 0:
            if BLOCKED:
                raise LLMError(
                    f"全部 {len(BLOCKED)} 个条目均被内容风控拦截（Content Exists Risk）。"
                    "被拦请求已落盘 data/media/blocked/，请在新会话中二分定位，"
                    "或设置 DEEPSEEK_BASE_URL / DEEPSEEK_MODEL 切换模型供应商重试。"
                )
            raise LLMError("主题与文案均生成失败，请检查 DEEPSEEK_API_KEY 与网络")

        # 先落盘生成结果：报告渲染出错时不至于浪费已消耗的 LLM 调用
        _save_json(
            GEN_CACHE,
            {
                "date": d,
                "run_at": run_at,
                "hot_hits": hot_hits,
                "articles": articles,
                "topics": topics,
                "articles_out": articles_out,
                "blocked": BLOCKED,
            },
        )

    recent = recent_window(articles)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = build_report(d, hot_hits, articles, topics, articles_out, run_at)
    report_rel = f"data/media/reports/toutiao_copy_{d}.md"
    (REPORT_DIR / f"toutiao_copy_{d}.md").write_text(report, encoding="utf-8")
    csv_rel = f"data/media/reports/toutiao_data_{d}.csv"
    write_csv(REPORT_DIR / f"toutiao_data_{d}.csv", hot_hits, articles)

    push_result = None
    if push or (push is None and wechat.sc_configured()):
        push_result = wechat.send_markdown(
            f"📰 今日头条文案包 · {d}",
            digest_md(d, topics, articles_out, report_rel),
        )

    result = {
        "date": d,
        "hot_hits": len(hot_hits),
        "articles_verified": len(articles),
        "recent_48h": len(recent),
        "topics": {k: [t["title"] for t in (v or [])] for k, v in topics.items()},
        "article_titles": {k: [a["title"] for a in (v or [])] for k, v in articles_out.items()},
        "report_file": report_rel,
        "csv_file": csv_rel,
        "push": push_result,
        "blocked": len(BLOCKED),
        "blocked_items": BLOCKED,
        "note": "本任务不输出互动量：平台不公开",
    }
    _save_json(
        LAST_RUN_FILE,
        {"last_run": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"), **result},
    )
    return result


def main():
    ap = argparse.ArgumentParser(description="今日头条文案助手（国学 × 银发康养）")
    ap.add_argument("--date", default=None, help="覆盖日期 YYYY-MM-DD")
    ap.add_argument("--push", action="store_true", default=None)
    ap.add_argument("--no-push", dest="push", action="store_false")
    ap.add_argument(
        "--from-cache",
        action="store_true",
        help="复用上次生成结果只重渲染报告（不调用 LLM，用于改模板/修格式）",
    )
    args = ap.parse_args()
    result = run_toutiao(date_str=args.date, push=args.push, from_cache=args.from_cache)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
