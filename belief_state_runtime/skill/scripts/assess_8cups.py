# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

#!/usr/bin/env python3
"""Assess: 每天应该喝8杯水"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from assess import assess_claim_with_response

claim = "每天应该喝8杯水"
evidence = """
《中国居民膳食指南(2022)》推荐成年人每天饮水量1500-1700ml，按200-250ml标准杯计算约7-8杯。
北京大学公卫学院副研究员张娜：8杯水有一定科学依据，但严谨性不足，需明确杯子容量。
《科学》期刊研究：首次揭示人类全生命周期需水量规律，8杯水建议可能超过大多数人真正需水量。
医生：每天8杯水只是笼统概念和平均值，具体因人而异。
英国营养基金会报告：八杯水护肤法"毫无科学依据"，喝水多少与肤质/皮肤保湿性无直接联系。
水中毒：较罕见，仅在短时间内超量饮水超出肾脏代谢能力时可能发生。
关键变量：运动量、气候、体质、排出量等都影响实际需水量。
"""

ai_judgment = {
    "direct_support": False,       # 部分支持，但不是"应该"的绝对标准
    "new_info": True,              # 有新的研究和数据
    "logical_consistent": True,    # 证据内部一致
    "direct_refute": False,        # 没有完全否定，只是说"不严谨"
    "limitation": True,            # 大量限制条件和个体差异
    "error_outdated": False        # 2022-2025年数据，较新
}

result = assess_claim_with_response(claim, evidence, json.dumps(ai_judgment))

print("=" * 50)
print("CLAIM:", claim)
print("=" * 50)
print(f"State: {result['state']}")
print(f"Confidence: {result['confidence']:.3f}")
print(f"Summary: {result['summary']}")