# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

# -*- coding: utf-8 -*-
"""
belief-state-runtime v2 — 认识论推理引擎

Agent 集成：
    from belief_state_runtime import assess_claim, ProjectionConfig

    result = assess_claim("声明", evidence="证据", llm_func=agent.llm)
    # 保守策略:
    result = assess_claim("声明", llm_func=agent.llm,
                          config=ProjectionConfig.conservative())
"""

from typing import Optional, Callable, List, Dict
from .feature_extractor import FeatureExtractor, ProjectionConfig, LLM_FEATURES

LLMFunc = Callable[[list, float, int], str]

__version__ = "2.0.0"
__all__ = [
    "assess_claim", "assess_incremental", "get_skill_definition",
    "get_assessment_prompt", "assess_claim_with_response",
    "ProjectionConfig",
]

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
    config: Optional[ProjectionConfig] = None,
) -> dict:
    """
    评估声明的可信度。

    Args:
        claim: 要评估的声明文本
        evidence: 支持或反驳声明的证据文本（可选）
        previous_confidence: 之前的置信度（用于增量更新，可选）
        llm_func: LLM 调用函数（必需）
                  签名: (messages: list[dict], temperature: float, max_tokens: int) -> str
        config: v2 投影配置（可选）
                使用 ProjectionConfig.conservative() 进行高风险评估
                使用 ProjectionConfig.permissive() 进行低风险评估

    Returns:
        {
            "state": "VERIFIED" | "CONTESTED" | "UNCERTAIN",
            "confidence": 0.0-1.0,
            "confidence_range": [lower, upper],        # v2: 公式化区间
            "quality_factor": 0.0-1.0,
            "support_score": 0.0-1.0,
            "refute_score": 0.0-1.0,
            "features": {"direct_support": true, ...},
            "direct_refute": false,
            "limitation": false,
            "veto_reasons": [...],                      # v2: 触发的约束
            "cap_applied": 1.0,                         # v2: 应用的置信度上限
            "summary": "一句话总结"
        }
    """
    if llm_func is None:
        raise ValueError("llm_func is required. Pass your agent's LLM call function.")

    ext = _get_extractor(llm_func)
    result = ext.extract(
        claim, evidence,
        previous_confidence=previous_confidence,
        config=config,
    )

    return {
        "state": result.state,
        "confidence": round(result.final_confidence, 4),
        "confidence_range": [
            round(result.confidence_lower, 4),
            round(result.confidence_upper, 4),
        ],
        "quality_factor": round(result.quality_factor, 3),
        "support_score": round(result.support_score, 3),
        "refute_score": round(result.refute_score, 3),
        "features": result.features,
        "direct_refute": result.direct_refute,
        "limitation": result.limitation,
        "veto_reasons": result.veto_reasons,
        "cap_applied": round(result.cap_applied, 3),
        "summary": _generate_summary(result),
    }


def assess_incremental(
    claim: str,
    evidence_stages: list,
    llm_func: LLMFunc = None,
    config: Optional[ProjectionConfig] = None,
) -> list:
    """
    增量评估：逐条添加证据，观察置信度变化。

    Args:
        claim: 声明文本
        evidence_stages: 证据列表，按顺序逐条添加
        llm_func: LLM 调用函数（必需）
        config: v2 投影配置（可选）

    Returns:
        每步的结果列表，包含 delta 和 veto_reasons
    """
    if llm_func is None:
        raise ValueError("llm_func is required.")

    ext = _get_extractor(llm_func)
    results = []
    prev_conf = None

    for i, evidence in enumerate(evidence_stages):
        result = ext.extract(
            claim, evidence,
            previous_confidence=prev_conf,
            config=config,
        )
        entry = {
            "step": i + 1,
            "evidence_preview": evidence[:100],
            "state": result.state,
            "confidence": round(result.final_confidence, 4),
            "confidence_range": [
                round(result.confidence_lower, 4),
                round(result.confidence_upper, 4),
            ],
            "support_score": round(result.support_score, 3),
            "refute_score": round(result.refute_score, 3),
            "quality_factor": round(result.quality_factor, 3),
            "features": {k: v for k, v in result.features.items() if v},
            "veto_reasons": result.veto_reasons,
            "delta": round(result.final_confidence - prev_conf, 4) if prev_conf is not None else 0.0,
        }
        results.append(entry)
        prev_conf = result.final_confidence

    return results


