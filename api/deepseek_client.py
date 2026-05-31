# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

# -*- coding: utf-8 -*-
"""
LLM API 客户端 — 支持 DeepSeek 和 MiMo。

用法:
    from api.deepseek_client import llm_chat
    response = llm_chat([{"role": "user", "content": "hello"}])
"""

import os
from typing import Optional
from openai import OpenAI

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "")
MIMO_BASE_URL = os.environ.get("MIMO_BASE_URL", "https://token-plan-sgp.xiaomimimo.com/v1")
MIMO_MODEL = "mimo-v2.5"

_client: Optional[OpenAI] = None
_mimo_client: Optional[OpenAI] = None
_mimo_available: Optional[bool] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return _client


def get_mimo_client() -> OpenAI:
    global _mimo_client
    if _mimo_client is None:
        _mimo_client = OpenAI(api_key=MIMO_API_KEY, base_url=MIMO_BASE_URL)
    return _mimo_client


def _check_mimo_available() -> bool:
    global _mimo_available
    if _mimo_available is not None:
        return _mimo_available
    try:
        client = get_mimo_client()
        resp = client.chat.completions.create(
            model=MIMO_MODEL,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=512,
            temperature=0.0,
        )
        msg = resp.choices[0].message if resp.choices else None
        has_content = bool(msg and (msg.content or getattr(msg, 'reasoning_content', None)))
        _mimo_available = has_content
    except Exception:
        _mimo_available = False
    return _mimo_available


def deepseek_chat(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    model: str = "deepseek-v4-flash",
) -> str:
    client = get_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        raise RuntimeError(f"DeepSeek API 调用失败: {e}")


def mimo_chat(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    model: str = MIMO_MODEL,
) -> str:
    client = get_mimo_client()
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        if not content and hasattr(response.choices[0].message, 'reasoning_content'):
            reasoning = response.choices[0].message.reasoning_content or ""
            if reasoning:
                lines = reasoning.strip().split('\n')
                content = lines[-1] if lines else reasoning[:200]
        return content
    except Exception as e:
        raise RuntimeError(f"MiMo API 调用失败: {e}")


def llm_chat(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    model: str = "deepseek-v4-flash",
    prefer_mimo: bool = True,
) -> str:
    """统一 LLM 调用入口。首选 MiMo，回退 DeepSeek。"""
    if prefer_mimo and _check_mimo_available():
        try:
            return mimo_chat(messages, temperature=temperature, max_tokens=max_tokens)
        except Exception:
            pass
    return deepseek_chat(messages, temperature=temperature, max_tokens=max_tokens, model=model)
