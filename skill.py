# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

# -*- coding: utf-8 -*-
"""
belief-state-runtime v2 skill — Agent 可调用的认识论推理工具

Agent 集成（使用 agent 自己的 LLM）：
    from skill import assess_claim, ProjectionConfig

    # agent 提供自己的 LLM 调用函数
    def my_llm(messages, temperature=0.05, max_tokens=256):
        return agent.chat(messages, temperature=temperature, max_tokens=max_tokens)

    result = assess_claim("特斯拉自动驾驶更安全",
                          evidence="NHTSA报告显示...",
                          llm_func=my_llm)

    # v2: 保守策略（高风险场景）
    result = assess_claim("金融声明", llm_func=my_llm,
                          config=ProjectionConfig.conservative())

    # v2: AI-friendly 接口（零额外 LLM 调用）
    prompt = get_assessment_prompt(claim, evidence)
    # AI 回答 6 个布尔值...
    result = assess_claim_with_response(claim, evidence, ai_response)

CLI（使用 DeepSeek API）：
    python skill.py "特斯拉自动驾驶更安全" --evidence "NHTSA报告显示..."
    python skill.py --interactive
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from epistemic.feature_extractor import FeatureExtractor, ProjectionConfig, LLM_FEATURES


# ── 提取器实例管理 ──────────────────────────────────────────

_extractors = {}

def _get_extractor(llm_func=None):
    """
    获取或缓存 FeatureExtractor 实例。

    Args:
        llm_func: LLM 调用函数，签名 (messages, temperature, max_tokens) -> str
                  如果为 None，使用默认 DeepSeek API
    """
    key = id(llm_func) if llm_func else "default"
    if key not in _extractors:
        _extractors[key] = FeatureExtractor(llm_chat_func=llm_func)
    return _extractors[key]


# ── 核心 API ──────────────────────────────────────────

def assess_claim(
    claim: str,
    evidence: str = "",
    previous_confidence: float = None,
    llm_func=None,
    config: ProjectionConfig = None,
) -> dict:
    """
    评估声明的可信度。

    Args:
        claim: 要评估的声明文本
        evidence: 支持或反驳声明的证据文本（可选）
        previous_confidence: 之前的置信度（用于增量更新，可选）
        llm_func: LLM 调用函数（可选）
                  签名: (messages: list[dict], temperature: float, max_tokens: int) -> str
                  Agent 应传入自己的 LLM 调用函数
                  不传则使用 DeepSeek API
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
    ext = _get_extractor(llm_func)
    result = ext.extract(claim, evidence, previous_confidence=previous_confidence, config=config)

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
    llm_func=None,
    config: ProjectionConfig = None,
) -> list:
    """
    增量评估：逐条添加证据，观察置信度变化。

    Args:
        claim: 声明文本
        evidence_stages: 证据列表，按顺序逐条添加
        llm_func: LLM 调用函数（可选）
        config: v2 投影配置（可选）

    Returns:
        每步的结果列表，包含 delta 和 veto_reasons
    """
    ext = _get_extractor(llm_func)
    results = []
    prev_conf = None

    for i, evidence in enumerate(evidence_stages):
        result = ext.extract(claim, evidence, previous_confidence=prev_conf, config=config)
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
    config: ProjectionConfig = None,
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
    features: dict,
    previous_confidence: float = None,
    config: ProjectionConfig = None,
) -> dict:
    """从预提取的特征计算完整评估（不调用 LLM）。"""
    from epistemic.feature_extractor import FeatureResult
    import math as _math

    result = FeatureResult()

    # Layer 1: 规则层（用 dummy llm_chat 只跑规则层）
    ext = FeatureExtractor(llm_chat_func=lambda m, t, mt: "{}")
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


# ── Skill 定义 ──────────────────────────────────────────

