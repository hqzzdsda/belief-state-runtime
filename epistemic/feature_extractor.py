# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

# -*- coding: utf-8 -*-
"""
belief-state-runtime v1 — 通用信念更新引擎

规则层（4 个连续信号）+ LLM 层（6 个布尔特征）→ 置信度 + 状态

设计原则：
  - 规则层提供确定性、可复现的基础信号
  - LLM 仅做最必要的语义判断（6 个布尔值）
  - 不依赖外部标签，根据新旧置信度差值自动驱动更新
  - 参数和阈值使用通用设定，不针对特定数据集调优
"""

import math
import re
import json as json_mod
from typing import Dict, Tuple, Optional
from dataclasses import dataclass, field


# ── LLM 特征定义（6 个布尔值）──────────────────────────

LLM_FEATURES = {
    "direct_support":    "证据是否直接支持声明？（即证据与声明方向一致且没有矛盾）",
    "new_info":          "证据是否提供了先前未提及的新信息？（例如新数据、新案例、新观点）",
    "logical_consistent":"证据与之前已知信息是否逻辑一致？",
    "direct_refute":     "证据是否明确反驳声明？（例如直接否定声明中的事实或推理）",
    "limitation":        "证据是否指出声明的局限性或例外条件？",
    "error_outdated":    "证据是否揭示声明中的信息是错误的或已过时？",
}


@dataclass
class FeatureResult:
    """信念评估结果"""
    # 规则层信号
    source_reliability: float = 0.5
    evidence_density: float = 0.0
    temporal_freshness: float = 0.5
    provenance_quality: float = 0.2
    quality_factor: float = 0.5        # Q: 规则层综合质量

    # LLM 层特征
    features: Dict[str, bool] = field(default_factory=dict)
    support_score: float = 0.0         # LLM 支持分
    refute_score: float = 0.0          # LLM 反驳分

    # 最终结果
    raw_confidence: float = 0.5        # 聚合后的原始置信度
    final_confidence: float = 0.5      # 增量更新后的最终置信度
    state: str = "UNCERTAIN"           # VERIFIED / CONTESTED / UNCERTAIN
    direct_refute: bool = False        # 是否触发矛盾覆盖
    limitation: bool = False           # 是否有局限性

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


