"""
v1 vs v2 belief-assessor 完整对比
对 54 条测试数据集做 v1 ↔ v2 对比
"""
import sys, json, os, glob, re, math
from dataclasses import dataclass, field
from typing import Dict, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
from assess import _compute_from_features as v2_compute, ProjectionConfig

DATASETS_DIR = os.path.join(os.path.dirname(__file__), "tests")

# ════════════════════════════════════════════════════════════
# v1 完整复刻（精确匹配原始代码逻辑，不调用原始模块）
# ════════════════════════════════════════════════════════════

V1_KEYWORDS = [
    (["official", "government", "who", "nih", "fda", "央行", "官方", "政府"], 0.9),
    (["research", "study", "journal", "nature", "science", "研究", "论文", "期刊"], 0.8),
    (["report", "survey", "statistics", "报告", "白皮书", "调查", "统计"], 0.7),
    (["news", "reported", "新闻", "报道", "媒体"], 0.6),
    (["forum", "social media", "twitter", "论坛", "社交媒体", "网友"], 0.3),
]

V1_DOMAINS = [
    ("gov", 0.9), ("edu", 0.9), ("who.int", 0.9),
    ("pubmed.ncbi", 0.9), ("nature.com", 0.9), ("science.org", 0.9),
    ("reuters.com", 0.7), ("bbc.com", 0.7), ("apnews.com", 0.7),
    ("nytimes.com", 0.7), ("theguardian.com", 0.7),
    ("arxiv.org", 0.6), ("wikipedia.org", 0.5),
    ("twitter.com", 0.3), ("x.com", 0.3), ("reddit.com", 0.3),
]

def v1_source(evidence: str) -> float:
    if not evidence:
        return 0.4
    domains = re.findall(r'https?://([^\s/]+)', evidence)
    if domains:
        scores = []
        for d in domains:
            d = d.lower()
            for pattern, score in V1_DOMAINS:
                if pattern in d:
                    scores.append(score)
                    break
            else:
                if d.endswith(".gov") or d.endswith(".edu"):
                    scores.append(0.9)
                elif d.endswith(".org"):
                    scores.append(0.6)
                else:
                    scores.append(0.5)
        return sum(scores) / len(scores)
    text = evidence.lower()
    for keywords, score in V1_KEYWORDS:
        if any(w in text for w in keywords):
            return score
    return 0.6

def v1_density(evidence: str) -> float:
    if not evidence:
        return 0.0
    segments = re.split(r'\n\n|(?<=[.。])\s+', evidence)
    segments = [s.strip() for s in segments if len(s.strip()) > 20]
    return min(1.0, 0.3 + len(segments) * 0.2)

def v1_temporal(evidence: str) -> float:
    if not evidence:
        return 0.7
    years = re.findall(r'\b((?:19|20)\d{2})\b', evidence)
    if years:
        latest = max(int(y) for y in years)
        age = 2026 - latest
        return round(1.0 / (1.0 + age), 4)
    return 0.7

def v1_provenance(evidence: str) -> float:
    domains = re.findall(r'https?://([^\s/]+)', evidence)
    if domains:
        unique_tlds = set()
        for d in domains:
            parts = d.split(".")
            tld = ".".join(parts[-2:]) if len(parts) >= 2 else d
            unique_tlds.add(tld)
        return min(1.0, 0.4 + len(unique_tlds) * 0.2)
    return 0.5

def v1_incremental(raw_conf, old_conf, alpha=0.5):
    if old_conf is None:
        return raw_conf
    delta = raw_conf - old_conf
    if delta > 0.1:
        return alpha * raw_conf + (1 - alpha) * old_conf
    elif delta < -0.1:
        return min(old_conf, raw_conf)
    else:
        return (old_conf + raw_conf) / 2.0

def v1_state(conf):
    if conf >= 0.65:
        return "VERIFIED"
    elif conf <= 0.25:
        return "UNCERTAIN"
    return "CONTESTED"

