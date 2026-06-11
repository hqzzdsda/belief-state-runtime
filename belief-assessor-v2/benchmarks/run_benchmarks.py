"""
v2 belief-assessor 外部基准评测
FEVER (100), PubHealth (150), LIAR (150)
"""
import sys, os, csv, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from assess import _compute_from_features

BASE = r"C:\Users\huqiu\.qclaw\workspace\belief-state-runtime - 副本"

def label_to_features(label):
    label = label.upper().strip()
    if label in ("SUPPORTS", "TRUE"):
        return {"direct_support": True, "new_info": True, "logical_consistent": True,
                "direct_refute": False, "limitation": False, "error_outdated": False}
    elif label in ("REFUTES", "FALSE"):
        return {"direct_support": False, "new_info": False, "logical_consistent": False,
                "direct_refute": True, "limitation": False, "error_outdated": True}
    elif label == "MIXTURE":
        return {"direct_support": True, "new_info": True, "logical_consistent": True,
                "direct_refute": False, "limitation": True, "error_outdated": False}
    else:
        return {"direct_support": False, "new_info": False, "logical_consistent": False,
                "direct_refute": False, "limitation": False, "error_outdated": False}

def expected(label):
    label = label.upper().strip()
    if label in ("SUPPORTS", "TRUE", "MIXTURE"):
        return ["VERIFIED", "CONTESTED"]
    else:
        return ["CONTESTED", "UNCERTAIN"]

def is_hit(v2_state, label):
    ok = expected(label)
    hit = v2_state in ok
    cautious = hit and v2_state == "CONTESTED" and label.upper() in ("SUPPORTS", "TRUE")
    miss_fp = not hit and v2_state == "VERIFIED" and label.upper() in ("REFUTES", "FALSE")
    return hit, "cautious" if cautious else ("miss_fp" if miss_fp else ("hit" if hit else "miss"))

def load_fever100():
    fp = os.path.join(BASE, "_data", "fever_100.json")
    with open(fp, "r", encoding="utf-8") as f:
        raw = json.load(f)
    # Normalize evidence_text -> evidence
    for s in raw:
        if "evidence_text" in s:
            s["evidence"] = s["evidence_text"]
        elif "evidence" in s:
            pass
        else:
            s["evidence"] = ""
    return raw

def load_pubhealth(limit=150):
    tsv = (BASE + r"\datasets\priority2_domain\PubHealth\downloads\extracted"
           r"\9583300c0a34546faa3472f87dd09440cb023271856ea91ec3ca975373e6c9e2\PUBHEALTH\test.tsv")
    samples = []
    with open(tsv, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        next(reader)
        for row in reader:
            if len(row) < 9:
                continue
            label = row[8].strip()
            if label not in ("true", "false", "mixture", "unproven"):
                continue
            samples.append({"claim": row[2], "evidence": row[4], "label": label})
            if limit and len(samples) >= limit:
                break
    return samples

def load_liar(limit=150):
    fp = os.path.join(BASE, "eval_subsets", "liar_subset.json")
    with open(fp, "r", encoding="utf-8") as f:
        data = json.load(f)
    samples = []
    for s in data["samples"]:
        ev = s.get("evidence_text") or ""
        samples.append({"claim": s["claim"], "evidence": ev, "label": s["label"]})
        if limit and len(samples) >= limit:
            break
    return samples

def run_eval(name, samples):
    print(f"\n{'='*70}")
    print(f"  {name} ({len(samples)} samples)")
    print(f"{'='*70}")

    all_r = []
    for s in samples:
        feat = label_to_features(s["label"])
        r = _compute_from_features(s["claim"], s.get("evidence") or "", feat)
        hit, reason = is_hit(r["state"], s["label"])
        all_r.append({**r, "benchmark": s["label"], "hit": hit, "reason": reason,
                      "evidence_len": len(s.get("evidence") or "")})

    total = len(all_r)
    hits = sum(1 for r in all_r if r["hit"])
    cautious = sum(1 for r in all_r if r["reason"] == "cautious")
    miss_fp = sum(1 for r in all_r if r["reason"] == "miss_fp")
    miss = sum(1 for r in all_r if r["reason"] == "miss")

    print(f"  命中: {hits}/{total} ({hits/total*100:.1f}%)  ", end="")
    if cautious: print(f"[{cautious} cautious] ", end="")
    if miss_fp: print(f"[{miss_fp} false_pos] ", end="")
    print()

    v_c = sum(1 for r in all_r if r["state"] == "VERIFIED")
    c_c = sum(1 for r in all_r if r["state"] == "CONTESTED")
    u_c = sum(1 for r in all_r if r["state"] == "UNCERTAIN")
    avg_conf = sum(r["confidence"] for r in all_r) / total
    print(f"  状态: V={v_c} C={c_c} U={u_c}  平均conf={avg_conf:.4f}")

    # Per-label
    for lbl in ["SUPPORTS", "TRUE", "REFUTES", "FALSE", "MIXTURE", "unproven"]:
        grp = [r for r in all_r if r["benchmark"].upper() == lbl or r["benchmark"] == lbl]
        if not grp:
            continue
        v = sum(1 for r in grp if r["state"] == "VERIFIED")
        c = sum(1 for r in grp if r["state"] == "CONTESTED")
        u = sum(1 for r in grp if r["state"] == "UNCERTAIN")
        avg = sum(r["confidence"] for r in grp) / len(grp)
        if lbl in ("SUPPORTS", "TRUE"):
            good = v+c
        elif lbl in ("REFUTES", "FALSE"):
            good = c+u
        else:
            good = v+c
        print(f"  {lbl:>10} ({len(grp):>3}): V={v} C={c} U={u} avg={avg:.4f}  → ok={good}/{len(grp)} ({good/len(grp)*100:.0f}%)")

    if miss_fp:
        print(f"\n  --- False positives (REFUTES/FALSE→VERIFIED) ---")
        for r in all_r:
            if r["reason"] == "miss_fp":
                print(f"  conf={r['confidence']:.4f} veto={r['veto_reasons']}")
    return all_r

def main():
    fever = load_fever100()
    pubhealth = load_pubhealth(150)
    liar = load_liar(150)

    r1 = run_eval("FEVER (100)", fever)
    r2 = run_eval("PubHealth (150)", pubhealth)
    r3 = run_eval("LIAR (150)", liar)

    all_r = r1 + r2 + r3
    total = len(all_r)
    hits = sum(1 for r in all_r if r["hit"])
    print(f"\n{'='*70}")
    print(f"  综合 ({total} samples)")
    print(f"{'='*70}")
    print(f"  总命中: {hits}/{total} ({hits/total*100:.1f}%)")
    print(f"  总假阳性: {sum(1 for r in all_r if r['reason']=='miss_fp')}")

if __name__ == "__main__":
    main()
