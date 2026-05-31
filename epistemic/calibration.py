# belief-state-runtime (c) 2026 hqzzdsda — MIT License
# https://github.com/hqzzdsda/belief-state-runtime

# -*- coding: utf-8 -*-
"""
Calibration v1 — 信念置信度校准。

核心问题：系统说 "conf=0.7"，实际正确率是否 ≈70%？
如果不是，confidence 需要被校准。

方法：
1. Platt Scaling   （Sigmoid 拟合，适合近似可信的置信度）
2. Isotonic Regression（保序回归，不假设分布，适合大数据）
3. Reliability Diagram + ECE （评估校准质量）
4. Online Bayesian Weight Update（可选：根据校准误差动态调整融合权重）

存储：calibration_data.jsonl  （每行: {"confidence": float, "correct": bool, "policy": str, "timestamp": str}）
"""

from __future__ import annotations
import json, math, os, pickle
from typing import List, Dict, Tuple, Optional, Callable
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from scipy.special import expit, logit
from scipy.optimize import minimize


_DEFAULT_DATA_PATH = os.path.join(os.path.dirname(__file__), "calibration_data.jsonl")
_BINS = 10
_MODEL_PATH = os.path.join(os.path.dirname(__file__), "calibration_model.pkl")


# ========== 数据收集 ==========

def log_calibration_sample(
    confidence: float,
    correct: bool,
    policy: str = "default",
    belief_id: Optional[str] = None,
    metadata: Optional[Dict] = None,
    data_path: str = _DEFAULT_DATA_PATH,
) -> None:
    """记录一条校准样本（在信念得到 Ground Truth 验证后调用）。"""
    record = {
        "confidence": round(float(confidence), 4),
        "correct": bool(correct),
        "policy": policy,
        "belief_id": belief_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if metadata:
        record["metadata"] = metadata

    with open(data_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_calibration_data(
    data_path: str = _DEFAULT_DATA_PATH,
    policy_filter: Optional[str] = None,
    min_samples: int = 20,
) -> Tuple[np.ndarray, np.ndarray]:
    """加载校准数据，返回 (confidences, corrects)。"""
    if not os.path.exists(data_path):
        return np.array([], dtype=np.float64), np.array([], dtype=bool)

    confs = []
    corrs = []
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if policy_filter and r.get("policy") != policy_filter:
                continue
            confs.append(r["confidence"])
            corrs.append(r["correct"])

    if len(confs) < min_samples:
        raise ValueError(
            f"校准数据不足：仅 {len(confs)} 条（需要 ≥ {min_samples} 条）。"
            f"请继续收集 Ground Truth 标注数据。"
        )

    return np.array(confs, dtype=np.float64), np.array(corrs, dtype=bool)


# ========== 评估指标 ==========

def compute_reliability_diagram(
    confidences: np.ndarray,
    corrects: np.ndarray,
    n_bins: int = _BINS,
) -> Dict:
    """计算 Reliability Diagram 数据 + ECE。"""
    bins = np.linspace(0, 1, n_bins + 1)
    bin_centers = (bins[:-1] + bins[1:]) / 2

    bin_indices = np.clip(np.digitize(confidences, bins) - 1, 0, n_bins - 1)

    accs = np.zeros(n_bins)
    counts = np.zeros(n_bins)

    for i in range(n_bins):
        mask = bin_indices == i
        cnt = int(mask.sum())
        counts[i] = cnt
        accs[i] = corrects[mask].mean() if cnt > 0 else np.nan

    valid = counts > 0
    if np.any(valid):
        ece = float(
            np.sum(counts[valid] * np.abs(accs[valid] - bin_centers[valid]))
            / np.sum(counts[valid])
        )
        mce = float(np.nanmax(np.abs(accs[valid] - bin_centers[valid])))
    else:
        ece = 0.0
        mce = 0.0

    return {
        "bins": bin_centers.tolist(),
        "accuracies": [float(a) if not np.isnan(a) else None for a in accs],
        "counts": counts.astype(int).tolist(),
        "ece": ece,
        "mce": mce,
    }


def evaluate_calibration(
    confidences: Optional[np.ndarray] = None,
    corrects: Optional[np.ndarray] = None,
    data_path: str = _DEFAULT_DATA_PATH,
    n_bins: int = _BINS,
    verbose: bool = True,
) -> Dict:
    """评估当前校准状态，打印报告。"""
    if confidences is None or corrects is None:
        confidences, corrects = load_calibration_data(data_path)

    diagram = compute_reliability_diagram(confidences, corrects, n_bins)

    if verbose:
        print("=== 校准评估报告 ===")
        print(f"ECE = {diagram['ece']:.4f}  (期望值校准误差，越小越好，理想值=0)")
        print(f"MCE = {diagram['mce']:.4f}  (最大校准误差)")
        print(f"样本数: {sum(diagram['counts'])}")
        print()
        print(f"{'置信度区间':>12} | {'实际正确率':>10} | {'样本数':>6}  {'校准状态'}")
        print("-" * 50)
        for i, (acc, cnt) in enumerate(zip(diagram['accuracies'], diagram['counts'])):
            if acc is None:
                continue
            lo = i / n_bins
            hi = (i + 1) / n_bins
            expected = (lo + hi) / 2
            diff = abs(acc - expected)
            marker = "✅" if diff < 0.1 else ("⚠️" if diff < 0.25 else "❌")
            print(f"[{lo:.1f}–{hi:.1f}] | {acc:>10.3f} | {cnt:>6}  {marker} (Δ={diff:+.3f})")
        print()
        if diagram['ece'] < 0.05:
            print("🟢 校准良好 (ECE < 0.05)")
        elif diagram['ece'] < 0.15:
            print("🟡 校准一般 (ECE = 0.05~0.15)，建议执行校准")
        else:
            print("🔴 校准较差 (ECE ≥ 0.15)，必须执行校准！")

    return diagram


# ========== Platt Scaling ==========

class PlattScaler:
    """
    Platt Scaling: P(correct | conf) = sigmoid(a * logit(conf) + b)
    拟合参数 a, b 使得 NLL 最小。适合小样本（≥20 条）。
    """

    def __init__(self):
        self.a: float = 1.0
        self.b: float = 0.0
        self.fitted_: bool = False

    def fit(self, confidences: np.ndarray, corrects: np.ndarray) -> "PlattScaler":
        eps = 1e-12
        conf_clipped = np.clip(confidences, eps, 1 - eps)
        y = corrects.astype(np.float64)

        def nll(params):
            a, b = params
            logits = logit(conf_clipped) * a + b
            p = np.clip(expit(logits), eps, 1 - eps)
            return -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))

        result = minimize(nll, x0=[1.0, 0.0], method="Nelder-Mead",
                         options={"maxiter": 1000, "xatol": 1e-6, "fatol": 1e-6})
        if not result.success:
            print(f"[warn] Platt 拟合未完全收敛: {result.message}")
        self.a, self.b = result.x
        self.fitted_ = True
        return self

    def transform(self, confidences: np.ndarray) -> np.ndarray:
        if not self.fitted_:
            raise RuntimeError("PlattScaler 未拟合，请先调用 fit()。")
        eps = 1e-12
        conf_clipped = np.clip(confidences, eps, 1 - eps)
        return expit(logit(conf_clipped) * self.a + self.b)

    def __repr__(self):
        return f"PlattScaler(a={self.a:.4f}, b={self.b:.4f})"


