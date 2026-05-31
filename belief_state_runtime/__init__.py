# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

# -*- coding: utf-8 -*-
"""
belief-state-runtime — 认识论推理引擎

Agent 集成：
    from belief_state_runtime import assess_claim

    result = assess_claim("声明", evidence="证据", llm_func=agent.llm)
"""

from typing import Optional, Callable, List, Dict
from .feature_extractor import FeatureExtractor

LLMFunc = Callable[[list, float, int], str]

__version__ = "1.0.0"
__all__ = ["assess_claim", "assess_incremental", "get_skill_definition"]

_extractors = {}


def _get_extractor(llm_func: LLMFunc) -> FeatureExtractor:
    key = id(llm_func)
    if key not in _extractors:
        _extractors[key] = FeatureExtractor(llm_func=llm_func)
    return _extractors[key]


def assess_claim(
    claim: str,
    evidence: str = "",
    previous_confidence: float = None,
    llm_func: LLMFunc = None,
) -> dict:
    """
    评估声明的可信度。

    Args:
        claim: 要评估的声明文本
        evidence: 支持或反驳声明的证据文本（可选）
        previous_confidence: 之前的置信度（用于增量更新，可选）
        llm_func: LLM 调用函数（必需）
                  签名: (messages: list[dict], temperature: float, max_tokens: int) -> str

    Returns:
        {
            "state": "VERIFIED" | "CONTESTED" | "UNCERTAIN",
            "confidence": 0.0-1.0,
            "confidence_range": [lower, upper],
            "quality_factor": 0.0-1.0,
            "support_score": 0.0-1.0,
            "refute_score": 0.0-1.0,
            "features": {"direct_support": true, ...},
            "direct_refute": false,
            "limitation": false,
            "summary": "一句话总结"
        }
    """
    if llm_func is None:
        raise ValueError("llm_func is required. Pass your agent's LLM call function.")

    ext = _get_extractor(llm_func)
    result = ext.extract(claim, evidence, previous_confidence=previous_confidence)

    return {
        "state": result.state,
        "confidence": result.final_confidence,
        "confidence_range": [
            max(0.0, result.final_confidence - 0.15),
            min(1.0, result.final_confidence + 0.15),
        ],
        "quality_factor": round(result.quality_factor, 3),
        "support_score": round(result.support_score, 3),
        "refute_score": round(result.refute_score, 3),
        "features": result.features,
        "direct_refute": result.direct_refute,
        "limitation": result.limitation,
        "summary": _generate_summary(result),
    }


def assess_incremental(
    claim: str,
    evidence_stages: list,
    llm_func: LLMFunc = None,
) -> list:
    """
    增量评估：逐条添加证据，观察置信度变化。

    Args:
        claim: 声明文本
        evidence_stages: 证据列表，按顺序逐条添加
        llm_func: LLM 调用函数（必需）

    Returns:
        每步的结果列表
    """
    if llm_func is None:
        raise ValueError("llm_func is required.")

    ext = _get_extractor(llm_func)
    results = []
    prev_conf = None

    for i, evidence in enumerate(evidence_stages):
        result = ext.extract(claim, evidence, previous_confidence=prev_conf)
        entry = {
            "step": i + 1,
            "evidence_preview": evidence[:100],
            "state": result.state,
            "confidence": result.final_confidence,
            "support_score": round(result.support_score, 3),
            "refute_score": round(result.refute_score, 3),
            "quality_factor": round(result.quality_factor, 3),
            "features": {k: v for k, v in result.features.items() if v},
            "delta": round(result.final_confidence - prev_conf, 3) if prev_conf is not None else 0.0,
        }
        results.append(entry)
        prev_conf = result.final_confidence

    return results


def get_skill_definition() -> dict:
    """返回 skill 的结构化定义，供 agent 框架注册使用。"""
    return {
        "name": "belief_assessor",
        "description": "评估声明的可信度，基于证据输出结构化的信念状态和校准后的置信度。当需要判断一条信息是否可信时使用。",
        "parameters": {
            "claim": {
                "type": "string",
                "required": True,
                "description": "要评估的声明文本",
            },
            "evidence": {
                "type": "string",
                "required": False,
                "description": "支持或反驳声明的证据文本。可以是多个来源的证据拼接。",
            },
        },
        "returns": {
            "state": "VERIFIED（可信）/ CONTESTED（有争议）/ UNCERTAIN（不确定）",
            "confidence": "0.0-1.0 的置信度",
            "confidence_range": "[lower, upper] 置信区间",
            "features": "6 个布尔判断依据",
            "summary": "一句话总结",
        },
    }


def _generate_summary(result) -> str:
    parts = []
    if result.direct_refute:
        parts.append("证据明确反驳了声明")
    elif result.state == "VERIFIED":
        if result.final_confidence >= 0.85:
            parts.append("证据强力支持声明")
        else:
            parts.append("证据支持声明")
    elif result.state == "CONTESTED":
        if result.limitation:
            parts.append("证据支持但有局限性")
        else:
            parts.append("证据存在争议")
    else:
        parts.append("证据不足以判断")

    true_feats = [k for k, v in result.features.items() if v]
    if "new_info" in true_feats:
        parts.append("提供了新信息")
    if "error_outdated" in true_feats:
        parts.append("信息可能过时")

    return "，".join(parts) if parts else "无法评估"
