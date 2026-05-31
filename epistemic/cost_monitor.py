# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

# -*- coding: utf-8 -*-
"""
API 成本监控 v1 — 跟踪每轮验证的 API 调用成本。

DeepSeek 定价（2025-05，参考 deepseek.com/pricing）：
  - deepseek-chat (Flash):  输入 CNY1/M tokens, 输出 CNY2/M tokens
  - deepseek-reasoner (Pro): 输入 CNY4/M tokens, 输出 CNY16/M tokens

功能：
1. 逐条记录 API 调用（model, tokens, cost）
2. 按 round / policy / model 聚合
3. 成本预算控制：到达预算上限自动降级（Pro → Flash / 减少验证频率）
4. 输出成本摘要（供 Dashboard 展示）
"""

from __future__ import annotations
import json, os, time
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict
from datetime import datetime, timezone


# ── 定价表（元 / 百万 tokens）──────────────────────────────────────────────
PRICING = {
    # model_id: (input_per_M, output_per_M)  单位：CNY
    "deepseek-chat":       (1.0, 2.0),      # Flash
    "deepseek-reasoner":   (4.0, 16.0),     # Pro
    "deepseek-coder":      (1.0, 2.0),      # Flash variant
}

# 别名映射
_MODEL_ALIASES = {
    "deepseek-chat": "Flash",
    "deepseek-reasoner": "Pro",
    "deepseek-coder": "Flash",
}

_DEFAULT_LOG_PATH = os.path.join(
    os.path.dirname(__file__), "cost_log.jsonl"
)


@dataclass
class APICall:
    """单次 API 调用记录。"""
    model: str
    tokens_in: int
    tokens_out: int
    cost_cny: float
    round_num: int
    policy: str
    node: str             # generate / verify / collect / ...
    timestamp: float = field(default_factory=time.time)