# ========== Isotonic Regression ==========

class IsotonicCalibrator:
    """
    保序回归校准。不假设 Sigmoid 形状，适合大样本（≥100 条）。
    依赖 sklearn（可选，若不可用则自动降级为 Platt）。
    """

    def __init__(self):
        self.x_: Optional[np.ndarray] = None
        self.y_: Optional[np.ndarray] = None
        self.fitted_: bool = False

    def fit(self, confidences: np.ndarray, corrects: np.ndarray) -> "IsotonicCalibrator":
        from sklearn.isotonic import IsotonicRegression
        model = IsotonicRegression(out_of_bounds="clip")
        model.fit(confidences, corrects.astype(np.float64))
        # 保存阶梯函数的断点
        self.x_ = model.X_thresholds_
        self.y_ = model.y_thresholds_
        self._model = model
        self.fitted_ = True
        return self

    def transform(self, confidences: np.ndarray) -> np.ndarray:
        if not self.fitted_:
            raise RuntimeError("IsotonicCalibrator 未拟合，请先调用 fit()。")
        return self._model.transform(confidences)

    def __repr__(self):
        return f"IsotonicCalibrator(fitted={self.fitted_}, n_knots={len(self.x_) if self.x_ is not None else 0})"


# ========== 自动校准 ==========

