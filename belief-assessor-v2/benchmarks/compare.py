#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v1 vs v2 对比测试 runner — 挂载 agent 后直接调用。

Usage:
    python compare.py "claim文本"
    
    然后输入搜索到的证据文本和 6 bool JSON。
    输出 v1 vs v2 的对比结果。

    或者 agent 在对话中直接 import 使用。
"""

import sys
import json

# v1 和 v2 的路径 — 安装后 agent 挂载的路径可能不同，此处用相对导入
# 实际使用时根据 skill 安装路径调整

def run_comparison(claim, evidence, ai_6bool_json):
    """
    同一条 claim+evidence+6bool，分别跑 v1 和 v2，输出对比。
    
    Args:
        claim: 声明文本
        evidence: 搜索到的证据
        ai_6bool_json: agent 的 6 个布尔判断 (JSON 字符串)
    
    Returns:
        dict 包含 v1_result, v2_result, diff
    """
    # --- 导入 v1 ---
    # 根据 skill 名调整 import 路径
    # v1 skill name: belief-state-runtime → import path 可能是 belief_state_runtime
    try:
        import importlib
        from pathlib import Path
        
        # 查找 v1 skill
        v1_paths = list(Path.home().glob(".qclaw/skills/belief-state-runtime*/scripts/assess.py"))
        v1_path = str(v1_paths[0]) if v1_paths else None
        
        # 查找 v2 skill (当前目录)
        v2_dir = Path(__file__).parent
        
        # 如果 v1 不在预期位置，尝试其他路径
        if not v1_path:
            v1_paths = list(Path.home().glob(".openclaw/workspace/skills/belief-state-runtime*/scripts/assess.py"))
            v1_path = str(v1_paths[0]) if v1_paths else None
        
        if not v1_path:
            return {"error": "v1 skill not found. 请先安装 belief-state-runtime (v1) skill"}
        
        # v2
        v2_path = str(v2_dir / "scripts" / "assess.py")
        
        # 动态加载 v1
        v1_spec = importlib.util.spec_from_file_location("v1_assess", v1_path)
        v1_module = importlib.util.module_from_spec(v1_spec)
        v1_spec.loader.exec_module(v1_module)
        
        # 动态加载 v2
        v2_spec = importlib.util.spec_from_file_location("v2_assess", v2_path)
        v2_module = importlib.util.module_from_spec(v2_spec)
        v2_spec.loader.exec_module(v2_module)
        
    except Exception as e:
        return {"error": f"Import failed: {e}"}
    
    # 解析 6 bool
    try:
        parsed = json.loads(ai_6bool_json) if isinstance(ai_6bool_json, str) else ai_6bool_json
    except json.JSONDecodeError:
        parsed = ai_6bool_json
    
    # --- v1 评估 ---
    try:
        r1 = v1_module.assess_claim_with_response(claim, evidence, json.dumps(parsed))
    except Exception as e:
        r1 = {"error": str(e)}
    
    # --- v2 评估 (standard) ---
    try:
        r2 = v2_module.assess_claim_with_response(claim, evidence, json.dumps(parsed))
    except Exception as e:
        r2 = {"error": str(e)}
    
    # --- v2 评估 (conservative) ---
    try:
        r2c = v2_module.assess_claim_with_response(
            claim, evidence, json.dumps(parsed),
            config=v2_module.ProjectionConfig.conservative()
        )
    except Exception as e:
        r2c = {"error": str(e)}
    
    # --- diff ---
    return {
        "claim": claim,
        "evidence_preview": evidence[:150],
        "ai_judgments": {k: v for k, v in parsed.items() if isinstance(v, bool)},
        "v1": {
            "state": r1.get("state"),
            "confidence": r1.get("confidence"),
            "confidence_range": r1.get("confidence_range"),
        },
        "v2_standard": {
            "state": r2.get("state"),
            "confidence": r2.get("confidence"),
            "confidence_range": r2.get("confidence_range"),
            "veto_reasons": r2.get("veto_reasons"),
            "cap_applied": r2.get("cap_applied"),
        },
        "v2_conservative": {
            "state": r2c.get("state"),
            "confidence": r2c.get("confidence"),
            "confidence_range": r2c.get("confidence_range"),
            "veto_reasons": r2c.get("veto_reasons"),
            "cap_applied": r2c.get("cap_applied"),
        },
        "key_diff": {
            "state_changed": r1.get("state") != r2.get("state"),
            "v1_v2_state": f"{r1.get('state')} → {r2.get('state')}",
            "v2_has_veto": len(r2.get("veto_reasons", [])) > 0,
            "v2_capped": r2.get("cap_applied", 1.0) < 1.0,
            "v2_ci_width": (
                round(r2.get("confidence_range", [0, 1])[1] - r2.get("confidence_range", [0, 1])[0], 4)
                if isinstance(r2.get("confidence_range"), list) and len(r2.get("confidence_range", [])) == 2
                else "N/A"
            ),
        },
    }


def print_comparison(result):
    """美化打印对比结果"""
    if "error" in result:
        print(f"❌ {result['error']}")
        return
    
    print(f"\n{'='*60}")
    print(f"Claim: {result['claim'][:60]}")
    print(f"Evidence: {result['evidence_preview'][:80]}...")
    print(f"AI judgments: {result['ai_judgments']}")
    print(f"\n{'─'*60}")
    print(f"{'':>20} {'v1':>12} {'v2(标准)':>12} {'v2(保守)':>12}")
    print(f"{'─'*60}")
    print(f"{'state':>20} {result['v1']['state']:>12} {result['v2_standard']['state']:>12} {result['v2_conservative']['state']:>12}")
    print(f"{'confidence':>20} {result['v1']['confidence']:>12.4f} {result['v2_standard']['confidence']:>12.4f} {result['v2_conservative']['confidence']:>12.4f}")
    
    ci1 = result['v1']['confidence_range']
    ci2 = result['v2_standard']['confidence_range']
    ci3 = result['v2_conservative']['confidence_range']
    print(f"{'CI lower':>20} {ci1[0]:>12.4f} {ci2[0]:>12.4f} {ci3[0]:>12.4f}")
    print(f"{'CI upper':>20} {ci1[1]:>12.4f} {ci2[1]:>12.4f} {ci3[1]:>12.4f}")
    
    veto = result['v2_standard']['veto_reasons']
    print(f"{'veto_reasons':>20} {'(v1 无此字段)':>12} {str(veto):>12} {str(result['v2_conservative']['veto_reasons']):>12}")
    
    print(f"\n{'─'*60}")
    print(f"差异: 状态变化={result['key_diff']['v1_v2_state']}, "
          f"v2触发约束={result['key_diff']['v2_has_veto']}, "
          f"v2区间宽度={result['key_diff']['v2_ci_width']}")
    print(f"{'='*60}\n")


# ── 命令行入口 ──
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python compare.py '声明文本'")
        print("然后粘贴证据和6bool JSON")
        sys.exit(1)
    
    claim = sys.argv[1]
    
    print("请输入证据文本 (多行, 以空行结束):")
    evidence_lines = []
    while True:
        try:
            line = input()
            if line == "":
                break
            evidence_lines.append(line)
        except EOFError:
            break
    evidence = "\n".join(evidence_lines)
    
    print("请输入 6 bool JSON:")
    ai_json = input()
    
    result = run_comparison(claim, evidence, ai_json)
    print_comparison(result)
