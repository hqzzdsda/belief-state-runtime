# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

# -*- coding: utf-8 -*-
"""
belief-state-runtime skill — Agent 可调用的认识论推理工具

Agent 集成（使用 agent 自己的 LLM）：
    from skill import assess_claim

    # agent 提供自己的 LLM 调用函数
    def my_llm(messages, temperature=0.05, max_tokens=256):
        return agent.chat(messages, temperature=temperature, max_tokens=max_tokens)

    result = assess_claim("特斯拉自动驾驶更安全",
                          evidence="NHTSA报告显示...",
                          llm_func=my_llm)

CLI（使用 DeepSeek API）：
    python skill.py "特斯拉自动驾驶更安全" --evidence "NHTSA报告显示..."
    python skill.py --interactive
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from epistemic.feature_extractor import FeatureExtractor


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
    llm_func=None,
) -> list:
    """
    增量评估：逐条添加证据，观察置信度变化。

    Args:
        claim: 声明文本
        evidence_stages: 证据列表，按顺序逐条添加
        llm_func: LLM 调用函数（可选）

    Returns:
        每步的结果列表
    """
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
                "summary": "一句话总结",
            }
        }
    """
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
        "usage": """
当 agent 收到用户的信息请求时：
1. 收集相关证据（搜索结果、文档片段、API 返回等）
2. 调用 belief_assessor(claim, evidence)
3. 根据返回的 state 决定回答方式：
   - VERIFIED: 直接引用信息，标注置信度
   - CONTESTED: 告知用户"存在争议"，列出正反证据
   - UNCERTAIN: 告知用户"证据不足"，建议进一步查询
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
    """根据评估结果生成一句话总结。"""
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


# ── CLI ──────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="belief-state-runtime skill — 认识论推理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python skill.py "特斯拉自动驾驶更安全" --evidence "NHTSA报告显示..."
  python skill.py --interactive
  python skill.py --definition  # 输出 skill 定义 JSON
        """,
    )
    parser.add_argument("claim", nargs="?", help="要评估的声明")
    parser.add_argument("--evidence", "-e", default="", help="证据文本")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument("--model", "-m", default="auto",
                        choices=["auto", "mimo", "deepseek"],
                        help="LLM 模型: auto(优先MiMo), mimo, deepseek (默认: auto)")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--definition", "-d", action="store_true", help="输出 skill 定义 JSON")
    args = parser.parse_args()

    if args.definition:
        print(json.dumps(get_skill_definition(), ensure_ascii=False, indent=2))
        return

    # 构建 LLM 函数
    llm_func = _build_llm_func(args.model)

    if args.interactive:
        _interactive_mode(llm_func)
        return

    if not args.claim:
        parser.print_help()
        return

    result = assess_claim(args.claim, evidence=args.evidence, llm_func=llm_func)

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
        print(f"  总结: {result['summary']}")


def _interactive_mode(llm_func=None):
    """交互模式：多轮输入声明和证据。"""
    print("\n  belief-state-runtime 交互模式")
    print("  输入声明，然后输入证据（空行结束）。输入 q 退出。\n")

    prev_conf = None
    while True:
        claim = input("  声明: ").strip()
        if claim.lower() in ("q", "quit", "exit"):
            break
        if not claim:
            continue

        evidence = input("  证据: ").strip()

        result = assess_claim(claim, evidence=evidence, previous_confidence=prev_conf, llm_func=llm_func)
        prev_conf = result["confidence"]

        print(f"\n  → {result['state']} (conf={result['confidence']:.3f})")
        print(f"    {result['summary']}")
        true_feats = [k for k, v in result['features'].items() if v]
        if true_feats:
            print(f"    特征: {', '.join(true_feats)}")
        print()


if __name__ == "__main__":
    main()