class CostMonitor:
    """API 成本监控器（单例模式）。"""

    _instance: Optional["CostMonitor"] = None

    def __init__(self, log_path: str = _DEFAULT_LOG_PATH):
        self.log_path = log_path
        self.calls: List[APICall] = []
        self._round_costs: Dict[int, float] = defaultdict(float)
        self._round_calls: Dict[int, int] = defaultdict(int)
        self._model_costs: Dict[str, float] = defaultdict(float)
        self._policy_costs: Dict[str, float] = defaultdict(float)
        self._total_cost: float = 0.0
        self._budget_cny: Optional[float] = None
        self._budget_exceeded: bool = False

    @classmethod
    def get_instance(cls) -> "CostMonitor":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """重置单例（测试用）。"""
        cls._instance = None

    def set_budget(self, budget_cny: float) -> None:
        """设置总预算上限（元）。"""
        self._budget_cny = budget_cny
        self._budget_exceeded = False

    def record(
        self,
        model: str,
        tokens_in: int,
        tokens_out: int,
        round_num: int = 0,
        policy: str = "default",
        node: str = "unknown",
    ) -> float:
        """
        记录一次 API 调用，返回本次成本（元）。

        自动计算成本并聚合统计。
        """
        pricing = PRICING.get(model, (2.0, 4.0))  # 未知模型用默认价
        cost = (tokens_in * pricing[0] + tokens_out * pricing[1]) / 1_000_000

        call = APICall(
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_cny=cost,
            round_num=round_num,
            policy=policy,
            node=node,
        )

        self.calls.append(call)
        self._round_costs[round_num] += cost
        self._round_calls[round_num] += 1
        self._model_costs[model] += cost
        self._policy_costs[policy] += cost
        self._total_cost += cost

        # 预算检查
        if self._budget_cny and self._total_cost >= self._budget_cny:
            self._budget_exceeded = True

        # 持久化
        self._append_log(call)

        return cost

    def budget_exceeded(self) -> bool:
        return self._budget_exceeded

    def get_total_cost(self) -> float:
        return self._total_cost

    def get_round_cost(self, round_num: int) -> float:
        return self._round_costs.get(round_num, 0.0)

    def get_summary(self) -> Dict:
        """
        成本摘要（供 Dashboard 展示）。

        Returns:
            {
                "total_cost_cny": float,
                "total_calls": int,
                "avg_cost_per_round": float,
                "by_model": {"Flash": cost, "Pro": cost},
                "by_policy": {"default": cost, ...},
                "round_costs": [round_0_cost, round_1_cost, ...],
                "budget_remaining": Optional[float],
                "budget_exceeded": bool,
            }
        """
        n_rounds = max(self._round_costs.keys(), default=-1) + 1
        avg_per_round = self._total_cost / max(n_rounds, 1)

        by_model_alias = {}
        for model, cost in self._model_costs.items():
            alias = _MODEL_ALIASES.get(model, model)
            by_model_alias[alias] = by_model_alias.get(alias, 0.0) + cost

        round_costs = [self._round_costs.get(r, 0.0) for r in range(n_rounds)]

        budget_remaining = None
        if self._budget_cny:
            budget_remaining = max(0.0, self._budget_cny - self._total_cost)

        return {
            "total_cost_cny": round(self._total_cost, 6),
            "total_calls": len(self.calls),
            "avg_cost_per_round": round(avg_per_round, 6),
            "by_model": {k: round(v, 6) for k, v in by_model_alias.items()},
            "by_policy": {k: round(v, 6) for k, v in self._policy_costs.items()},
            "round_costs": [round(c, 6) for c in round_costs],
            "budget_remaining": round(budget_remaining, 6) if budget_remaining is not None else None,
            "budget_exceeded": self._budget_exceeded,
        }

    def estimate_verify_cost(
        self,
        n_beliefs: int,
        deep_ratio: float = 0.3,
        model: str = "deepseek-chat",
    ) -> float:
        """
        预估一次验证轮次的成本。

        Args:
            n_beliefs: 待验证信念数
            deep_ratio: 深度验证比例
            model: 默认模型
        """
        # 经验值：单次信号提取 ≈ 500 input + 200 output tokens
        # 深度验证 ≈ 1500 input + 500 output tokens
        LIGHT_TOKENS = (500, 200)
        DEEP_TOKENS = (1500, 500)

        n_deep = int(n_beliefs * deep_ratio)
        n_light = n_beliefs - n_deep

        pricing = PRICING.get(model, (2.0, 4.0))
        light_cost = n_light * (LIGHT_TOKENS[0] * pricing[0] + LIGHT_TOKENS[1] * pricing[1]) / 1_000_000
        deep_cost = n_deep * (DEEP_TOKENS[0] * pricing[0] + DEEP_TOKENS[1] * pricing[1]) / 1_000_000

        return light_cost + deep_cost

    def suggest_cost_reduction(self) -> List[str]:
        """根据当前成本分布，提出降本建议。"""
        suggestions = []
        summary = self.get_summary()

        # 1. Pro 模型占比
        pro_cost = summary["by_model"].get("Pro", 0.0)
        total = summary["total_cost_cny"]
        if total > 0 and pro_cost / total > 0.5:
            suggestions.append(
                f"Pro 模型占总成本 {pro_cost/total:.0%}，"
                f"建议对低优先级信念降级为 Flash 模型"
            )

        # 2. 单轮成本过高
        if summary["round_costs"]:
            max_round = max(summary["round_costs"])
            avg_round = summary["avg_cost_per_round"]
            if max_round > avg_round * 3:
                suggestions.append(
                    f"单轮最高成本 CNY{max_round:.4f} 是平均的 {max_round/avg_round:.1f}x，"
                    f"检查该轮是否有过多深度验证"
                )

        # 3. 预算预警
        if summary["budget_remaining"] is not None and summary["budget_remaining"] < total * 0.2:
            suggestions.append(
                f"预算剩余 CNY{summary['budget_remaining']:.4f} (< 20%)，"
                f"建议减少验证频率或降级模型"
            )

        if not suggestions:
            suggestions.append("成本控制良好，无需调整 [OK]")

        return suggestions

    def _append_log(self, call: APICall) -> None:
        """追加一条日志到 JSONL。"""
        record = {
            "model": call.model,
            "tokens_in": call.tokens_in,
            "tokens_out": call.tokens_out,
            "cost_cny": round(call.cost_cny, 8),
            "round": call.round_num,
            "policy": call.policy,
            "node": call.node,
            "timestamp": datetime.fromtimestamp(
                call.timestamp, tz=timezone.utc
            ).isoformat(),
        }
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass  # 日志写入失败不影响主流程


