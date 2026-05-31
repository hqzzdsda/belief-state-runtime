# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Assess: 中国生育率下降会导致经济崩溃吗"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assess import get_assessment_prompt, assess_claim_with_response

claim = "中国生育率下降会导致经济崩溃"
evidence = """
最新数据：2025年全年出生人口仅约800万（中国自1949年以来最低），人口连续第四年负增长，出生率降至每千人5.63人（2023年为6.4人）。

结构性挑战：
- 劳动力市场紧缩：预计2025年20-39岁女性较2020年减少1400万人，劳动力短缺推高工资
- 老龄化加速：65岁以上人口占比上升，养老和医疗支出压力加重
- 消费结构转型：年轻人口减少，传统消费市场（母婴、教育）萎缩，老年消费需求快速增长
- 储蓄率下降：老龄化导致储蓄率下降，投资驱动型经济增长模式难以为继
- 房地产承压：人口减少削弱住房需求，三四线城市房价下行压力
- 地方财政：土地财政模式难以为继
- 社会保障体系：养老压力上升，独生子女家庭养老负担重

积极面（中国人民大学人口研究）：
- 生育率下降缓解了人口高速增长造成的各种危机
- 经济走出"人口陷阱"，宏观人口经济关系进入协调状态
- 创造最有利于经济增长的人口"黄金结构"
- 制度和政策因素可以催化积极经济后果

国际经验：
- 日本、德国经历速降型生育率下降，面临老龄化挑战但未出现经济崩溃
- 法国、北美经历缓降型生育率下降，经济相对平稳
- 生育率下降与经济增长的关系十分复杂，不会自动导致崩溃
"""

print("=" * 60)
print("CLAIM:", claim)
print("=" * 60)

# AI's judgment based on evidence
ai_judgment = {
    "direct_support": False,       # Evidence does NOT directly support "经济崩溃"
    "new_info": True,              # Provides new specific data
    "logical_consistent": True,    # Evidence is internally consistent
    "direct_refute": False,        # Does not explicitly refute (no scholar says "won't collapse")
    "limitation": True,           # Many limitations mentioned (challenges + opportunities)
    "error_outdated": False        # Data is recent (2025)
}

print(f"\nAI Judgment (6 features): {json.dumps(ai_judgment, ensure_ascii=False)}")

result = assess_claim_with_response(
    claim=claim,
    evidence=evidence,
    llm_response=json.dumps(ai_judgment)
)

print(f"\n{'='*60}")
print("ASSESSMENT RESULT")
print("=" * 60)
print(f"State: {result['state']}")
print(f"Confidence: {result['confidence']:.3f}")
print(f"Confidence Range: [{result['confidence_range'][0]:.3f}, {result['confidence_range'][1]:.3f}]")
print(f"Quality Factor: {result['quality_factor']}")
print(f"Support Score: {result['support_score']} | Refute Score: {result['refute_score']}")
print(f"\nSummary: {result['summary']}")
print(f"\nFeatures: {json.dumps(result['features'], ensure_ascii=False)}")