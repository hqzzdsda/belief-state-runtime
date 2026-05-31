# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

# -*- coding: utf-8 -*-
"""
Signal Correlation Analysis v1 — 信号独立性诊断。

用途：
- compute_signal_correlations(): 对运行时收集的信号矩阵做 Pearson 相关
- report_correlations(): 格式化为文本报告
- plot_correlation_matrix(): 可视化热力图
- flag_redundant_signals(): 自动标记高度冗余信号对

设计原则：信号越独立，融合越可靠。高相关性 → 冗余 → 建议降权或合并。
"""

from __future__ import annotations
import json, os, math, warnings
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

import numpy as np

# matplotlib 可选（无头环境也能跑文本报告）
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except ImportError:
    _HAS_MPL = False

# 信号名称及其中文标签
SIGNAL_LABELS_CN: Dict[str, str] = {
    "self_confidence": "自评置信度",
    "reasoning_consistency": "推理一致性",
    "source_reliability": "源可靠性",
    "evidence_density": "证据密度",
    "contradiction_score": "矛盾评分",
    "temporal_decay": "时效衰减",
    "execution_success": "执行成功",
    "final_confidence": "最终置信度",
    "exploration_divergence": "探索发散度",
    "belief_history_consistency": "历史一致性",
}


def _collect_signal_matrix(
    beliefs: List[Dict],
    signal_names: Optional[List[str]] = None,
    include_history: bool = True,
) -> Tuple[np.ndarray, List[str]]:
    """
    从 belief list 中抽取信号矩阵。

    Returns:
        matrix: shape (N_samples, M_signals) —— 含 NaN 的行被剔除
        names: M 个信号名
    """
    if signal_names is None:
        # 按透出顺序排列
        signal_names = [
            "self_confidence", "reasoning_consistency", "source_reliability",
            "evidence_density", "contradiction_score", "temporal_decay",
            "execution_success", "final_confidence",
        ]

    rows = []
    for b in beliefs:
        signals = b.get("signals", {})
        row = [signals.get(name, np.nan) for name in signal_names]
        rows.append(row)

        # 也收集 signal_history（如果需要）
        if include_history:
            for hist_entry in b.get("signal_history", []):
                row_h = [hist_entry.get(name, np.nan) for name in signal_names]
                rows.append(row_h)

    if not rows:
        return np.empty((0, len(signal_names))), signal_names

    matrix = np.array(rows, dtype=np.float64)
    # 剔除全 NaN 的行
    mask = ~np.all(np.isnan(matrix), axis=1)
    matrix = matrix[mask]
    return matrix, signal_names


def compute_signal_correlations(
    beliefs: List[Dict],
    signal_names: Optional[List[str]] = None,
    include_history: bool = True,
    method: str = "pearson",
) -> Dict:
    """
    计算信号 Pearson 相关矩阵。

    Returns:
        {
            "matrix": list[list[float]],   # 相关系数方阵
            "labels": list[str],           # 中文标签
            "names": list[str],            # 英文名
            "n_samples": int,
            "n_signals": int,
            "method": str,
        }
    """
    M, names = _collect_signal_matrix(beliefs, signal_names, include_history)
    n_samples, n_signals = M.shape

    if n_samples < 3 or n_signals < 2:
        return {
            "matrix": [],
            "labels": [],
            "names": names,
            "n_samples": n_samples,
            "n_signals": n_signals,
            "method": method,
            "error": "样本不足（需要 ≥3 个样本）",
        }

    # 列填充中位数（处理 NaN）
    for j in range(n_signals):
        col = M[:, j]
        nan_mask = np.isnan(col)
        if np.any(nan_mask):
            col[nan_mask] = np.nanmedian(col[~nan_mask])

    # 剔除方差接近 0 的列（避免 np.corrcoef 除零警告）
    stds = np.std(M, axis=0)
    keep_cols = stds > 1e-8
    if not np.all(keep_cols):
        M = M[:, keep_cols]
        names = [names[j] for j in range(len(names)) if keep_cols[j]]

    n_signals = M.shape[1]
    if n_signals < 2:
        return {
            "matrix": [[0.0]],
            "labels": [SIGNAL_LABELS_CN.get(n, n) for n in names],
            "names": names,
            "n_samples": n_samples,
            "n_signals": n_signals,
            "method": method,
            "error": "有效信号不足（方差均为 0 或只剩 1 列）",
        }

    corr = np.corrcoef(M, rowvar=False)
    # 如果 corr 是标量（只有 1 列），转为 1x1 矩阵
    if np.ndim(corr) == 0:
        corr = np.array([[float(corr)]])

    return {
        "matrix": [[round(float(x), 3) for x in row] for row in corr],
        "labels": [SIGNAL_LABELS_CN.get(n, n) for n in names],
        "names": names,
        "n_samples": n_samples,
        "n_signals": n_signals,
        "method": method,
    }