def v1_compute(claim, evidence, features, prev_conf=None):
    """Exact v1 logic."""
    src = v1_source(evidence)
    dens = v1_density(evidence)
    temp = v1_temporal(evidence)
    prov = v1_provenance(evidence)

    qf = 0.4 * src + 0.3 * dens + 0.2 * temp + 0.1 * prov

    f = features
    support = (
        (1.0 if f.get("direct_support") else 0.0) +
        (0.5 if f.get("new_info") else 0.0) +
        (0.3 if f.get("logical_consistent") else 0.0)
    ) / 1.8

    refute = (
        (1.0 if f.get("direct_refute") else 0.0) +
        (0.6 if f.get("error_outdated") else 0.0)
    ) / 1.6

    dref = f.get("direct_refute", False)
    lim = f.get("limitation", False)

    semantic = support * (1 - refute)
    raw = 0.6 * semantic + 0.4 * qf
    if lim:
        raw *= 0.85
    raw = min(1.0, max(0.0, raw))

    # V1: direct_refute early exit
    if dref:
        return {
            "state": "CONTESTED",
            "confidence": round(min(raw, 0.6), 4),
            "quality_factor": round(qf, 3),
            "support_score": round(support, 3),
            "refute_score": round(refute, 3),
            "veto_reasons": ["direct_refute"],
            "features": features,
            "source": src, "density": dens, "temporal": temp, "provenance": prov,
        }

    final = v1_incremental(raw, prev_conf)
    st = v1_state(final)

    return {
        "state": st,
        "confidence": round(final, 4),
        "quality_factor": round(qf, 3),
        "support_score": round(support, 3),
        "refute_score": round(refute, 3),
        "veto_reasons": [],
        "features": features,
        "source": src, "density": dens, "temporal": temp, "provenance": prov,
    }

def v1_compute_chain(claim, evidence_steps, features_steps):
    """Run v1 incremental chain."""
    prev = None
    results = []
    for ev, ft in zip(evidence_steps, features_steps):
        r = v1_compute(claim, ev, ft, prev)
        results.append(r)
        prev = r["confidence"]
    return results


# ════════════════════════════════════════════════════════════
# 运行对比
# ════════════════════════════════════════════════════════════

def load_datasets():
    datasets = []
    for fp in sorted(glob.glob(os.path.join(DATASETS_DIR, "dataset_*.json"))):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
            datasets.append(data)
    return datasets

SEP = "─" * 100

