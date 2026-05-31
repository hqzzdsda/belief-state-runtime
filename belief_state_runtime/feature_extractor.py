# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

# -*- coding: utf-8 -*-
"""
belief-state-runtime v1 — 通用信念更新引擎

规则层（4 个连续信号）+ LLM 层（6 个布尔特征）→ 置信度 + 状态

此文件自包含，不依赖外部 API 客户端。
LLM 调用通过 llm_func 参数注入。
"""

import math
import re
import json as json_mod
from typing import Dict, Tuple, Optional, Callable
from dataclasses import dataclass, field

# ── LLM 特征定义 ──────────────────────────────────────────

LLM_FEATURES = {
    "direct_support":     "证据是否直接支持声明？",
    "new_info":           "证据是否提供了先前未提及的新信息？",
    "logical_consistent": "证据与之前已知信息是否逻辑一致？",
    "direct_refute":      "证据是否明确反驳声明？",
    "limitation":         "证据是否指出声明的局限性或例外条件？",
    "error_outdated":     "证据是否揭示声明中的信息是错误的或已过时？",
}


@dataclass
class FeatureResult:
    """信念评估结果"""
    source_reliability: float = 0.5
    evidence_density: float = 0.0
    temporal_freshness: float = 0.5
    provenance_quality: float = 0.2
    quality_factor: float = 0.5

    features: Dict[str, bool] = field(default_factory=dict)
    support_score: float = 0.0
    refute_score: float = 0.0

    raw_confidence: float = 0.5
    final_confidence: float = 0.5
    state: str = "UNCERTAIN"
    direct_refute: bool = False
    limitation: bool = False

    def to_dict(self) -> dict:
        return {
            "source_reliability": round(self.source_reliability, 4),
            "evidence_density": round(self.evidence_density, 4),
            "temporal_freshness": round(self.temporal_freshness, 4),
            "provenance_quality": round(self.provenance_quality, 4),
            "quality_factor": round(self.quality_factor, 4),
            "features": self.features,
            "support_score": round(self.support_score, 4),
            "refute_score": round(self.refute_score, 4),
            "raw_confidence": round(self.raw_confidence, 4),
            "final_confidence": round(self.final_confidence, 4),
            "state": self.state,
            "direct_refute": self.direct_refute,
            "limitation": self.limitation,
        }


# ── LLM 调用类型 ──────────────────────────────────────────

LLMFunc = Callable[[list, float, int], str]
"""
LLM 调用函数签名:
  messages: [{"role": "user", "content": "..."}]
  temperature: float
  max_tokens: int
  -> str (LLM 回复文本)
"""