# ── AI-Friendly Interface ──────────────────────────────────────────

def get_assessment_prompt(claim: str, evidence: str = "") -> str:
    """
    返回 AI agent 应回答的评估提示词（6 个布尔判断）。

    Agent 工作流：
    1. Agent 搜索证据
    2. 调用 get_assessment_prompt(claim, evidence) 获取提示词
    3. AI 回答 6 个布尔值 JSON
    4. 调用 assess_claim_with_response(claim, evidence, ai_response) 获取结果

    Returns:
        str: AI agent 应回答的提示词文本
    """
    return f"""你是一个事实验证助手。请基于以下【声明】和【新证据】，回答6个判断。输出一个JSON对象，只输出JSON，不要有其他文字。

声明：{claim}
新证据：{evidence[:1500] if evidence else "(未提供证据)"}

判断标准：
1. direct_support: 证据是否直接支持声明？
2. new_info: 证据是否提供了先前未提及的新信息？
3. logical_consistent: 证据与之前已知信息是否逻辑一致？
4. direct_refute: 证据是否明确反驳声明？
5. limitation: 证据是否指出声明的局限性或例外条件？
6. error_outdated: 证据是否揭示声明中的信息是错误的或已过时？

输出格式：
{{"direct_support": true/false, "new_info": true/false, "logical_consistent": true/false, "direct_refute": true/false, "limitation": true/false, "error_outdated": false}}"""


def assess_claim_with_response(
    claim: str,
    evidence: str = "",
    llm_response: str = "",
    previous_confidence: float = None,
    config: Optional[ProjectionConfig] = None,
) -> dict:
    """
    使用 AI agent 的 6 布尔回答完成完整评估（零额外 LLM 调用）。

    Agent 工作流：
    1. 搜索证据
    2. get_assessment_prompt(claim, evidence) → prompt
    3. AI 回答 6 个布尔值 JSON
    4. assess_claim_with_response(claim, evidence, ai_response) → result

    Args:
        claim: 声明文本
        evidence: 证据文本
        llm_response: AI agent 的 6 布尔 JSON 回答
        previous_confidence: 之前的置信度（用于增量更新）
        config: v2 投影配置（可选）

    Returns:
        完整评估结果 dict
    """
    import re as _re
    import json as _json

    features = {fid: False for fid in LLM_FEATURES}

    if llm_response:
        try:
            json_match = _re.search(r'\{[^{}]+\}', llm_response)
            if json_match:
                data = _json.loads(json_match.group())
                for fid in LLM_FEATURES:
                    val = data.get(fid)
                    if isinstance(val, bool):
                        features[fid] = val
                    elif isinstance(val, str):
                        features[fid] = val.lower() in ("true", "yes", "1")
                    elif isinstance(val, (int, float)):
                        features[fid] = bool(val)
        except (_json.JSONDecodeError, AttributeError):
            for fid in LLM_FEATURES:
                pattern = _re.compile(rf'"{fid}"\s*:\s*(true|false)', _re.IGNORECASE)
                match = pattern.search(llm_response)
                if match:
                    features[fid] = match.group(1).lower() == "true"

    return _compute_from_features(claim, evidence, features, previous_confidence, config)


