"""验证「输出侧偶发拦截」假设：同一提示词长文生成 5 轮，看是否出现随机 BLOCKED。

若同一提示词部分轮次 OK、部分轮次被拦，即可确认：
  风控不是死在你的提示词上，而是死在模型某一次生成的正文里（输出侧），
  因此「重跑就好/换思路」不是解法，必须做重试+降级。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jobs.diag_risk import call, save  # noqa: E402

# 银发康养链路里风险最高的一条：中年男性健康 + 猝死 + 洗澡/脑梗
USER = (
    "请基于下面的主题，原创一篇可直接发布在今日头条的中文纯文字文案（不要插图、不要分镜表）。\n"
    "主题标题：过了40岁，最怕这3个时间点\n"
    "核心思想：中年男性猝死风险常集中在几个容易被忽视的日常场景：清晨猛起、酒后洗澡、长期熬夜后剧烈活动。"
    "提前避开这些'危险时刻'，比吃任何补品都实在。\n"
    "切入角度：以《伤寒杂病论》'治未病'思想为引，逐条拆解晨起、酒后、熬夜后三个时刻的身体信号和应对动作。\n\n"
    "要求：\n1. 正文 800-1100 字；\n2. 口语化、多短句，段落之间用空行；\n"
    "3. 结尾用一句提问引导评论互动；\n"
    "4. 健康类内容必须有边界：不做诊断、不承诺疗效、不提具体药物剂量、不指导具体用药；\n"
    "5. 严禁编造任何事实与个人案例；\n"
    "6. 标题保持 8-20 字。\n\n"
    '输出 JSON：{"title":"最终标题","body":"完整正文（用\\n\\n分段）"}'
)
SYS = "你是今日头条银发康养赛道爆款文案作者，只输出 JSON 对象。"
ROUNDS = 5


def main() -> int:
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": USER}]
    kinds = []
    for i in range(1, ROUNDS + 1):
        r = call(msgs, temperature=1.0, max_tokens=4000, json_mode=True)
        r["name"] = f"output-risk/heavy#{i}"
        save(f"output_risk_heavy_{i}", r)
        kinds.append(r["kind"])
        flag = "OK     " if r["ok"] else f"{r['kind']:<7}"
        print(f"[{flag}] 第{i}轮  {len(r['text'])} 字符  {r['text'][:70]!r}", flush=True)

    blocked = kinds.count("BLOCKED")
    print(f"\n结果：{ROUNDS} 轮中 {blocked} 轮被风控拦截 —— {kinds}")
    if blocked:
        print(">>> 确认：同一提示词也会随机命中「输出侧」风控。")
    else:
        print(">>> 本轮未复现；结合前序实验，说明该拦截为低频偶发，必须靠重试+降级兜底。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
