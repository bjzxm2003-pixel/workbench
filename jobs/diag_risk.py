"""内容风控（Content Exists Risk / INVALID_REQUEST）诊断器。

用途：定位到底是哪一段文本、哪一条证据、哪一类文案触发了服务端内容审核。
做法：
  1. 离线重建出错时的真实请求体（复用 jobs.toutiao_copy 的提示词与缓存数据）
  2. 逐层探针：控制组 → 包装层 → 单条证据 → 单条主题成稿
  3. 二分法：对一段文本做二分，快速夹出敏感片段

用法：
  python -m jobs.diag_risk              # 完整诊断（会真实调用 API，消耗额度）
  python -m jobs.diag_risk --dry-run    # 只打印将发送的请求，不调用 API
  python -m jobs.diag_risk --only ev:silver
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from jobs.toutiao_copy import (  # noqa: E402
    GEN_CACHE,
    HEALTH_DISCLAIMER,
    TRACKS,
    _evidence_text,
    gather_evidence,
    topic_prompt,
)
from server.config import get_secret, load_media_keywords  # noqa: E402

BASE_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "media" / "diag"

SYS_TOPIC = "你是爆款选题策划专家，只输出 JSON 对象。"
SYS_WRITE = "你是今日头条{label}赛道爆款文案作者，只输出 JSON 对象。"


# ---------------- 探针执行 ----------------
def call(messages: list[dict], *, temperature: float = 0.8, max_tokens: int = 300,
         json_mode: bool = False) -> dict:
    key = get_secret("DEEPSEEK_API_KEY")
    if not key:
        return {"ok": False, "kind": "NOKEY", "status": 0, "text": "未配置 DEEPSEEK_API_KEY"}
    body = {"model": MODEL, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        r = requests.post(BASE_URL,
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"},
                          json=body, timeout=120)
    except requests.RequestException as e:
        return {"ok": False, "kind": "NETWORK", "status": 0, "text": f"{type(e).__name__}: {e}"}

    text = r.text
    if r.status_code == 200:
        try:
            content = r.json()["choices"][0]["message"]["content"]
            return {"ok": True, "kind": "OK", "status": 200, "text": content}
        except Exception:
            return {"ok": False, "kind": "PARSE", "status": 200, "text": text[:600]}
    if "Content Exists Risk" in text or "INVALID_REQUEST" in text:
        kind = "BLOCKED"
    else:
        kind = "ERROR"
    return {"ok": False, "kind": kind, "status": r.status_code, "text": text[:600]}


def run_probe(name: str, messages: list[dict], *, note: str = "", **kw) -> dict:
    t0 = time.time()
    res = call(messages, **kw)
    res.update({"name": name, "note": note, "secs": round(time.time() - t0, 1),
                "messages": messages})
    flag = "OK     " if res["ok"] else f"{res['kind']:<7}"
    print(f"[{flag}] {name:<34} {res['secs']:>5.1f}s  {res['text'][:90]!r}", flush=True)
    return res


def save(name: str, res: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    safe = name.replace("/", "_").replace(":", "-")
    (OUT_DIR / f"{safe}.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------- 证据池重建 ----------------
def load_pool() -> tuple[list[dict], list[dict]]:
    """取最近一次成功运行的真实证据池。"""
    if not GEN_CACHE.exists():
        raise SystemExit(f"缺少 {GEN_CACHE}，无法离线重建证据池")
    c = json.loads(GEN_CACHE.read_text(encoding="utf-8"))
    return c.get("hot_hits") or [], c.get("articles") or []


def evidence_lines(hot: list[dict], arts: list[dict], limit: int = 40) -> list[str]:
    return _evidence_text(hot + arts, limit).splitlines()


# ---------------- 二分定位 ----------------
def bisect_lines(lines: list[str], tag: str, *, wrapper, threshold: int = 1) -> list[str]:
    """对证据行做二分：返回所有被判定为触发的行。

    wrapper(sub_text) -> messages，负责把候选文本包进真实提示词。
    """
    bad: list[str] = []

    def probe(sub: list[str], label: str) -> bool:
        if not sub:
            return False
        sub_text = "\n".join(sub)
        res = run_probe(f"bisect/{tag}/{label}", wrapper(sub_text), note=f"{len(sub)} 行",
                        json_mode=True, max_tokens=200)
        save(f"bisect_{tag}_{label}", res)
        return res["kind"] == "BLOCKED"

    def rec(sub: list[str], path: str) -> None:
        if not sub:
            return
        if len(sub) <= threshold:
            if probe(sub, path):
                bad.extend(sub)
                print(f"    !! 触发片段已锁定：{sub}", flush=True)
            return
        if not probe(sub, path):          # 整段不触发 → 无需再分
            return
        mid = len(sub) // 2
        rec(sub[:mid], path + "L")
        rec(sub[mid:], path + "R")

    print(f"\n--- 二分定位（{tag}，共 {len(lines)} 行）---", flush=True)
    rec(lines, "root")
    return bad


# ---------------- 主流程 ----------------
def build_writers(pool_hot: list[dict], pool_art: list[dict]) -> dict:
    """重建四个真实的失败点请求：2 个选题轮 + 2 个成稿轮。"""
    ev = {}
    for track, cfg in TRACKS.items():
        hits = [a for a in pool_art if any(k.casefold() in a["title"].casefold()
                                          for k in cfg["kws"])]
        if not hits:
            hits = pool_art[:10]
        ev[track] = _evidence_text(pool_hot + hits)

    probes: dict[str, tuple[list[dict], dict]] = {}
    for track in TRACKS:
        probes[f"topic:{track}"] = (
            [{"role": "system", "content": SYS_TOPIC},
             {"role": "user", "content": topic_prompt(track, ev[track], 3)}],
            {"json_mode": True, "max_tokens": 2000, "temperature": 0.9},
        )

    cache = json.loads(GEN_CACHE.read_text(encoding="utf-8")) if GEN_CACHE.exists() else {}
    for track, topics in (cache.get("topics") or {}).items():
        cfg = TRACKS.get(track)
        if not cfg:
            continue
        for i, t in enumerate((topics or [])[:3], 1):
            health = track == "silver"
            extra = (
                "健康类内容必须有边界：不做诊断、不承诺疗效、不提具体药物剂量、不指导具体用药；"
                f"结尾固定加上这句提示：{HEALTH_DISCLAIMER}"
                if health else "可以引用经典原文，但引用要准确，不要杜撰出处。"
            )
            user = (
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
            )
            probes[f"write:{track}#{i}"] = (
                [{"role": "system", "content": SYS_WRITE.format(label=cfg["label"])},
                 {"role": "user", "content": user}],
                {"json_mode": True, "max_tokens": 600, "temperature": 0.95},
            )
    return probes


def main() -> int:
    ap = argparse.ArgumentParser(description="定位内容风控触发点")
    ap.add_argument("--dry-run", action="store_true", help="只打印请求，不调用 API")
    ap.add_argument("--only", default=None, help="只跑名称包含该子串的探针")
    ap.add_argument("--bisect", action="store_true", help="对证据行做二分定位（消耗较多额度）")
    ap.add_argument("--repro", action="store_true",
                    help="按真实链路抓取当天实时证据后再探测（复现真实失败）")
    args = ap.parse_args()

    if args.repro:
        print("=== 实时抓取证据（复现真实运行）===", flush=True)
        hot_hits, articles = gather_evidence(load_media_keywords("toutiao"))
        print(f"热榜命中 {len(hot_hits)} 条，文章核实 {len(articles)} 条", flush=True)
        for h in hot_hits:
            print(f"  HOT  {h['title']}")
        for a in articles:
            print(f"  ART  {a['title']}")
        pool_hot, pool_art = hot_hits, articles
    else:
        pool_hot, pool_art = load_pool()

    print(f"证据池：热榜 {len(pool_hot)} 条，文章 {len(pool_art)} 条")
    if not args.repro:
        for h in pool_hot:
            print(f"  HOT  {h['title']}")
        for a in pool_art:
            print(f"  ART  {a['title']}")

    probes = build_writers(pool_hot, pool_art)

    # 控制组：不含任何证据，验证 key/网络/模型本身是否正常
    control = [
        ("control/ping", [{"role": "user", "content": "回复两个字：正常"}],
         {"max_tokens": 20, "temperature": 0}),
        ("control/guoxue-system",
         [{"role": "system", "content": SYS_TOPIC}, {"role": "user", "content": "输出 {\"topics\":[]}"}],
         {"json_mode": True, "max_tokens": 50}),
        ("control/silver-system",
         [{"role": "system", "content": SYS_WRITE.format(label="银发康养")},
          {"role": "user", "content": "输出 {\"title\":\"测试\",\"body\":\"测试\"}"}],
         {"json_mode": True, "max_tokens": 50}),
    ]

    if args.dry_run:
        for n, m, kw in control:
            print(f"\n=== {n} ===\n{json.dumps(m, ensure_ascii=False)[:800]}")
        for n, (m, kw) in probes.items():
            print(f"\n=== {n} ===\n{json.dumps(m, ensure_ascii=False)[:1200]}")
        print(f"\n共 {len(control) + len(probes)} 个探针（dry-run 未调用 API）")
        return 0

    results = []
    for n, m, kw in control:
        # 控制组始终执行：没有它就无法区分「模型/网络问题」和「内容风控」
        r = run_probe(n, m, note="控制组", **kw)
        save(n, r)
        results.append(r)

    if args.repro:
        # 复现模式只跑「实时证据 → 选题轮」，成稿轮用当轮真实产出主题再跑
        for track in TRACKS:
            cfg = TRACKS[track]
            hits = [a for a in pool_art
                    if any(k.casefold() in a["title"].casefold() for k in cfg["kws"])]
            if not hits:
                hits = pool_art[:10]
            sub = _evidence_text(pool_hot + hits)
            msgs = [{"role": "system", "content": SYS_TOPIC},
                    {"role": "user", "content": topic_prompt(track, sub, 3)}]
            r = run_probe(f"live-topic:{track}", msgs, note="实时证据",
                          json_mode=True, max_tokens=500, temperature=0.9)
            save(f"live_topic_{track}", r)
            results.append(r)

            # 若选题轮通过，用真实产出的主题跑成稿轮（这一步最可能触发风控）
            if r["ok"]:
                try:
                    data = json.loads(r["text"])
                except Exception:
                    print(f"    （{track} 选题 JSON 解析失败，跳过成稿轮）", flush=True)
                    continue
                for i, t in enumerate((data.get("topics") or [])[:3], 1):
                    health = track == "silver"
                    extra = (
                        "健康类内容必须有边界：不做诊断、不承诺疗效、不提具体药物剂量、不指导具体用药；"
                        f"结尾固定加上这句提示：{HEALTH_DISCLAIMER}"
                        if health else "可以引用经典原文，但引用要准确，不要杜撰出处。"
                    )
                    user = (
                        "请基于下面的主题，原创一篇可直接发布在今日头条的中文纯文字文案（不要插图、不要分镜表）。\n"
                        f"主题标题：{t.get('title','')}\n核心思想：{t.get('core','')}\n切入角度：{t.get('angle','')}\n\n"
                        "要求：\n1. 正文 800-1100 字，首段 3 句内必须出现具体场景；\n"
                        "2. 口语化、有共鸣、多短句，段落之间用空行；\n"
                        "3. 结尾用一句提问引导评论互动；\n"
                        f"4. {extra}\n"
                        "5. **严禁编造任何事实**，包括：阅读量/点赞/评论/研究结论/百分比/统计数字；"
                        "也**不得虚构个人经历或他人案例**，不许假装有专家/医生/机构背书；\n"
                        "6. 标题可微调得更有吸引力，但必须保持 8-20 字。\n\n"
                        '输出 JSON：{"title":"最终标题","body":"完整正文（用\\n\\n分段）"}'
                    )
                    wm = [{"role": "system", "content": SYS_WRITE.format(label=cfg["label"])},
                          {"role": "user", "content": user}]
                    wr = run_probe(f"live-write:{track}#{i}", wm, note=t.get("title", ""),
                                   json_mode=True, max_tokens=700, temperature=0.95)
                    save(f"live_write_{track}_{i}", wr)
                    results.append(wr)
        blocked = [r["name"] for r in results if r["kind"] == "BLOCKED"]
        print("\n================ 复现结果 ================")
        for r in results:
            print(f"{r['kind']:<8} {r['name']:<28} {r['text'][:70]!r}")
        print(f"\n被拦截 {len(blocked)}/{len(results)}：{blocked}")
        print(f"明细已落盘：{OUT_DIR}")
        return 0 if not blocked else 1

    blocked_names = []
    for n, (m, kw) in probes.items():
        if args.only and args.only not in n:
            continue
        r = run_probe(n, m, note="重建失败点", **kw)
        save(n, r)
        results.append(r)
        if r["kind"] == "BLOCKED":
            blocked_names.append(n)

    if args.bisect and blocked_names:
        for track in TRACKS:
            cfg = TRACKS[track]
            hits = [a for a in pool_art
                    if any(k.casefold() in a["title"].casefold() for k in cfg["kws"])] or pool_art[:10]
            lines = evidence_lines(pool_hot, hits)

            def wrapper(sub_text: str, _track=track) -> list[dict]:
                return [{"role": "system", "content": SYS_TOPIC},
                        {"role": "user", "content": topic_prompt(_track, sub_text, 3)}]

            bad = bisect_lines(lines, track, wrapper=wrapper)
            if bad:
                print(f"\n>>> {track} 触发证据行：")
                for b in bad:
                    print(f"    {b}")

    # 汇总
    print("\n================ 汇总 ================")
    for r in results:
        print(f"{r['kind']:<8} {r['name']:<34} {r['text'][:80]!r}")
    blocked = [r["name"] for r in results if r["kind"] == "BLOCKED"]
    print(f"\n被拦截 {len(blocked)}/{len(results)}：{blocked}")
    print(f"明细已落盘：{OUT_DIR}")
    return 0 if not blocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