def _compute_from_features(
    claim: str,
    evidence: str,
    features: Dict[str, bool],
    previous_confidence: Optional[float] = None,
    config: Optional[ProjectionConfig] = None,
) -> dict:
    """从预提取的特征计算完整评估（不调用 LLM）。"""
    from .feature_extractor import FeatureResult
    import math as _math

    result = FeatureResult()

    # Layer 1: 规则层（用 dummy llm_func 只跑规则层）
    ext = FeatureExtractor(llm_func=lambda m, t, mt: "{}")
    ext._extract_rule_signals(evidence, result)

    # 设置特征
    result.features = features
    result.direct_refute = features.get("direct_refute", False)
    result.limitation = features.get("limitation", False)

    # 质量因子 Q
    result.quality_factor = (
        0.4 * result.source_reliability +
        0.3 * result.evidence_density +
        0.2 * result.temporal_freshness +
        0.1 * result.provenance_quality
    )

    # 支持分和反驳分
    f = result.features
    result.support_score = (
        (1.0 if f.get("direct_support") else 0.0) +
        (0.5 if f.get("new_info") else 0.0) +
        (0.3 if f.get("logical_consistent") else 0.0)
    ) / 1.8

    result.refute_score = (
        (1.0 if f.get("direct_refute") else 0.0) +
        (0.6 if f.get("error_outdated") else 0.0)
    ) / 1.6

    # 原始置信度
    semantic = result.support_score * (1 - result.refute_score)
    raw_conf = 0.6 * semantic + 0.4 * result.quality_factor
    if result.limitation:
        raw_conf *= 0.85
    result.raw_confidence = min(1.0, max(0.0, raw_conf))

    # v2: 投影层
    cfg = config or ProjectionConfig()
    ext._project(result, claim, previous_confidence, cfg)

    return {
        "state": result.state,
        "confidence": round(result.final_confidence, 4),
        "confidence_range": [
            round(result.confidence_lower, 4),
            round(result.confidence_upper, 4),
        ],
        "quality_factor": round(result.quality_factor, 3),
        "support_score": round(result.support_score, 3),
        "refute_score": round(result.refute_score, 3),
        "features": result.features,
        "direct_refute": result.direct_refute,
        "limitation": result.limitation,
        "veto_reasons": result.veto_reasons,
        "cap_applied": round(result.cap_applied, 3),
        "summary": _generate_summary(result),
    }


def get_skill_definition() -> dict:
    """返回 skill 的结构化定义，供 agent 框架注册使用。"""
    return {
        "name": "belief_assessor",
        "description": "评估声明的可信度，基于证据输出结构化的信念状态和校准后的置信度。v2 新增 4 重约束系统、参数化配置、公式化置信区间。",
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
            "confidence_range": "[lower, upper] 公式化置信区间",
            "veto_reasons": "触发的约束列表（v2 新增）",
            "features": "6 个布尔判断依据",
            "summary": "一句话总结",
        },
        "usage": """
当 agent 收到用户的信息请求时：
1. 收集相关证据（搜索结果、文档片段、API 返回等）
2. 调用 belief_assessor(claim, evidence)
3. 根据返回的 state 决定回答方式：
   - VERIFIED: 直接引用信息，标注置信度
   - CONTESTED: 告知用户"存在争议"，列出正反证据。检查 veto_reasons 了解原因
   - UNCERTAIN: 告知用户"证据不足"，建议进一步查询
4. v2 新增: 使用 ProjectionConfig.conservative() 处理高风险场景
""",
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
        elif result.veto_reasons:
            reasons = ", ".join(result.veto_reasons)
            parts.append(f"证据存在争议（{reasons}）")
        else:
            parts.append("证据存在争议")
    else:
        if result.veto_reasons:
            reasons = ", ".join(result.veto_reasons)
            parts.append(f"证据不足（{reasons}）")
        else:
            parts.append("证据不足以判断")

    true_feats = [k for k, v in result.features.items() if v]
    if "new_info" in true_feats:
        parts.append("提供了新信息")
    if "error_outdated" in true_feats:
        parts.append("信息可能过时")

    return "，".join(parts) if parts else "无法评估"
