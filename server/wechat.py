"""Server酱 微信推送（复用 tender-monitor 的 SCKEY 方案）"""
import requests

from .config import get_secret

PUSH_URL = "https://sctapi.ftqq.com/{sendkey}.send"


def sc_configured() -> bool:
    return bool(get_secret("SCKEY"))


def send_markdown(title: str, markdown: str) -> dict:
    sendkey = get_secret("SCKEY")
    if not sendkey:
        return {"sent": False, "reason": "未配置 SCKEY：请在 server/.env 或项目根 .env 中填写后重启后端"}
    try:
        resp = requests.post(
            PUSH_URL.format(sendkey=sendkey),
            data={"title": title, "desp": markdown},
            timeout=10,
        )
        data = resp.json()
        if data.get("code") == 0:
            return {"sent": True}
        return {"sent": False, "reason": f"Server酱返回异常: {data.get('message', data)}"}
    except Exception as e:  # noqa: BLE001
        return {"sent": False, "reason": f"推送异常: {e}"}


def build_table_markdown(master: dict, max_rows: int = 50) -> str:
    """主表 → Markdown 表格（推送正文）。超长截断并给出提示。"""
    rows = master.get("rows", [])
    lines = ["| 序号 | 项目名称 | 预计发布公告时间 | 发布时间 | 开标时间 | 投标单位 | 状态 |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    shown = rows[:max_rows]
    for i, r in enumerate(shown, start=1):
        esc = lambda s: str(s or "").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {i} | {esc(r.get('name'))} | {esc(r.get('expect_publish'))} | "
            f"{esc(r.get('publish_at'))} | {esc(r.get('open_at'))} | {esc(r.get('bidder'))} | {esc(r.get('status'))} |"
        )
    total = len(rows)
    if total > max_rows:
        lines.append(f"\n> 共 {total} 项，仅展示前 {max_rows} 项；完整表格请在工作台导出。")
    else:
        lines.append(f"\n> 共 {total} 项 · 由「月招标计划筛选助手」生成")
    return "\n".join(lines)