class FeatureExtractor:
    """
    通用信念更新引擎。

    用法:
        ext = FeatureExtractor()
        result = ext.extract(claim, evidence)
        # 增量更新:
        result2 = ext.extract(claim, new_evidence, previous_confidence=result.final_confidence)
    """

    def __init__(self, llm_chat_func=None):
        if llm_chat_func is None:
            from api.deepseek_client import llm_chat
            self.llm_chat = lambda messages, temperature=0.05, max_tokens=256: \
                llm_chat(messages=messages, temperature=temperature,
                         max_tokens=max_tokens)
        else:
            self.llm_chat = llm_chat_func

    def extract(
        self,
        claim: str,
        evidence: str,
        previous_confidence: Optional[float] = None,
        alpha: float = 0.5,
    ) -> FeatureResult:
        """
        提取特征并计算置信度。

        Args:
            claim: 声明文本
            evidence: 证据文本
            previous_confidence: 上一步置信度（用于增量更新）
            alpha: EMA 更新速度（strengthener 时使用）
        """
        result = FeatureResult()

        # ── Layer 1: 规则层（4 个连续信号）──
        self._extract_rule_signals(evidence, result)

        # ── Layer 2: LLM 层（6 个布尔特征）──
        self._extract_llm_features(claim, evidence, result)

        # ── Step 3: 质量因子 Q ──
        result.quality_factor = (
            0.4 * result.source_reliability +
            0.3 * result.evidence_density +
            0.2 * result.temporal_freshness +
            0.1 * result.provenance_quality
        )

        # ── Step 4: LLM 支持分与反驳分 ──
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

        # ── Step 5: 原始置信度（加权混合）──
        semantic = result.support_score * (1 - result.refute_score)
        raw_conf = 0.6 * semantic + 0.4 * result.quality_factor

        # limitation 单独降级（不进 refute_score）
        if result.limitation:
            raw_conf *= 0.85

        result.raw_confidence = min(1.0, max(0.0, raw_conf))

        # ── Step 6: 矛盾强制覆盖 ──
        if result.direct_refute:
            result.state = "CONTESTED"
            result.final_confidence = min(result.raw_confidence, 0.6)
            return result

        # ── Step 7: 增量信念更新 ──
        result.final_confidence = self._incremental_update(
            result.raw_confidence, previous_confidence, alpha,
        )

        # ── Step 8: 状态判定 ──
        result.state = self._determine_state(result.final_confidence)

        return result

    # ── 规则层 ──────────────────────────────────────────

    def _extract_rule_signals(self, evidence: str, result: FeatureResult):
        """从 evidence 文本提取 4 个连续信号。"""
        if not evidence:
            result.source_reliability = 0.4
            result.evidence_density = 0.0
            result.temporal_freshness = 0.7
            result.provenance_quality = 0.5
            return

        text = evidence.lower()

        # source_reliability
        domains = re.findall(r'https?://([^\s/]+)', evidence)
        if domains:
            scores = [self._domain_score(d) for d in domains]
            result.source_reliability = sum(scores) / len(scores)
        else:
            result.source_reliability = self._keyword_reliability(text)

        # evidence_density: 按换行/句号/引用分隔的片段数
        segments = re.split(r'\n\n|(?<=[.。])\s+', evidence)
        segments = [s.strip() for s in segments if len(s.strip()) > 20]
        result.evidence_density = min(1.0, 0.3 + len(segments) * 0.2)  # 单片段也有 0.5

        # temporal_freshness
        years = re.findall(r'\b((?:19|20)\d{2})\b', evidence)
        if years:
            latest = max(int(y) for y in years)
            age = 2026 - latest
            result.temporal_freshness = round(1.0 / (1.0 + age), 4)
        else:
            result.temporal_freshness = 0.7  # 无年份时不惩罚（可能是永恒真理）

        # provenance_quality: 独立顶级域名数
        unique_tlds = set()
        for d in domains:
            parts = d.split(".")
            tld = ".".join(parts[-2:]) if len(parts) >= 2 else d
            unique_tlds.add(tld)
        result.provenance_quality = min(1.0, 0.4 + len(unique_tlds) * 0.2) if unique_tlds else 0.5

    def _domain_score(self, domain: str) -> float:
        """URL 域名 → 可靠性分数。"""
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
        """无 URL 时用关键词推断来源可靠性。"""
        for keywords, score in [
            (["官方", "政府", "who", "nih", "fda", "央行"], 0.9),
            (["研究", "论文", "期刊", "nature", "science", "pubmed"], 0.8),
            (["报告", "白皮书", "调查", "统计"], 0.7),
            (["新闻", "报道", "媒体", "记者"], 0.6),
            (["论坛", "社交媒体", "网友", "微博", "twitter"], 0.3),
        ]:
            if any(w in text for w in keywords):
                return score
        return 0.6  # 无明显特征时给中等偏上基线

    # ── LLM 层 ──────────────────────────────────────────

    def _extract_llm_features(self, claim: str, evidence: str, result: FeatureResult):
        """LLM 一次调用提取 6 个布尔特征。"""
        prompt = f"""你是一个事实验证助手。请基于以下【声明】和【新证据】，回答6个判断。输出一个JSON对象，只输出JSON，不要有其他文字。

声明：{claim}
新证据：{evidence[:1500]}

判断标准：
1. direct_support: 证据是否直接支持声明？（即证据与声明方向一致且没有矛盾）
2. new_info: 证据是否提供了先前未提及的新信息？（例如新数据、新案例、新观点）
3. logical_consistent: 证据与之前已知信息是否逻辑一致？
4. direct_refute: 证据是否明确反驳声明？（例如直接否定声明中的事实或推理）
5. limitation: 证据是否指出声明的局限性或例外条件？（例如"该方法有效但对老年人无效"）
6. error_outdated: 证据是否揭示声明中的信息是错误的或已过时？

输出格式：
{{"direct_support": true/false, "new_info": true/false, "logical_consistent": true/false, "direct_refute": true/false, "limitation": true/false, "error_outdated": true/false}}"""

        features = {fid: False for fid in LLM_FEATURES}

        try:
            response = self.llm_chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.05,
                max_tokens=256,
            )
            features = self._parse_features(response)
        except Exception as e:
            print(f"[WARN] LLM 特征提取失败: {e}")

        result.features = features

    def _parse_features(self, response: str) -> Dict[str, bool]:
        """从 LLM 回答中解析 6 个布尔特征。"""
        features = {fid: False for fid in LLM_FEATURES}

        # 尝试 JSON 解析
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

        # Fallback: 正则提取
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
        self,
        raw_conf: float,
        old_conf: Optional[float],
        alpha: float,
    ) -> float:
        """
        增量信念更新。

        - 无旧置信度：直接使用 raw_conf
        - strengthener（delta > +0.1）：EMA 平滑上升
        - weakener（delta < -0.1）：取 min，快速拉低
        - neutral：取平均，轻微移动
        """
        if old_conf is None:
            return raw_conf

        delta = raw_conf - old_conf

        if delta > 0.1:
            # strengthener: EMA
            return alpha * raw_conf + (1 - alpha) * old_conf
        elif delta < -0.1:
            # weakener: 快速拉低，对抗天花板
            return min(old_conf, raw_conf)
        else:
            # neutral: 轻微移动
            return (old_conf + raw_conf) / 2.0

    # ── 状态判定 ──────────────────────────────────────────

    def _determine_state(self, confidence: float) -> str:
        """根据置信度判定状态。"""
        if confidence >= 0.65:
            return "VERIFIED"
        elif confidence <= 0.25:
            return "UNCERTAIN"
        else:
            return "CONTESTED"


def extract_features_v4(
    claim: str,
    evidence: str,
    llm_chat_func=None,
    previous_confidence: Optional[float] = None,
    alpha: float = 0.5,
) -> Tuple[float, str, FeatureResult]:
    """
    便捷函数：一步完成特征提取 + 置信度计算。

    Returns:
        (confidence, state, result)
    """
    ext = FeatureExtractor(llm_chat_func)
    result = ext.extract(claim, evidence, previous_confidence, alpha)
    return result.final_confidence, result.state, result