def auto_calibrate(
    confidences: Optional[np.ndarray] = None,
    corrects: Optional[np.ndarray] = None,
    data_path: str = _DEFAULT_DATA_PATH,
    method: str = "auto",
    test_ratio: float = 0.2,
    random_state: int = 42,
    save_model: bool = True,
) -> Tuple[Callable[[np.ndarray], np.ndarray], Dict]:
    """
    自动选择并拟合校准器，返回校准函数 + 报告。

    Returns:
        (calibrate_fn, report_dict)
        calibrate_fn: 输入 conf -> 校准后 conf（支持 np.ndarray 或 float）
    """
    if confidences is None or corrects is None:
        confidences, corrects = load_calibration_data(data_path)

    n = len(confidences)
    rng = np.random.RandomState(random_state)
    indices = rng.permutation(n)
    split = int(n * (1 - test_ratio))
    train_idx, test_idx = indices[:split], indices[split:]

    if method == "auto":
        method = "platt" if n < 100 else "isotonic"

    if method == "platt":
        calibrator = PlattScaler()
    elif method == "isotonic":
        try:
            import sklearn  # noqa: F401
            calibrator = IsotonicCalibrator()
        except ImportError:
            print("[warn] sklearn 不可用，自动降级为 Platt Scaling。")
            calibrator = PlattScaler()
            method = "platt"
    else:
        raise ValueError(f"未知方法: {method}")

    calibrator.fit(confidences[train_idx], corrects[train_idx])

    # 在测试集上评估
    test_conf = confidences[test_idx]
    test_corr = corrects[test_idx]
    calibrated = calibrator.transform(test_conf)

    diagram_before = compute_reliability_diagram(test_conf, test_corr)
    diagram_after = compute_reliability_diagram(calibrated, test_corr)

    def calibrate_fn(c):
        c_arr = np.array([c] if np.isscalar(c) else c, dtype=np.float64)
        result = calibrator.transform(c_arr)
        return float(result[0]) if np.isscalar(c) else result

    report = {
        "method": method,
        "n_train": int(len(train_idx)),
        "n_test": int(len(test_idx)),
        "ece_before": diagram_before["ece"],
        "ece_after": diagram_after["ece"],
        "improvement": diagram_before["ece"] - diagram_after["ece"],
        "mce_before": diagram_before["mce"],
        "mce_after": diagram_after["mce"],
    }

    print(f"[校准完成] 方法={method}")
    print(f"  ECE: {report['ece_before']:.4f} → {report['ece_after']:.4f} (改善 +{report['improvement']:.4f})")

    # 保存模型
    if save_model:
        with open(_MODEL_PATH, "wb") as f:
            pickle.dump({"method": method, "calibrator": calibrator}, f)
        print(f"  模型已保存至: {_MODEL_PATH}")

    return calibrate_fn, report


# ========== 在线贝叶斯权重更新 ==========

def bayesian_weight_update(
    policy_name: str = "default",
    calibration_data_path: str = _DEFAULT_DATA_PATH,
    prior_strength: float = 10.0,
    verbose: bool = True,
) -> Dict[str, float]:
    """
    根据校准结果，用 Beta-Bernoulli 模型更新信号权重。

    每个信号视为一个 "是否能预测正确性" 的 Bernoulli 变量。
    用 Beta(α, β) 先验，根据观测数据（信号值 > 中位数 且 belief 正确）更新后验。

    Returns:
        new_weights: {signal_name: new_weight}
    """
    from schemas.state import get_policy, SIGNAL_WEIGHTS

    try:
        confs, corrs = load_calibration_data(calibration_data_path, policy_filter=policy_name)
    except ValueError:
        if verbose:
            print("[贝叶斯更新] 数据不足，返回原权重（先验占主导）。")
        policy = get_policy(policy_name)
        return dict(policy.signal_weights)

    policy = get_policy(policy_name)
    current_weights = dict(policy.signal_weights)

    # 简化：用 final_confidence 和 correctness 的相关性来更新
    # 完整实现需要每个 signal 的历史值（从 signal_history 读取）
    new_weights = {}
    for name, w in current_weights.items():
        # Beta 先验：均值 = w，浓度 = prior_strength
        alpha_prior = w * prior_strength + 1.0
        beta_prior = (1 - w) * prior_strength + 1.0

        # 观测：该信号值高的 belief 是否更可能正确？
        # 这里用 final_confidence 作为 proxy（实际应替换为真实 signal 值）
        high_conf_mask = confs > np.median(confs)
        if high_conf_mask.sum() < 3:
            new_weights[name] = w  # 数据不足，保持原权重
            continue

        correct_high = corrs[high_conf_mask].mean()
        correct_low = corrs[~high_conf_mask].mean() if (~high_conf_mask).sum() >= 3 else 0.5

        # 该信号有区分度 → 提高权重；否则降低
        delta = (correct_high - correct_low) * 0.3  # 保守更新
        new_w = np.clip(w + delta, 0.0, 1.0)
        new_weights[name] = round(new_w, 4)

    if verbose:
        print("[贝叶斯权重更新]")
        for name in current_weights:
            old = current_weights[name]
            new = new_weights[name]
            arrow = "↑" if new > old else ("↓" if new < old else "=")
            print(f"  {name}: {old:.3f} {arrow} {new:.3f}")

    return new_weights