def run_comparison():
    datasets = load_datasets()
    print(f"加载 {len(datasets)} 个数据集")

    diffs = {}
    all_v1 = []; all_v2 = []

    for dataset in datasets:
        name = dataset.get("name", "?")
        typ = dataset.get("type", "parametric")
        print(f"\n{'='*80}")
        print(f"  {name}")
        print(f"{'='*80}")
        print(f"  {'ID':>8}  {'V1 state':>10} {'V1 conf':>8}  {'V2 state':>10} {'V2 conf':>8}  {'V2 veto':>50}  {'Diff':>6}")
        print(SEP)

        dataset_diffs = 0

        if typ == "sequential":
            chains = dataset.get("chains", [])
            for chain in chains:
                cid = chain["id"]
                steps = chain["steps"]
                evs = [s["evidence"] for s in steps]
                fts = [s["features"] for s in steps]

                # v1 chain
                prev = None
                v1_results = []
                for ev, ft in zip(evs, fts):
                    r = v1_compute(cid, ev, ft, prev)
                    v1_results.append(r)
                    prev = r["confidence"]
                # v2 chain
                prev = None
                v2_results = []
                for ev, ft in zip(evs, fts):
                    r = v2_compute(cid, ev, ft, prev)
                    v2_results.append(r)
                    prev = r["confidence"]

                v1_confs = ", ".join(f"{r['confidence']:.4f}" for r in v1_results)
                v2_confs = ", ".join(f"{r['confidence']:.4f}" for r in v2_results)
                v1_states = " → ".join(r['state'] for r in v1_results)
                v2_states = " → ".join(r['state'] for r in v2_results)

                chain_diff = sum(1 for r1, r2 in zip(v1_results, v2_results)
                                 if abs(r1["confidence"] - r2["confidence"]) > 0.01)
                if chain_diff:
                    all_v1.extend(v1_results); all_v2.extend(v2_results)
                dataset_diffs += chain_diff
                marker = " ⚠" if chain_diff else "  "

                print(f"  {cid:>8}  V1={v1_states} [{v1_confs}]")
                print(f"  {'':>8}  V2={v2_states} [{v2_confs}]{marker}")
                diffs[cid] = chain_diff
        else:
            cases = dataset.get("cases", [])
            for case in cases:
                cid = case["id"]
                v1r = v1_compute(case["claim"], case["evidence"], case["features"])
                v2r = v2_compute(case["claim"], case["evidence"], case["features"])
                all_v1.append(v1r); all_v2.append(v2r)

                same_state = v1r["state"] == v2r["state"]
                conf_diff = v2r["confidence"] - v1r["confidence"]
                significant = abs(conf_diff) > 0.01

                if significant or not same_state:
                    dataset_diffs += 1

                veto_str = ", ".join(v2r["veto_reasons"]) if v2r["veto_reasons"] else "[]"
                if same_state and not significant:
                    print(f"  {cid:>8}  {v1r['state']:<10} {v1r['confidence']:>8.4f}  {v2r['state']:<10} {v2r['confidence']:>8.4f}  {veto_str:>50}   ✓")
                else:
                    diff_str = f"{conf_diff:+.4f}" if significant else ""
                    marker = " ✓" if same_state else " ∅"
                    print(f"  {cid:>8}  {v1r['state']:<10} {v1r['confidence']:>8.4f}  {v2r['state']:<10} {v2r['confidence']:>8.4f}  {veto_str:>50}  {diff_str:>6}{marker}")

        if dataset_diffs:
            diffs[name] = dataset_diffs
            print(f"   → 差异数: {dataset_diffs}")

    # ── Aggregate stats ──
    print(f"\n{'='*80}")
    print(f"  汇总统计")
    print(f"{'='*80}")

    same_s = sum(1 for r1, r2 in zip(all_v1, all_v2) if r1["state"] == r2["state"])
    diff_s = sum(1 for r1, r2 in zip(all_v1, all_v2) if r1["state"] != r2["state"])
    total = len(all_v1)
    v1_v = sum(1 for r in all_v1 if r["state"] == "VERIFIED")
    v1_c = sum(1 for r in all_v1 if r["state"] == "CONTESTED")
    v1_u = sum(1 for r in all_v1 if r["state"] == "UNCERTAIN")
    v2_v = sum(1 for r in all_v2 if r["state"] == "VERIFIED")
    v2_c = sum(1 for r in all_v2 if r["state"] == "CONTESTED")
    v2_u = sum(1 for r in all_v2 if r["state"] == "UNCERTAIN")

    print(f"\n  V1: VERIFIED={v1_v}  CONTESTED={v1_c}  UNCERTAIN={v1_u}")
    print(f"  V2: VERIFIED={v2_v}  CONTESTED={v2_c}  UNCERTAIN={v2_u}")
    print(f"  状态一致: {same_s}/{total}")
    print(f"  状态不同: {diff_s}/{total}")

    # Confidence deltas
    conf_deltas = [v2r["confidence"] - v1r["confidence"] for v1r, v2r in zip(all_v1, all_v2)]
    avg = sum(conf_deltas) / len(conf_deltas)
    drops = sum(1 for d in conf_deltas if d < -0.01)
    raises = sum(1 for d in conf_deltas if d > 0.01)

    print(f"\n  V2 vs V1 置信度平均变化: {avg:+.4f}")
    print(f"  下降(>0.01): {drops}")
    print(f"  上升(>0.01): {raises}")
    print(f"  无变化:     {total - drops - raises}")

    # Find cases where v2 is more conservative (lower conf)
    print(f"\n  --- V2 更保守（降幅最大的 5 个） ---")
    sorted_deltas = sorted(zip(conf_deltas, all_v1, all_v2), key=lambda x: x[0])
    for d, r1, r2 in sorted_deltas[:5]:
        print(f"   {d:+.4f}: V1 {r1['state']} {r1['confidence']:.4f} → V2 {r2['state']} {r2['confidence']:.4f} veto={r2['veto_reasons']}")

    print(f"\n  --- V2 更宽松（升幅最大的 5 个） ---")
    for d, r1, r2 in reversed(sorted_deltas[-5:]):
        print(f"   {d:+.4f}: V1 {r1['state']} {r1['confidence']:.4f} → V2 {r2['state']} {r2['confidence']:.4f} veto={r2['veto_reasons']}")

    # State transition analysis
    print(f"\n  --- 状态转换矩阵 ---")
    for s1 in ["VERIFIED", "CONTESTED", "UNCERTAIN"]:
        for s2 in ["VERIFIED", "CONTESTED", "UNCERTAIN"]:
            cnt = sum(1 for r1, r2 in zip(all_v1, all_v2) if r1["state"] == s1 and r2["state"] == s2)
            if cnt > 0:
                print(f"    V1 {s1:>10} → V2 {s2:<10}: {cnt}")

if __name__ == "__main__":
    run_comparison()
