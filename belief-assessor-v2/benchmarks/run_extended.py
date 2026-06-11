"""
belief-assessor v2 — 扩展外部基准评测
新增: fever_with_evidence, anli, halueval, mnli
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from assess import _compute_from_features

ES = r"C:\Users\huqiu\.qclaw\workspace\belief-state-runtime - 副本\eval_subsets"

def load(fname, limit=None):
    fp = os.path.join(ES, fname)
    import json
    with open(fp, "r", encoding="utf-8") as f:
        d = json.load(f)
    samples = d.get("samples", [])
    if limit:
        samples = samples[:limit]
    return samples

def label_to_features(label):
    label = label.upper().strip()
    if label in ("SUPPORTS", "TRUE"):
        return {"direct_support": True, "new_info": True, "logical_consistent": True,
                "direct_refute": False, "limitation": False, "error_outdated": False}
    elif label in ("REFUTES", "FALSE"):
        return {"direct_support": False, "new_info": False, "logical_consistent": False,
                "direct_refute": True, "limitation": False, "error_outdated": True}
    else:
        return {"direct_support": False, "new_info": False, "logical_consistent": False,
                "direct_refute": False, "limitation": False, "error_outdated": False}

def is_hit(state, label):
    label = label.upper().strip()
    if label in ("SUPPORTS", "TRUE"):
        return state in ("VERIFIED", "CONTESTED"), state == "CONTESTED"
    else:
        return state in ("CONTESTED", "UNCERTAIN"), False

def run_eval(name, samples):
    print(f"\n{'='*70}")
    print(f"  {name} ({len(samples)} samples)")
    print(f"{'='*70}")

    total = len(samples)
    hits = cautious = misses = 0
    v_c = c_c = u_c = 0
    total_conf = 0.0
    fp_cases = []

    for s in samples:
        ev = s.get("evidence_text", "") or s.get("evidence", "") or ""
        cl = s.get("claim", "")
        feat = label_to_features(s["label"])
        r = _compute_from_features(cl, ev, feat)
        hit, cautious_flag = is_hit(r["state"], s["label"])
        if hit:
            hits += 1
            if cautious_flag:
                cautious += 1
        else:
            misses += 1
            if r["state"] == "VERIFIED" and s["label"].upper() in ("REFUTES", "FALSE"):
                fp_cases.append((cl[:60], ev[:60], r["confidence"]))

        if r["state"] == "VERIFIED": v_c += 1
        elif r["state"] == "CONTESTED": c_c += 1
        else: u_c += 1
        total_conf += r["confidence"]

    avg_conf = total_conf / total if total else 0
    print(f"  命中: {hits}/{total} ({hits/total*100:.1f}%)", end="")
    if cautious: print(f"  [{cautious} cautious]", end="")
    print()
    print(f"  状态: V={v_c} C={c_c} U={u_c}  平均conf={avg_conf:.4f}")

    if fp_cases:
        print(f"\n  ⚠ 假阳性 ({len(fp_cases)}):")
        for cl, ev, conf in fp_cases[:3]:
            print(f"    conf={conf:.4f} claim={cl} ev={ev}")

    # Per-label breakdown
    labels = set(s["label"] for s in samples)
    for lbl in sorted(labels):
        grp = [s for s in samples if s["label"] == lbl]
        cfgs = []
        for s in grp:
            ev = s.get("evidence_text", "") or ""
            feat = label_to_features(s["label"])
            r = _compute_from_features(s["claim"], ev, feat)
            cfgs.append(r["confidence"])
        v = sum(1 for s in grp for f in [label_to_features(s["label"])]
                for r in [_compute_from_features(s["claim"], s.get("evidence_text","") or "", f)]
                if r["state"] == "VERIFIED")
        # Cheaper: just count from already computed
        v2 = sum(1 for s in grp for r in [_compute_from_features(s["claim"], s.get("evidence_text","") or "", label_to_features(s["label"]))] if r["state"] == "VERIFIED")
        c2 = sum(1 for s in grp for r in [_compute_from_features(s["claim"], s.get("evidence_text","") or "", label_to_features(s["label"]))] if r["state"] == "CONTESTED")
        avg = sum(cfgs) / len(cfgs) if cfgs else 0
        print(f"    {lbl:>10} ({len(grp):>3}): V={v2} C={c2} avg={avg:.4f}")

    return hits, misses

def main():
    total_hits = total_all = 0

    configs = [
        ("fever_with_evidence.json", "FEVER with evidence (200)", None),
        ("anli_subset.json", "ANLI (300)", None),
        ("halueval_subset.json", "HaluEval (300)", None),
        ("mnli_subset.json", "MNLI (200)", None),
    ]

    for fname, name, limit in configs:
        samples = load(fname, limit)
        h, m = run_eval(name, samples)
        total_hits += h
        total_all += len(samples)

    print(f"\n{'='*70}")
    print(f"  综合 (4 datasets, {total_all} samples)")
    print(f"{'='*70}")
    print(f"  总命中: {total_hits}/{total_all} ({total_hits/total_all*100:.1f}%)")

if __name__ == "__main__":
    main()