def report_correlations(
    beliefs: List[Dict],
    signal_names: Optional[List[str]] = None,
    verbose: bool = True,
) -> str:
    """
    生成信号相关性文本报告。
    """
    result = compute_signal_correlations(beliefs, signal_names)
    if "error" in result:
        return f"[相关性报告] {result['error']}"

    lines = [
        f"=== 信号相关性报告 ===",
        f"样本数: {result['n_samples']} | 信号数: {result['n_signals']} | 方法: {result['method']}",
        "",
    ]

    # 矩阵
    names = result["names"]
    labels = result["labels"]
    mat = result["matrix"]

    # 表头
    header = f"{'信号':>18}" + "".join(f"{l:>10}" for l in labels)
    lines.append(header)
    lines.append("-" * len(header))

    for i, (n, l) in enumerate(zip(names, labels)):
        row_str = f"{l:>18}" + "".join(f"{mat[i][j]:10.3f}" for j in range(len(names)))
        lines.append(row_str)

    lines.append("")

    # 高相关度对
    high_pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            r = abs(mat[i][j])
            if r >= 0.6:
                high_pairs.append((labels[i], labels[j], mat[i][j]))

    if high_pairs:
        high_pairs.sort(key=lambda x: -abs(x[2]))
        lines.append(f"⚠ 高相关度信号对 (|r| ≥ 0.6)：")
        for a, b, r in high_pairs:
            level = "🔴" if abs(r) >= 0.8 else "🟡"
            lines.append(f"  {level} {a} ↔ {b}: r = {r:+.3f}")
        lines.append("  建议：考虑降权高相关信号以避免双重计数。")
    else:
        lines.append("✅ 未发现显著冗余信号对 (|r| < 0.6)")

    text = "\n".join(lines)
    if verbose:
        print(text)
    return text


def plot_correlation_matrix(
    beliefs: List[Dict],
    signal_names: Optional[List[str]] = None,
    output_path: str = "correlation_matrix.png",
    figsize: Tuple[int, int] = (10, 8),
    title: str = "Epistemic Signal Correlation Matrix",
) -> Optional[str]:
    """
    生成相关性热力图并保存为 PNG。
    """
    if not _HAS_MPL:
        print("[warn] matplotlib 不可用，无法生成热力图。")
        return None

    result = compute_signal_correlations(beliefs, signal_names)
    if "error" in result:
        print(f"[warn] {result['error']}，无法生成热力图。")
        return None

    labels = result["labels"]
    mat = np.array(result["matrix"])

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(mat, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")

    # 标注数值
    for i in range(len(labels)):
        for j in range(len(labels)):
            text = ax.text(j, i, f"{mat[i][j]:.2f}",
                           ha="center", va="center",
                           color="white" if abs(mat[i][j]) > 0.5 else "black",
                           fontsize=9)

    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=9)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_title(title, fontsize=14, fontweight="bold")

    plt.colorbar(im, ax=ax, shrink=0.8, label="Pearson r")
    plt.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"[ok] 热力图已保存至 {output_path}")
    return os.path.abspath(output_path)


def flag_redundant_signals(
    beliefs: List[Dict],
    threshold: float = 0.7,
    signal_names: Optional[List[str]] = None,
) -> List[Dict]:
    """
    自动标记超过阈值的冗余信号对。
    被标记的信号建议降权或合并以避免 double-counting。

    Returns:
        [
            {"signal_a": str, "signal_b": str, "correlation": float, "severity": "high"|"medium"},
            ...
        ]
    """
    result = compute_signal_correlations(beliefs, signal_names)
    if "error" in result:
        return []

    names = result["names"]
    labels = result["labels"]
    mat = result["matrix"]

    flags = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            r = mat[i][j]
            if abs(r) >= threshold:
                flags.append({
                    "signal_a": names[i],
                    "label_a": labels[i],
                    "signal_b": names[j],
                    "label_b": labels[j],
                    "correlation": round(r, 3),
                    "severity": "high" if abs(r) >= 0.85 else "medium",
                })

    flags.sort(key=lambda x: -abs(x["correlation"]))
    return flags


# ========== Runtime 日志收集 ==========

def save_correlation_run(
    correlations: Dict,
    output_path: str = "correlation_result.json",
) -> str:
    """保存相关性分析结果为 JSON（供 supabase log 或前端读取）。"""
    data = {
        "matrix": correlations.get("matrix", []),
        "labels": correlations.get("labels", []),
        "names": correlations.get("names", []),
        "n_samples": correlations.get("n_samples", 0),
        "n_signals": correlations.get("n_signals", 0),
        "method": correlations.get("method", "pearson"),
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return os.path.abspath(output_path)