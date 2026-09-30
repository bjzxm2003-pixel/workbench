"""DeepSeek LLM 客户端（M4/M5/M6 创作任务共用，openai 兼容接口，仅依赖 requests）

风控兜底（2026-09 加固）
------------------------
DeepSeek 对**整段 messages 入参**做内容安全审核，命中即返回
``400 {"error":{"message":"Content Exists Risk ...","code":"invalid_request_error"}}``。
两类已知故障：

1. **偶发/输出侧**：同一条提示词有时通过、有时被拦（模型某次生成被扫到）。
   对策：原样重试，并用低温度重发换一条生成路径。
2. **会话级永久封禁**：敏感片段一旦进入上下文，该会话**每次**请求都返回同一个 400。
   对策：区分出 ``LLMBlocked``，把完整请求体落盘取证，然后让作业层跳过这一条、
   继续产出其余内容——绝不让一条文案把整轮 run 变成"处理失败"。

调用方（jobs/*.py）建议写法::

    try:
        out = deepseek_json(messages)
    except LLMBlocked as e:
        # 这一条被风控拦住：标记 blocked 后继续，不要中断整轮
        mark_blocked(item, e)
        continue
    except LLMError as e:
        # 网络/解析等其它故障
        ...

环境变量：
  ``DEEPSEEK_BASE_URL``     覆盖接口地址（便于切换供应商兜底）
  ``DEEPSEEK_MODEL``        覆盖模型名
  ``DEEPSEEK_MAX_ATTEMPTS`` 单次调用的最大尝试次数，默认 3
  ``DEEPSEEK_BLOCK_DIR``    被拦请求的取证落盘目录，默认 ``data/media/blocked``
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .config import BASE, get_secret

BJ_TZ = timezone(timedelta(hours=8))

DEFAULT_BASE_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"

# 命中任一标记即判定为「内容风控拒绝」而非普通 4xx/5xx
BLOCK_MARKERS = ("Content Exists Risk", "INVALID_REQUEST", "invalid_request_error")

# 低温度重发时的温度：换一条更"稳"的生成路径，避开输出侧偶发命中
SAFE_TEMPERATURE = 0.3

# 同一段文本连续被拦多少次后，判定为「会话级封禁」，不再无意义重试
SESSION_BLOCK_LIMIT = 3

_BLOCK_DIR: Path | None = None
_BLOCK_COUNT = 0      # 本进程内被拦总次数（用于汇总提示）
_LAST_BLOCK: dict | None = None


class LLMError(Exception):
    """LLM 调用失败的基类。"""

    def __init__(self, message: str, *, status: int = 0, request_id: str = "",
                 text: str = ""):
        super().__init__(message)
        self.status = status
        self.request_id = request_id
        self.text = text


class LLMBlocked(LLMError):
    """内容风控拒绝（Content Exists Risk / INVALID_REQUEST）。

    作业层应当捕获它并把当前条目标记为 blocked 后**继续**，而不是让整轮任务失败。
    """

    def __init__(self, message: str, *, status: int = 400, request_id: str = "",
                 text: str = "", log_file: str = "", sessions: int = 1):
        super().__init__(message, status=status, request_id=request_id, text=text)
        self.log_file = log_file
        self.sessions = sessions


def llm_configured() -> bool:
    return bool(get_secret("DEEPSEEK_API_KEY"))


def base_url() -> str:
    return os.environ.get("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL


def model_name() -> str:
    return os.environ.get("DEEPSEEK_MODEL") or DEFAULT_MODEL


def max_attempts() -> int:
    try:
        return max(1, min(5, int(os.environ.get("DEEPSEEK_MAX_ATTEMPTS", "3"))))
    except ValueError:
        return 3


def block_dir() -> Path:
    global _BLOCK_DIR
    if _BLOCK_DIR is None:
        _BLOCK_DIR = Path(os.environ.get("DEEPSEEK_BLOCK_DIR") or (BASE / "data" / "media" / "blocked"))
    return _BLOCK_DIR


def block_stats() -> dict:
    """本进程内的风控统计，供报告/推送里如实说明"哪些条目被拦"。"""
    return {"blocked": _BLOCK_COUNT, "last": _LAST_BLOCK}


# ---------------- 内部工具 ----------------
def _is_block_resp(resp) -> bool:
    # 只在 400 上判定风控：401/403/429 等即使带同样字样也不是内容审核
    if resp.status_code != 400:
        return False
    body = resp.text or ""
    return any(m in body for m in BLOCK_MARKERS)


def _extract_request_id(resp) -> str:
    """尽力取出 request_id：响应头优先，其次错误体/message 里的字段。"""
    for h in ("x-ds-trace-id", "x-request-id", "x-requestid", "trace-id", "x-trace-id"):
        v = resp.headers.get(h)
        if v:
            return str(v).strip()
    body = resp.text or ""
    # 兼容 {"request_id":"..."} 与 "Content Exists Risk (request_id: ...)"
    m = re.search(r'"(?:request_id|requestId|id)"\s*:\s*"([^"]+)"', body)
    if m:
        return m.group(1)
    m = re.search(r"request_id\s*[:=]\s*([0-9a-fA-F-]{8,})", body)
    return m.group(1) if m else ""


def _fingerprint(messages: list[dict]) -> str:
    raw = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# 净化规则：只处理**结构性高风险**内容，不做词表替换
_PLATFORM_RE = re.compile(r"(抖音|快手|小红书|今日头条|视频号|B站)")
_URL_RE = re.compile(r"https?://\S+")
_NUM_RE = re.compile(r"\d[\d,\.]*\s*(?:万|亿|千|百|%|％)|[\d,\.]{3,}")
_KEEP_PLATFORM = "短视频平台"


def sanitize_text(text: str) -> str:
    """降级用净化：去掉链接、具体数字与平台名。

    注意：这是**最后一级**降级手段，会有损语义（"点赞区间 8万-220万"会变成
    一句泛化描述）。因此默认前两次尝试**保持原文不变**，只在仍被拦时才启用。
    """
    out = _URL_RE.sub("", text)
    out = _NUM_RE.sub("", out)
    out = _PLATFORM_RE.sub(_KEEP_PLATFORM, out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out


def sanitized_messages(messages: list[dict]) -> list[dict]:
    """生成净化副本，并在末尾追加一条约束（不修改原始 messages）。"""
    out = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            out.append({**m, "content": sanitize_text(content)})
        else:
            out.append(dict(m))
    out.append({
        "role": "system",
        "content": (
            "补充约束：只输出通用创作建议，不得出现具体数据、链接、平台名称，"
            "不得涉及医疗诊断、用药指导、疗效承诺、投资建议。"
        ),
    })
    return out


def _summarize_messages(messages: list[dict], limit: int = 400) -> list[dict]:
    """取证摘要：保留角色与文本片段（完整原文落盘，便于事后二分定位）。"""
    out = []
    for m in messages:
        content = m.get("content")
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        out.append({"role": m.get("role", ""), "len": len(text),
                    "head": text[:limit], "tail": text[-limit:] if len(text) > limit else ""})
    return out


def log_blocked(messages: list[dict], resp, *, attempt: int, mode: str,
                temperature: float, model: str) -> str:
    """把被拦请求的完整上下文落盘，返回文件路径（取证专用）。"""
    global _BLOCK_COUNT, _LAST_BLOCK
    _BLOCK_COUNT += 1
    try:
        d = block_dir()
        d.mkdir(parents=True, exist_ok=True)
        request_id = _extract_request_id(resp)
        stamp = datetime.now(BJ_TZ).strftime("%Y%m%d_%H%M%S")
        fp = _fingerprint(messages)
        # 同一秒内同一 fingerprint 可能被拦多次（重试序列），加序号避免互相覆盖
        path = d / f"blocked_{stamp}_{fp}_a{attempt}.json"
        n = 1
        while path.exists():
            n += 1
            path = d / f"blocked_{stamp}_{fp}_a{attempt}_{n}.json"
        payload = {
            "at": datetime.now(BJ_TZ).strftime("%Y-%m-%d %H:%M:%S"),
            "request_id": request_id,
            "fingerprint": fp,
            "attempt": attempt,
            "mode": mode,
            "temperature": temperature,
            "model": model,
            "status": resp.status_code,
            "response_head": (resp.text or "")[:1000],
            "messages": messages,                    # 完整原文，便于二分定位
            "messages_digest": _summarize_messages(messages, limit=200),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        _LAST_BLOCK = {"fingerprint": fp, "request_id": request_id, "mode": mode,
                       "file": str(path), "at": payload["at"]}
        return str(path)
    except Exception as e:  # noqa: BLE001  取证失败不能影响主流程
        print(f"[warn] 风控取证落盘失败：{e}")
        return ""


def _post(body: dict, *, timeout: float):
    key = get_secret("DEEPSEEK_API_KEY")
    if not key:
        raise LLMError("未配置 DEEPSEEK_API_KEY：请在 server/.env 或 GitHub Secrets 中填写")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    return requests.post(base_url(), headers=headers, json=body, timeout=timeout)


def _parse_content(resp) -> str:
    try:
        data = resp.json()
        if not isinstance(data, dict):
            raise TypeError("响应不是 JSON 对象")
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, ValueError):
        raise LLMError(f"DeepSeek 响应解析失败: {(resp.text or '')[:300]}", status=resp.status_code)


# ---------------- 对外主入口 ----------------
def deepseek_chat(
    messages: list[dict],
    *,
    temperature: float = 0.8,
    max_tokens: int = 2400,
    json_mode: bool = False,
    timeout: float = 150,
    attempts: int | None = None,
) -> str:
    """带风控兜底的对话调用。

    成功返回文本；被风控拒绝抛出 ``LLMBlocked``（附 request_id 与取证文件路径）；
    其它故障抛 ``LLMError``。

    尝试序列（逐级降级，原文优先）：
      1) 原文 + 原温度
      2) 原文 + 低温度（换生成路径，避开输出侧偶发命中）
      3) 净化后的文本 + 低温度（最后手段，会有损语义）
    同一段文本连续被拦 ``SESSION_BLOCK_LIMIT`` 次后判定为会话级封禁，不再重试。
    """
    if not get_secret("DEEPSEEK_API_KEY"):
        raise LLMError("未配置 DEEPSEEK_API_KEY：请在 server/.env 或 GitHub Secrets 中填写")

    total = attempts if attempts is not None else max_attempts()
    fp = _fingerprint(messages)
    session_blocks = 0
    last_block: LLMBlocked | None = None

    for attempt in range(1, total + 1):
        if attempt == 1:
            msgs, temp, mode = messages, temperature, "original"
        elif attempt == 2:
            msgs, temp, mode = messages, min(temperature, SAFE_TEMPERATURE), "retry-low-temp"
        else:
            msgs = sanitized_messages(messages)
            temp = min(temperature, SAFE_TEMPERATURE)
            mode = "sanitized"

        body = {"model": model_name(), "messages": msgs,
                "temperature": temp, "max_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        try:
            resp = _post(body, timeout=timeout)
        except requests.RequestException as e:
            if attempt >= total:
                raise LLMError(f"DeepSeek 请求失败（已重试 {attempt} 次）: {e}")
            time.sleep(1.5 * attempt)
            continue

        if resp.status_code == 200:
            try:
                return _parse_content(resp)
            except LLMError:
                # 200 但体不完整/非预期：换一次生成路径再试
                if attempt >= total:
                    raise
                time.sleep(1.5 * attempt)
                continue

        if _is_block_resp(resp):
            log_file = log_blocked(messages, resp, attempt=attempt, mode=mode,
                                   temperature=temp, model=model_name())
            request_id = _extract_request_id(resp)
            session_blocks += 1
            last_block = LLMBlocked(
                f"内容风控拒绝（Content Exists Risk）：fingerprint={fp} "
                f"request_id={request_id or '未知'} 已落盘 {log_file or '（落盘失败）'}",
                status=resp.status_code, request_id=request_id,
                text=resp.text or "", log_file=log_file, sessions=session_blocks,
            )
            if session_blocks >= SESSION_BLOCK_LIMIT:
                # 同一段文本连续被拦，判定为会话级封禁：继续重试没有意义
                raise last_block
            continue

        if resp.status_code in (408, 429, 500, 502, 503, 504) and attempt < total:
            time.sleep(1.5 * attempt)
            continue

        raise LLMError(f"DeepSeek 返回 {resp.status_code}: {(resp.text or '')[:300]}",
                       status=resp.status_code, text=resp.text or "")

    if last_block:
        raise last_block
    raise LLMError(f"DeepSeek 调用失败：已尝试 {total} 次")


def probe(messages: list[dict], **kw) -> tuple[bool, str]:
    """单次探测某段文本是否被风控（诊断用，不重试、不降级）。

    返回 ``(是否通过, 说明/request_id)``。
    """
    body = {"model": model_name(), "messages": messages,
            "temperature": kw.get("temperature", 0.8),
            "max_tokens": kw.get("max_tokens", 200)}
    if kw.get("json_mode"):
        body["response_format"] = {"type": "json_object"}
    try:
        resp = _post(body, timeout=kw.get("timeout", 60))
    except requests.RequestException as e:
        return False, f"网络错误: {e}"
    if resp.status_code == 200:
        return True, _extract_request_id(resp)
    if _is_block_resp(resp):
        rid = _extract_request_id(resp)
        log_blocked(messages, resp, attempt=1, mode="probe",
                    temperature=body["temperature"], model=body["model"])
        return False, rid or "被风控拒绝"
    return False, f"HTTP {resp.status_code}: {(resp.text or '')[:300]}"


# ---------------- JSON 便捷入口 ----------------
def _repair_json(t: str) -> str:
    """修剪尾随逗号并补齐未闭合的括号（max_tokens 截断时很常见）。"""
    t = re.sub(r",\s*([}\]])", r"\1", t)
    opens, closes = [], {"}": "{", "]": "["}
    in_str = esc = False
    for ch in t:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            opens.append(ch)
        elif ch in "}]" and opens and opens[-1] == closes[ch]:
            opens.pop()
    if in_str:
        t += '"'
    for ch in reversed(opens):
        t += "}" if ch == "{" else "]"
    return t


def deepseek_json(messages: list[dict], **kw) -> dict:
    """要求模型返回 JSON 对象，自动剥离代码围栏、修剪尾随逗号并补全截断括号。"""
    text = deepseek_chat(messages, json_mode=True, **kw)
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.startswith("json"):
            t = t[4:]
    t = t.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # 兜底 1：截取第一对花括号
    start, end = t.find("{"), t.rfind("}")
    if start >= 0 and end > start:
        candidate = t[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    # 兜底 2：从第一个 { 起修复截断
    if start >= 0:
        try:
            return json.loads(_repair_json(t[start:]))
        except json.JSONDecodeError:
            pass
    # 兜底 3：整段修复
    try:
        return json.loads(_repair_json(t))
    except json.JSONDecodeError:
        raise LLMError(f"DeepSeek JSON 解析失败: {text[:300]}", text=text)
