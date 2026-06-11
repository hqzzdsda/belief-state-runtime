# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

# -*- coding: utf-8 -*-
"""
belief-state-runtime v2 — 通用信念更新引擎

规则层（4 个连续信号）+ LLM 层（6 个布尔特征）→ v2 投影层（4 重约束 + 公式化置信区间）

v2 新增（相比 v1）：
  - ProjectionConfig：可配置阈值 + 3 档预设（standard/conservative/permissive）
  - 4 重约束：矛盾上限、溯源门禁、时效门禁、密度底线
  - 公式化置信区间：(1-Q)×base + min/√n_eff
  - 历史声明豁免：自动检测历史事实，跳过时效惩罚
  - veto_reasons 输出：明确告知为什么置信度被限制
  - 零额外 LLM 调用，零外部依赖

设计原则：
  - 规则层提供确定性、可复现的基础信号
  - LLM 仅做最必要的语义判断（6 个布尔值）
  - v2 投影层负责约束、区间计算和状态判定
  - 不依赖外部标签，根据新旧置信度差值自动驱动更新
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


# ── v2: 投影配置 ──────────────────────────────────────────

@dataclass
class ProjectionConfig:
    """参数化策略配置 — 替代 v1 的硬编码阈值。

    三种预设覆盖所有场景，无需完整版 5 种 Policy 的复杂度。
    """

    # ── 阈值 ──
    verify_threshold: float = 0.70        # >= 此值为 VERIFIED
    contest_threshold: float = 0.25       # <= 此值为 UNCERTAIN（中间 = CONTESTED）

    # ── 约束参数 ──

    # 约束 1: 矛盾上限
    contradiction_cap: float = 0.55       # 有反驳时的置信度上限

    # 约束 2: 溯源质量门禁
    provenance_cap: float = 0.60          # 来源质量低时的置信度上限
    min_provenance_quality: float = 0.55  # 门禁阈值

    # 约束 3: 时效门禁
    decay_threshold: float = 0.40         # freshness 低于此 = 过期
    temporal_cap: float = 0.50            # 过期证据的置信度上限

    # 约束 4: 证据密度底线
    density_floor: float = 0.30           # density 低于此 = 太稀疏
    density_cap: float = 0.55             # 低密度证据的置信度上限

    # ── 置信区间参数 ──
    uncertainty_base: float = 0.5         # (1-quality) 的缩放系数
    uncertainty_min: float = 0.1          # 1/√n_eff 的缩放系数

    # ── 增量更新 ──
    alpha: float = 0.5                    # strengthener 的混合系数

    # ── 预设 ──

    @classmethod
    def standard(cls) -> "ProjectionConfig":
        """默认均衡策略。通用评估场景。"""
        return cls()

    @classmethod
    def conservative(cls) -> "ProjectionConfig":
        """高阈值严格策略。高风险场景（金融、医疗、法律）。"""
        return cls(
            verify_threshold=0.78, contest_threshold=0.30,
            contradiction_cap=0.50, provenance_cap=0.55,
            min_provenance_quality=0.60, decay_threshold=0.35,
            temporal_cap=0.50, density_floor=0.35,
            uncertainty_base=0.55, uncertainty_min=0.12,
        )

    @classmethod
    def permissive(cls) -> "ProjectionConfig":
        """低阈值宽松策略。低风险场景（头脑风暴、探索性研究）。"""
        return cls(
            verify_threshold=0.62, contest_threshold=0.20,
            contradiction_cap=0.60, provenance_cap=0.65,
            min_provenance_quality=0.45, decay_threshold=0.30,
            temporal_cap=0.55, density_floor=0.20,
            uncertainty_base=0.40, uncertainty_min=0.08,
        )


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
    final_confidence: float = 0.5      # 投影后的最终置信度
    state: str = "UNCERTAIN"           # VERIFIED / CONTESTED / UNCERTAIN
    direct_refute: bool = False        # 是否触发矛盾覆盖
    limitation: bool = False           # 是否有局限性

    # v2 新增字段
    confidence_lower: float = 0.0      # 置信区间下界
    confidence_upper: float = 1.0      # 置信区间上界
    veto_reasons: list = field(default_factory=list)  # 触发的约束列表
    cap_applied: float = 1.0           # 应用的置信度上限

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
            "confidence_lower": round(self.confidence_lower, 4),
            "confidence_upper": round(self.confidence_upper, 4),
            "state": self.state,
            "direct_refute": self.direct_refute,
            "limitation": self.limitation,
            "veto_reasons": self.veto_reasons,
            "cap_applied": round(self.cap_applied, 4),
        }


class FeatureExtractor:
    """
    通用信念更新引擎 v2。

    用法:
        ext = FeatureExtractor()
        result = ext.extract(claim, evidence)
        # 增量更新:
        result2 = ext.extract(claim, new_evidence, previous_confidence=result.final_confidence)
        # 保守策略:
        result = ext.extract(claim, evidence, config=ProjectionConfig.conservative())
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
        config: Optional[ProjectionConfig] = None,
    ) -> FeatureResult:
        """
        提取特征并计算置信度。

        Args:
            claim: 声明文本
            evidence: 证据文本
            previous_confidence: 上一步置信度（用于增量更新）
            alpha: EMA 更新速度（strengthener 时使用，config 中 alpha 优先）
            config: v2 投影配置。None 使用 standard 预设。
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

        # ── v2: 投影层（取代 v1 的 _determine_state + 固定区间）──
        cfg = config or ProjectionConfig()
        self._project(result, claim, previous_confidence, cfg)

        return result

    # ── v2 投影层 ──────────────────────────────────────────

    def _is_historical_claim(self, claim: str) -> bool:
        """检测声明是否指向历史/过去事件。

        历史声明（如"罗马帝国于476年灭亡"）应豁免时效惩罚，
        因为证据中的年份是事件时间坐标，而非证据过时的标志。
        但如果声明被反驳，则时效仍然重要——挑战需要新证据。
        """
        if not claim:
            return False

        text = claim.lower()

        # 过去时动词和历史事件标记（中英文）
        past_tense_words = {
            "was", "were", "developed", "discovered", "invented", "created",
            "established", "founded", "occurred", "happened", "began",
            "ended", "completed", "published", "launched", "introduced",
            "built", "constructed", "formed", "originated",
            "fought", "won", "lost", "died", "born", "ruled", "reigned",
            "produced", "wrote", "painted", "composed", "designed",
            "previously", "originally", "historically",
            "discovered", "invented", "created",
            "成立于", "建于", "发生于", "始于", "终于",
            "出生", "逝世", "去世", "灭亡", "建立",
            "发明", "发现", "创造", "出版", "发表",
            "统一", "建国", "改革开放",
        }
        if any(word in text for word in past_tense_words):
            return True

        # 包含过去年份（19xx 或 2024 及之前）
        year_pattern = re.compile(r'\b(19\d{2}|200\d|201\d|202[0-4])\b')
        if year_pattern.search(text):
            return True

        return False

    def _project(
        self,
        result: FeatureResult,
        claim: str,
        prev_conf: Optional[float],
        cfg: ProjectionConfig,
    ):
        """v2 投影层：4 重约束 + 公式化置信区间 + 可配置状态判定。"""
        scalar = result.raw_confidence
        cap = 1.0
        result.veto_reasons = []

        # ── 约束 1: 矛盾上限 ──
        # 证据有反驳或矛盾时，对置信度设硬上限
        if result.refute_score >= cfg.contest_threshold:
            cap = min(cap, cfg.contradiction_cap)
            result.veto_reasons.append("contradiction_capped")

        # 强矛盾：反驳碾压支持 → 强制 CONTESTED
        if result.refute_score > result.support_score * 2:
            result.state = "CONTESTED"
            result.veto_reasons.append("contradiction_dominates")

        # 直接反驳：立即 CONTESTED，短路返回
        if result.direct_refute:
            result.state = "CONTESTED"
            scalar = min(scalar, min(cap, 0.60))
            result.final_confidence = scalar
            result.confidence_lower = 0.0
            result.confidence_upper = scalar
            result.cap_applied = cap
            return  # 直接反驳是确定的，不需要继续

        # ── 约束 2: 溯源质量门禁 ──
        if result.quality_factor < cfg.min_provenance_quality:
            cap = min(cap, cfg.provenance_cap)
            result.veto_reasons.append("provenance_gated")

        # ── 约束 3: 时效门禁 ──
        # 历史声明仅在被挑战时才受时效约束
        is_historical = self._is_historical_claim(claim)
        is_challenged = result.refute_score > result.support_score
        skip_temporal = is_historical and not is_challenged
        if not skip_temporal and result.temporal_freshness < cfg.decay_threshold:
            cap = min(cap, cfg.temporal_cap)
            result.veto_reasons.append("temporal_decayed")
            # 过期证据 → 即使当前 VERIFIED 也降级
            if result.state == "VERIFIED":
                result.state = "CONTESTED"

        # ── 约束 4: 证据密度底线 ──
        if result.evidence_density < cfg.density_floor:
            cap = min(cap, cfg.density_cap)
            result.veto_reasons.append("density_floor")

        # ── 应用 cap ──
        scalar = min(scalar, cap)
        result.cap_applied = cap

        # ── 增量更新（保留 v1 逻辑）──
        if prev_conf is not None:
            scalar = self._incremental_update(scalar, prev_conf, cfg.alpha)

        result.final_confidence = scalar

        # ── 公式化置信区间 ──
        n_eff = max(int(result.evidence_density * 10), 1)
        uncertainty_margin = (
            (1.0 - result.quality_factor) * cfg.uncertainty_base +
            cfg.uncertainty_min / math.sqrt(n_eff)
        )
        result.confidence_lower = max(scalar - uncertainty_margin, 0.0)
        result.confidence_upper = min(scalar + uncertainty_margin, cap)

        # ── 状态判定（如果约束尚未设定）──
        if result.state != "CONTESTED":
            cannot_verify = (
                result.quality_factor < cfg.min_provenance_quality or
                result.evidence_density < cfg.density_floor
            )
            if scalar >= cfg.verify_threshold and not cannot_verify:
                result.state = "VERIFIED"
            elif scalar <= cfg.contest_threshold:
                result.state = "UNCERTAIN"
            else:
                result.state = "CONTESTED"

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
        result.evidence_density = min(1.0, 0.3 + len(segments) * 0.2)

        # temporal_freshness
        years = re.findall(r'(?<!\d)((?:19|20)\d{2})(?!\d)', evidence)
        if years:
            latest = max(int(y) for y in years)
            age = 2026 - latest
            result.temporal_freshness = round(1.0 / (1.0 + age), 4)
        else:
            result.temporal_freshness = 0.7  # 无年份时不惩罚

        # provenance_quality: 独立顶级域名数
        unique_tlds = set()
        for d in domains:
            parts = d.split(".")
            tld = ".".join(parts[-2:]) if len(parts) >= 2 else d
            unique_tlds.add(tld)
        result.provenance_quality = min(1.0, 0.4 + len(unique_tlds) * 0.2) if unique_tlds else 0.5

    def _domain_score(self, domain: str) -> float:
        """URL 域名 → 可靠性分数。v2 扩展了域名列表。"""
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
        """无 URL 时用关键词推断来源可靠性。v2 扩展了中英文关键词。"""
        for keywords, score in [
            (["official", "government", "who", "nih", "fda", "央行", "官方", "政府",
              "交通运输部", "国家统计局", "卫健委", "国务院", "工信部", "财政部", "审计"], 0.9),
            (["research", "study", "journal", "nature", "science", "研究", "论文", "期刊"], 0.8),
            (["report", "survey", "statistics", "报告", "白皮书", "调查", "统计"], 0.7),
            (["news", "reported", "新闻", "报道", "媒体"], 0.6),
            (["forum", "social media", "twitter", "reddit", "论坛", "社交媒体", "网友",
              "telegram", "博客", "贴吧", "小红书", "匿名", "帖子", "笔记", "微信群",
              "知乎", "微博", "bilibili", "抖音", "快手"], 0.3),
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

    # ── 状态判定（v1 兼容，新代码请走 _project）──

    def _determine_state(self, confidence: float) -> str:
        """v1 兼容的状态判定。新代码请使用 _project()。"""
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
    config: Optional[ProjectionConfig] = None,
) -> Tuple[float, str, FeatureResult]:
    """
    便捷函数：一步完成特征提取 + 置信度计算。

    Returns:
        (confidence, state, result)
    """
    ext = FeatureExtractor(llm_chat_func)
    result = ext.extract(claim, evidence, previous_confidence, alpha, config)
    return result.final_confidence, result.state, result