class FeatureExtractor:
    """
    通用信念更新引擎。

    用法:
        ext = FeatureExtractor(llm_func=my_llm)
        result = ext.extract(claim, evidence)
    """

    def __init__(self, llm_func: LLMFunc):
        if llm_func is None:
            raise ValueError("llm_func is required. Pass your agent's LLM call function.")
        self.llm_func = llm_func

    def extract(
        self,
        claim: str,
        evidence: str,
        previous_confidence: Optional[float] = None,
        alpha: float = 0.5,
    ) -> FeatureResult:
        result = FeatureResult()

        # Layer 1: 规则层
        self._extract_rule_signals(evidence, result)

        # Layer 2: LLM 层
        self._extract_llm_features(claim, evidence, result)

        # 质量因子 Q
        result.quality_factor = (
            0.4 * result.source_reliability +
            0.3 * result.evidence_density +
            0.2 * result.temporal_freshness +
            0.1 * result.provenance_quality
        )

        # 支持分与反驳分
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

        result.direct_refute = f.get("direct_refute", False)
        result.limitation = f.get("limitation", False)

        # 原始置信度
        semantic = result.support_score * (1 - result.refute_score)
        raw_conf = 0.6 * semantic + 0.4 * result.quality_factor
        if result.limitation:
            raw_conf *= 0.85
        result.raw_confidence = min(1.0, max(0.0, raw_conf))

        # 矛盾覆盖
        if result.direct_refute:
            result.state = "CONTESTED"
            result.final_confidence = min(result.raw_confidence, 0.6)
            return result

        # 增量更新
        result.final_confidence = self._incremental_update(
            result.raw_confidence, previous_confidence, alpha,
        )

        # 状态判定
        result.state = self._determine_state(result.final_confidence)
        return result

    # ── 规则层 ──────────────────────────────────────────

    def _extract_rule_signals(self, evidence: str, result: FeatureResult):
        if not evidence:
            result.source_reliability = 0.4
            result.evidence_density = 0.0
            result.temporal_freshness = 0.7
            result.provenance_quality = 0.5
            return

        text = evidence.lower()

        domains = re.findall(r'https?://([^\s/]+)', evidence)
        if domains:
            scores = [self._domain_score(d) for d in domains]
            result.source_reliability = sum(scores) / len(scores)
        else:
            result.source_reliability = self._keyword_reliability(text)

        segments = re.split(r'\n\n|(?<=[.。])\s+', evidence)
        segments = [s.strip() for s in segments if len(s.strip()) > 20]
        result.evidence_density = min(1.0, 0.3 + len(segments) * 0.2)

        years = re.findall(r'\b((?:19|20)\d{2})\b', evidence)
        if years:
            latest = max(int(y) for y in years)
            age = 2026 - latest
            result.temporal_freshness = round(1.0 / (1.0 + age), 4)
        else:
            result.temporal_freshness = 0.7

        unique_tlds = set()
        for d in domains:
            parts = d.split(".")
            tld = ".".join(parts[-2:]) if len(parts) >= 2 else d
            unique_tlds.add(tld)
        result.provenance_quality = min(1.0, 0.4 + len(unique_tlds) * 0.2) if unique_tlds else 0.5

    def _domain_score(self, domain: str) -> float:
        domain = domain.lower()
        for pattern, score in [
            ("gov", 0.9), ("edu", 0.9), ("who.int", 0.9),
            ("pubmed.ncbi", 0.9), ("nature.com", 0.9), ("science.org", 0.9),
            ("reuters.com", 0.7), ("bbc.com", 0.7), ("apnews.com", 0.7),
            ("nytimes.com", 0.7), ("theguardian.com", 0.7),
            ("arxiv.org", 0.6), ("wikipedia.org", 0.5),
            ("twitter.com", 0.3), ("x.com", 0.3), ("reddit.com", 0.3),
        ]:
            if pattern in domain:
                return score
        if domain.endswith(".gov") or domain.endswith(".edu"):
            return 0.9
        if domain.endswith(".org"):
            return 0.6
        return 0.5

    def _keyword_reliability(self, text: str) -> float:
        for keywords, score in [
            (["official", "government", "who", "nih", "fda", "央行", "官方", "政府"], 0.9),
            (["research", "study", "journal", "nature", "science", "研究", "论文", "期刊"], 0.8),
            (["report", "survey", "statistics", "报告", "白皮书", "调查", "统计"], 0.7),
            (["news", "reported", "新闻", "报道", "媒体"], 0.6),
            (["forum", "social media", "twitter", "论坛", "社交媒体", "网友"], 0.3),
        ]:
            if any(w in text for w in keywords):
                return score
        return 0.6

    # ── LLM 层 ──────────────────────────────────────────

    def _extract_llm_features(self, claim: str, evidence: str, result: FeatureResult):
        prompt = f"""你是一个事实验证助手。请基于以下【声明】和【新证据】，回答6个判断。输出一个JSON对象，只输出JSON，不要有其他文字。

声明：{claim}
新证据：{evidence[:1500]}

判断标准：
1. direct_support: 证据是否直接支持声明？
2. new_info: 证据是否提供了先前未提及的新信息？
3. logical_consistent: 证据与之前已知信息是否逻辑一致？
4. direct_refute: 证据是否明确反驳声明？
5. limitation: 证据是否指出声明的局限性或例外条件？
6. error_outdated: 证据是否揭示声明中的信息是错误的或已过时？

输出格式：
{{"direct_support": true/false, "new_info": true/false, "logical_consistent": true/false, "direct_refute": true/false, "limitation": true/false, "error_outdated": false}}"""

        features = {fid: False for fid in LLM_FEATURES}

        try:
            response = self.llm_func(
                [{"role": "user", "content": prompt}],
                0.05,
                256,
            )
            features = self._parse_features(response)
        except Exception as e:
            print(f"[WARN] LLM feature extraction failed: {e}")

        result.features = features

    def _parse_features(self, response: str) -> Dict[str, bool]:
        features = {fid: False for fid in LLM_FEATURES}

        try:
            json_match = re.search(r'\{[^{}]+\}', response)
            if json_match:
                data = json_mod.loads(json_match.group())
                for fid in LLM_FEATURES:
                    val = data.get(fid)
                    if isinstance(val, bool):
                        features[fid] = val
                    elif isinstance(val, str):
                        features[fid] = val.lower() in ("true", "yes", "1")
                    elif isinstance(val, (int, float)):
                        features[fid] = bool(val)
                return features
        except (json_mod.JSONDecodeError, AttributeError):
            pass

        for fid in LLM_FEATURES:
            pattern = re.compile(rf'"{fid}"\s*:\s*(true|false)', re.IGNORECASE)
            match = pattern.search(response)
            if match:
                features[fid] = match.group(1).lower() == "true"
            else:
                pattern2 = re.compile(rf'{fid}\s*[:=]\s*(true|false)', re.IGNORECASE)
                match2 = pattern2.search(response)
                if match2:
                    features[fid] = match2.group(1).lower() == "true"

        return features

    # ── 增量更新 ──────────────────────────────────────────

    def _incremental_update(
        self, raw_conf: float, old_conf: Optional[float], alpha: float,
    ) -> float:
        if old_conf is None:
            return raw_conf
        delta = raw_conf - old_conf
        if delta > 0.1:
            return alpha * raw_conf + (1 - alpha) * old_conf
        elif delta < -0.1:
            return min(old_conf, raw_conf)
        else:
            return (old_conf + raw_conf) / 2.0

    def _determine_state(self, confidence: float) -> str:
        if confidence >= 0.65:
            return "VERIFIED"
        elif confidence <= 0.25:
            return "UNCERTAIN"
        else:
            return "CONTESTED"
