"""DeepSeek LLM 客户端（M4/M5 创作任务共用，openai 兼容接口，仅依赖 requests）"""
from __future__ import annotations

import json

import requests

from .config import get_secret

BASE_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"


class LLMError(Exception):
    pass


def llm_configured() -> bool:
    return bool(get_secret("DEEPSEEK_API_KEY"))


def deepseek_chat(
    messages: list[dict],
    *,
    temperature: float = 0.8,
    max_tokens: int = 2400,
    json_mode: bool = False,
    timeout: float = 150,
) -> str:
    key = get_secret("DEEPSEEK_API_KEY")
    if not key:
        raise LLMError("未配置 DEEPSEEK_API_KEY：请在 server/.env 或 GitHub Secrets 中填写")
    body = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    try:
        resp = requests.post(
            BASE_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=body,
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise LLMError(f"DeepSeek 请求失败: {e}")
    if resp.status_code != 200:
        raise LLMError(f"DeepSeek 返回 {resp.status_code}: {resp.text[:300]}")
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError):
        raise LLMError(f"DeepSeek 响应解析失败: {resp.text[:300]}")


def deepseek_json(messages: list[dict], **kw) -> dict:
    """要求模型返回 JSON 对象，自动剥离代码围栏并解析。"""
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
        # 兜底：截取第一对花括号
        start, end = t.find("{"), t.rfind("}")
        if start >= 0 and end > start:
            return json.loads(t[start : end + 1])
        raise LLMError(f"DeepSeek JSON 解析失败: {text[:300]}")