# ========== 验证校准效果 ==========

def verify_calibration(
    target_confidence: float = 0.7,
    n_bootstrap: int = 1000,
    data_path: str = _DEFAULT_DATA_PATH,
) -> Dict:
    """
    验证校准后 conf=X 的信念，实际正确率是否 ≈X%。
    用 Bootstrap 估计置信区间。
    """
    confs, corrs = load_calibration_data(data_path, min_samples=20)

    # 加载校准模型
    if not os.path.exists(_MODEL_PATH):
        print("[warn] 未找到校准模型，使用原始置信度。")
        calibrated_confs = confs
    else:
        with open(_MODEL_PATH, "rb") as f:
            model_data = pickle.load(f)
        calibrator = model_data["calibrator"]
        calibrated_confs = calibrator.transform(confs)

    # 找校准后 conf 在 target_confidence ±0.05 范围内的样本
    mask = np.abs(calibrated_confs - target_confidence) < 0.05
    if mask.sum() < 5:
        return {
            "target": target_confidence,
            "actual_accuracy": None,
            "n_samples": 0,
            "error": f"校准后 conf≈{target_confidence} 的样本不足（仅 {mask.sum()} 条）",
        }

    actual = corrs[mask].mean()
    n = int(mask.sum())

    # Bootstrap 95% CI
    boot_means = []
    for _ in range(n_bootstrap):
        idx = np.random.choice(n, size=n, replace=True)
        boot_means.append(corrs[mask][idx].mean())
    ci_lo = float(np.percentile(boot_means, 2.5))
    ci_hi = float(np.percentile(boot_means, 97.5))

    result = {
        "target": target_confidence,
        "actual_accuracy": float(actual),
        "n_samples": n,
        "95_ci": [ci_lo, ci_hi],
        "calibrated": os.path.exists(_MODEL_PATH),
    }

    print(f"[验证校准] conf={target_confidence} → 实际正确率 = {actual:.3f} "
          f"(95% CI [{ci_lo:.3f}, {ci_hi:.3f}], n={n})")
    if abs(actual - target_confidence) < 0.1:
        print("  ✅ 校准有效！")
    else:
        print(f"  ⚠️ 仍有偏差（期望 {target_confidence}，实际 {actual:.3f}）")

    return result


# ========== CLI / __init__.py 导出辅助 ==========

def cmd_evaluate(data_path: str = _DEFAULT_DATA_PATH) -> None:
    """命令行：评估当前校准状态。"""
    try:
        confs, corrs = load_calibration_data(data_path)
    except ValueError as e:
        print(f"[校准] {e}")
        return
    evaluate_calibration(confs, corrs)


def cmd_calibrate(data_path: str = _DEFAULT_DATA_PATH, method: str = "auto") -> None:
    """命令行：拟合并保存校准器。"""
    try:
        confs, corrs = load_calibration_data(data_path)
    except ValueError as e:
        print(f"[校准] {e}")
        return
    auto_calibrate(confs, corrs, method=method)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="信念置信度校准 CLI")
    parser.add_argument("action", choices=["evaluate", "calibrate", "verify"],
                        help="evaluate=评估现状, calibrate=拟合模型, verify=验证校准效果")
    parser.add_argument("--method", default="auto", help="platt | isotonic | auto")
    parser.add_argument("--target", type=float, default=0.7, help="验证目标置信度")
    args = parser.parse_args()

    if args.action == "evaluate":
        cmd_evaluate()
    elif args.action == "calibrate":
        cmd_calibrate(method=args.method)
    elif args.action == "verify":
        verify_calibration(target_confidence=args.target)
