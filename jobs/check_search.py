"""搜索 API 本地预检：在把 key 填进 GitHub Secrets 之前，先确认它真的能用。

用法：
  TOUTIAO_SEARCH_API='tvly-xxxx' python -m jobs.check_search
  python -m jobs.check_search 'tvly-xxxx'          # 也可直接当参数传
  python -m jobs.check_search                      # 不带 key：只打印配置指引

会依次检查：
  1. 写法识别（裸 key / 带 key 的 URL / 普通 endpoint）
  2. 真实调用搜索接口（2 个查询），打印响应结构与抽到的链接
  3. 对返回的头条链接逐条走 parse_article 回源核实（确认不是死链）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobs.toutiao_copy import _resolve_search_api, _search_api_urls, parse_article  # noqa: E402

GUIDE = """
未检测到搜索 API 配置。接入 Tavily 的步骤：

1. 注册并取 key：https://app.tavily.com  →  API Keys  →  复制（形如 tvly-xxxxxxxx）

2. 本地先预检（推荐，避免填错 key 白等一次定时任务）：
     TOUTIAO_SEARCH_API='tvly-你的key' python -m jobs.check_search

3. 预检通过后填进 GitHub Secrets：
     仓库 Settings → Secrets and variables → Actions → New repository secret
     Name:   TOUTIAO_SEARCH_API
     Secret: tvly-你的key            （只填 key 即可；也可填
                                      https://api.tavily.com/search?api_key=tvly-你的key）

4. 之后每天 23:00 的定时运行会自动发现新链接，无需再手工维护
   data/media/toutiao_candidates.txt
"""


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    api = (arg or os.environ.get("TOUTIAO_SEARCH_API", "")).strip()
    if not api:
        print(GUIDE)
        return 0

    os.environ["TOUTIAO_SEARCH_API"] = api
    masked = api if len(api) <= 12 else api[:8] + "…" + api[-4:]
    endpoint, key, use_post = _resolve_search_api(api)

    print("=== 1. 写法识别 ===")
    print(f"  原始值  : {masked}")
    print(f"  接口地址: {endpoint}")
    print(f"  认证方式: {'POST + Bearer（api_key 风格）' if use_post else 'GET ?q=（endpoint 风格）'}")
    print(f"  取到 key: {'是（前 4 位 ' + key[:4] + '）' if key else '否'}")
    if use_post and not key:
        print("  ❌ 判定为 POST 风格但没取到 key，请检查写法")
        return 1

    print("\n=== 2. 真实调用（2 个查询）===")
    urls = _search_api_urls(verbose=True)
    print(f"\n  共抽到头条链接 {len(urls)} 条")

    print("\n=== 3. 逐条回源核实（parse_article）===")
    if not urls:
        print("  ⚠️ 没有拿到可用的头条文章链接。两种可能：")
        print("     ① 结果里根本没有 toutiao.com 域 → 搜索词没命中头条；")
        print("     ② 抽到了头条链接，但全是 /w/ 微头条或陈年旧文，已被过滤剔除")
        print("        （实测 2026-10 Tavily 就是这种情况，自动补充几乎无效）。")
        print("     不影响主流程（会回退本地清单），但别指望它替代人工补链接。")
        return 2

    ok = 0
    for u in urls:
        r = parse_article(u)
        if r:
            ok += 1
            h = r.get("pub_hours")
            win = "窗口内" if (h is not None and h <= 48) else ("已出窗" if h is not None else "时间未核实")
            print(f"  ✅ {r['pub_rel']:>8} [{win}] {r['title'][:42]}")
        else:
            print(f"  ❌ 回源核实失败（可能是死链或非文章页）: {u}")

    print(f"\n结论：{ok}/{len(urls)} 条可回源核实。"
          f"{' 预检通过，可以填进 GitHub Secrets。' if ok else ' 全部失败，请检查 key 是否有效。'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