def get_skill_definition() -> dict:
    """
    返回 skill 的结构化定义，供 agent 框架注册使用。

    Returns:
        {
            "name": "belief_assessor",
            "description": "评估声明的可信度，输出状态和置信度",
            "parameters": {
                "claim": {"type": "string", "required": True, "description": "要评估的声明"},
                "evidence": {"type": "string", "required": False, "description": "支持或反驳的证据"},
            },
            "returns": {
                "state": "VERIFIED/CONTESTED/UNCERTAIN",
                "confidence": "0.0-1.0",
                "veto_reasons": "触发的约束列表（v2）",
                "summary": "一句话总结",
            }
        }
    """
    return {
        "name": "belief_assessor",
        "description": "评估声明的可信度，基于证据输出结构化的信念状态和校准后的置信度。v2 新增 4 重约束系统、参数化配置、公式化置信区间。当需要判断一条信息是否可信时使用。",
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


# ── 辅助 ──────────────────────────────────────────

def _build_llm_func(model: str = "auto"):
    """根据 model 参数构建 LLM 调用函数。"""
    if model == "mimo":
        from api.deepseek_client import mimo_chat
        return lambda messages, temperature=0.05, max_tokens=256: \
            mimo_chat(messages=messages, temperature=temperature, max_tokens=max_tokens)
    elif model == "deepseek":
        from api.deepseek_client import deepseek_chat
        return lambda messages, temperature=0.05, max_tokens=256: \
            deepseek_chat(messages=messages, temperature=temperature,
                          max_tokens=max_tokens, model="deepseek-chat")
    else:  # auto
        from api.deepseek_client import llm_chat
        return lambda messages, temperature=0.05, max_tokens=256: \
            llm_chat(messages=messages, temperature=temperature, max_tokens=max_tokens)


def _generate_summary(result) -> str:
    """根据评估结果生成一句话总结。v2 包含 veto_reasons。"""
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


# ── CLI ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="belief-state-runtime v2 skill — 认识论推理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python skill.py "特斯拉自动驾驶更安全" --evidence "NHTSA报告显示..."
  python skill.py --interactive
  python skill.py --definition  # 输出 skill 定义 JSON
  python skill.py "声明" --conservative  # 使用保守策略
        """,
    )
    parser.add_argument("claim", nargs="?", help="要评估的声明")
    parser.add_argument("--evidence", "-e", default="", help="证据文本")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument("--model", "-m", default="auto",
                        choices=["auto", "mimo", "deepseek"],
                        help="LLM 模型: auto(优先MiMo), mimo, deepseek (默认: auto)")
    parser.add_argument("--conservative", "-c", action="store_true",
                        help="使用保守策略（高风险场景）")
    parser.add_argument("--permissive", "-p", action="store_true",
                        help="使用宽松策略（低风险场景）")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--definition", "-d", action="store_true", help="输出 skill 定义 JSON")
    args = parser.parse_args()

    if args.definition:
        print(json.dumps(get_skill_definition(), ensure_ascii=False, indent=2))
        return

    # 构建 LLM 函数
    llm_func = _build_llm_func(args.model)

    # 选择配置
    config = None
    if args.conservative:
        config = ProjectionConfig.conservative()
    elif args.permissive:
        config = ProjectionConfig.permissive()

    if args.interactive:
        _interactive_mode(llm_func, config)
        return

    if not args.claim:
        parser.print_help()
        return

    result = assess_claim(args.claim, evidence=args.evidence, llm_func=llm_func, config=config)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n  声明: {args.claim}")
        if args.evidence:
            print(f"  证据: {args.evidence[:80]}...")
        print(f"\n  状态: {result['state']}")
        print(f"  置信度: {result['confidence']:.3f} [{result['confidence_range'][0]:.3f}, {result['confidence_range'][1]:.3f}]")
        print(f"  质量因子: {result['quality_factor']:.3f}")
        print(f"  支持分: {result['support_score']:.3f}  反驳分: {result['refute_score']:.3f}")
        true_feats = [k for k, v in result['features'].items() if v]
        print(f"  特征: {', '.join(true_feats) if true_feats else '(无)'}")
        if result.get("veto_reasons"):
            print(f"  约束触发: {', '.join(result['veto_reasons'])}")
        if result.get("cap_applied", 1.0) < 1.0:
            print(f"  置信度上限: {result['cap_applied']:.3f}")
        print(f"  总结: {result['summary']}")


def _interactive_mode(llm_func=None, config=None):
    """交互模式：多轮输入声明和证据。"""
    config_name = "标准"
    if config and config.verify_threshold >= 0.78:
        config_name = "保守"
    elif config and config.verify_threshold <= 0.62:
        config_name = "宽松"

    print(f"\n  belief-state-runtime v2 交互模式 [{config_name}策略]")
    print("  输入声明，然后输入证据（空行结束）。输入 q 退出。\n")

    prev_conf = None
    while True:
        claim = input("  声明: ").strip()
        if claim.lower() in ("q", "quit", "exit"):
            break
        if not claim:
            continue

        evidence = input("  证据: ").strip()

        result = assess_claim(claim, evidence=evidence,
                              previous_confidence=prev_conf,
                              llm_func=llm_func, config=config)
        prev_conf = result["confidence"]

        veto_str = ""
        if result.get("veto_reasons"):
            veto_str = f" [约束: {', '.join(result['veto_reasons'])}]"

        print(f"\n  → {result['state']} (conf={result['confidence']:.3f}){veto_str}")
        print(f"    区间: [{result['confidence_range'][0]:.3f}, {result['confidence_range'][1]:.3f}]")
        print(f"    {result['summary']}")
        true_feats = [k for k, v in result['features'].items() if v]
        if true_feats:
            print(f"    特征: {', '.join(true_feats)}")
        print()


if __name__ == "__main__":
    main()