# ── 成本感知采样策略 ──────────────────────────────────────────────────

class CostAwareSampler:
    """
    根据预算和成本控制验证频率和深度。

    策略：
    1. 预算充足 → 正常验证
    2. 预算紧张 → 减少深度验证比例，降低一致性采样数
    3. 预算耗尽 → 仅做 light 验证
    """

    def __init__(self, monitor: Optional[CostMonitor] = None):
        self.monitor = monitor or CostMonitor.get_instance()

    def should_deep_verify(
        self,
        belief: dict,
        round_num: int,
        default_interval: int = 3,
    ) -> bool:
        """根据成本状态决定是否深度验证。"""
        # 预算耗尽 → 不做深度验证
        if self.monitor.budget_exceeded():
            return False

        # 预算紧张 → 降低频率
        summary = self.monitor.get_summary()
        if summary["budget_remaining"] is not None:
            remaining_pct = summary["budget_remaining"] / max(
                self.monitor._budget_cny or 1.0, 1.0
            )
            if remaining_pct < 0.2:
                # 仅在 round 0 做深度验证
                return round_num == 0
            elif remaining_pct < 0.5:
                # 频率减半
                return round_num % (default_interval * 2) == 0

        # 正常策略
        return round_num % default_interval == 0 or round_num == 0

    def get_consistency_samples(self, default: int = 3) -> int:
        """根据成本状态返回一致性采样数。"""
        if self.monitor.budget_exceeded():
            return 1
        summary = self.monitor.get_summary()
        if summary["budget_remaining"] is not None:
            remaining_pct = summary["budget_remaining"] / max(
                self.monitor._budget_cny or 1.0, 1.0
            )
            if remaining_pct < 0.3:
                return max(1, default - 1)
        return default

    def recommend_model(self, belief: dict, default_model: str) -> str:
        """根据信念优先级和预算推荐模型。"""
        if self.monitor.budget_exceeded():
            return "deepseek-chat"  # 降级为 Flash

        # 高矛盾 / 高优先级信念用 Pro
        signals = belief.get("signals", {})
        if signals.get("contradiction_score", 0) > 0.5:
            return "deepseek-reasoner"

        # 低置信度用 Pro
        if belief.get("final_confidence", 0.5) < 0.4:
            return "deepseek-reasoner"

        # 其余用默认
        return default_model


# ── 便捷函数 ──────────────────────────────────────────────────────────

def get_cost_monitor() -> CostMonitor:
    """获取全局 CostMonitor 单例。"""
    return CostMonitor.get_instance()


def format_cost_report(summary: Dict) -> str:
    """格式化成本报告（供 Dashboard / CLI 展示）。"""
    lines = [
        "=== API 成本报告 ===",
        "总成本: CNY{:.6f}".format(summary["total_cost_cny"]),
        "总调用: {} 次".format(summary["total_calls"]),
        "平均每轮: CNY{:.6f}".format(summary["avg_cost_per_round"]),
        "",
    ]

    if summary["by_model"]:
        lines.append("按模型:")
        for model, cost in summary["by_model"].items():
            lines.append("  {}: CNY{:.6f}".format(model, cost))

    if summary["by_policy"]:
        lines.append("")
        lines.append("按策略:")
        for policy, cost in summary["by_policy"].items():
            lines.append("  {}: CNY{:.6f}".format(policy, cost))

    if summary["round_costs"]:
        lines.append("")
        lines.append("逐轮成本:")
        for i, c in enumerate(summary["round_costs"]):
            bar = "█" * max(1, int(c / max(summary["round_costs"]) * 30))
            lines.append("  R{:>2}: CNY{:.4f} {}".format(i, c, bar))

    if summary["budget_remaining"] is not None:
        lines.append("")
        lines.append("预算剩余: CNY{:.4f}".format(summary["budget_remaining"]))
        lines.append("预算状态: {}".format(
            "❌ 已超支" if summary["budget_exceeded"] else "✅ 正常"
        ))

    return "\n".join(lines)
