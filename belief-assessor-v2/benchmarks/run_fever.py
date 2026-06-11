#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""FEVER 100 — v1 vs v2 批量对比测试"""
import json, sys, math, re, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from pathlib import Path

# ── 动态加载 v1 和 v2 ──
import importlib.util

# v1 = Belief_State_Runtime skill (已装)
v1_dirs = [
    Path.home() / ".qclaw" / "skills" / "Belief_State_Runtime",
    Path.home() / ".qclaw" / "skills" / "belief-state-runtime",
    Path.home() / ".qclaw" / "skills" / "belief-assessor",
]

v1_path = None
for d in v1_dirs:
    p = d / "assess.py"
    if p.exists():
        v1_path = str(p)
        break

# v2 = 当前目录
v2_path = Path(__file__).parent / "scripts" / "assess.py"

if not v1_path:
    print("ERROR: v1 (Belief_State_Runtime / belief-assessor) not found")
    print("Searched:")
    for d in v1_dirs:
        print(f"  {d / 'assess.py'}")
    sys.exit(1)
v2_path = str(v2_path)

# 加载 v1
spec = importlib.util.spec_from_file_location("v1_mod", v1_path)
v1_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v1_mod)

# 加载 v2
spec2 = importlib.util.spec_from_file_location("v2_mod", v2_path)
v2_mod = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(v2_mod)

# ── 加载 FEVER 100 ──
fever_path = Path.home() / ".qclaw" / "workspace" / "belief-state-runtime - 副本" / "_data" / "fever_100.json"
if not fever_path.exists():
    # 试试其他路径
    fever_path = Path(r"C:\Users\huqiu\.qclaw\workspace\belief-state-runtime - 副本\_data\fever_100.json")

with open(fever_path, "r", encoding="utf-8") as f:
    fever_data = json.load(f)

print(f"FEVER 100: {len(fever_data)} 条 ({sum(1 for d in fever_data if d['label']=='SUPPORTS')} SUPPORTS, {sum(1 for d in fever_data if d['label']=='REFUTES')} REFUTES)\n")

# ── 6 bool 自动生成 ──
def auto_6bool(label):
    """根据 ground truth label 生成合理的 6 bool"""
    if label == "SUPPORTS":
        return json.dumps({"direct_support": True, "new_info": True, "logical_consistent": True,
                           "direct_refute": False, "limitation": False, "error_outdated": False})
    else:  # REFUTES
        return json.dumps({"direct_support": False, "new_info": True, "logical_consistent": False,
                           "direct_refute": True, "limitation": False, "error_outdated": True})

# ── 批量跑 ──
results = []
errors = []

for i, item in enumerate(fever_data):
    claim = item["claim"]
    evidence = item["evidence_text"]
    label = item["label"]
    six_bool = auto_6bool(label)

    try:
        # v1
        r1 = v1_mod.assess_claim_with_response(claim, evidence, six_bool)
        # v2 standard
        r2 = v2_mod.assess_claim_with_response(claim, evidence, six_bool)
        # v2 conservative
        r2c = v2_mod.assess_claim_with_response(
            claim, evidence, six_bool,
            config=v2_mod.ProjectionConfig.conservative()
        )
        # v2 permissive
        r2p = v2_mod.assess_claim_with_response(
            claim, evidence, six_bool,
            config=v2_mod.ProjectionConfig.permissive()
        )

        results.append({
            "idx": i,
            "claim": claim[:60],
            "label": label,
            "v1_state": r1["state"],
            "v1_conf": r1["confidence"],
            "v2_state": r2["state"],
            "v2_conf": r2["confidence"],
            "v2_veto": r2["veto_reasons"],
            "v2_cap": r2["cap_applied"],
            "v2c_state": r2c["state"],
            "v2c_conf": r2c["confidence"],
            "v2c_veto": r2c["veto_reasons"],
            "v2p_state": r2p["state"],
            "v2p_conf": r2p["confidence"],
            "v2p_veto": r2p["veto_reasons"],
            "qual": r2["quality_factor"],
            "support": r2["support_score"],
            "refute": r2["refute_score"],
        })
    except Exception as e:
        errors.append({"idx": i, "claim": claim, "error": str(e)})

if errors:
    print(f"❌ 错误: {len(errors)} 条")
    for e in errors[:3]:
        print(f"  [{e['idx']}] {e['claim'][:40]}: {e['error']}")
    print()

# ── 统计 ──
print(f"{'='*80}")
print(f"一、总体统计 — {len(results)} 条")
print(f"{'='*80}")

def calc_stats(rs, get_state_field):
    """计算正确率"""
    total = len(rs)
    correct = sum(1 for r in rs if r["label"] == ("SUPPORTS" if get_state_field(r) == "VERIFIED" else 
                                                   "REFUTES" if get_state_field(r) in ("CONTESTED","UNCERTAIN") else "X"))
    # 更精确：SUPPORTS→VERIFIED 正确, REFUTES→CONTESTED 正确
    supports_ok = sum(1 for r in rs if r["label"] == "SUPPORTS" and get_state_field(r) == "VERIFIED")
    refutes_ok = sum(1 for r in rs if r["label"] == "REFUTES" and get_state_field(r) in ("CONTESTED", "UNCERTAIN"))
    total_s = sum(1 for r in rs if r["label"] == "SUPPORTS")
    total_r = sum(1 for r in rs if r["label"] == "REFUTES")
    return {
        "supports": (supports_ok, total_s),
        "refutes": (refutes_ok, total_r),
        "overall": (supports_ok + refutes_ok, total),
    }

def state_f(field):
    return lambda r: r[field]

for name, state_field in [("v1", "v1_state"), ("v2 standard", "v2_state"), ("v2 conservative", "v2c_state"), ("v2 permissive", "v2p_state")]:
    s = calc_stats(results, state_f(state_field))
    print(f"\n{name}:")
    print(f"  SUPPORTS→VERIFIED:     {s['supports'][0]}/{s['supports'][1]} ({s['supports'][0]/s['supports'][1]*100:.1f}%)" if s['supports'][1] else "  SUPPORTS: 0")
    print(f"  REFUTES→CONT/UNCT:     {s['refutes'][0]}/{s['refutes'][1]} ({s['refutes'][0]/s['refutes'][1]*100:.1f}%)" if s['refutes'][1] else "  REFUTES: 0")
    print(f"  总体正确:               {s['overall'][0]}/{s['overall'][1]} ({s['overall'][0]/s['overall'][1]*100:.1f}%)")

# ── 差异分析 ──
print(f"\n{'='*80}")
print(f"二、v1 vs v2 差异")
print(f"{'='*80}")

state_changed = [r for r in results if r["v1_state"] != r["v2_state"]]
veto_fired = [r for r in results if r["v2_veto"]]
cap_effective = [r for r in results if r["v2_cap"] < 1.0]

print(f"  状态不同的条数:         {len(state_changed)}")
print(f"  veto_reasons 非空的:   {len(veto_fired)}")
print(f"  置信度被 cap 的:       {cap_effective}")

if state_changed:
    print(f"\n  状态变化详情 ({len(state_changed)} 条):")
    for r in state_changed[:10]:
        print(f"    [{r['idx']:3d}] {r['label']:>8} → v1={r['v1_state']:>10} v2={r['v2_state']:>10} conf={r['v2_conf']:.4f} veto={r['v2_veto']}")

if veto_fired:
    print(f"\n  触发约束的条 ({len(veto_fired)}):")
    veto_types = {}
    for r in veto_fired:
        for v in r["v2_veto"]:
            veto_types[v] = veto_types.get(v, 0) + 1
    print(f"  约束触发次数: {veto_types}")

# ── 三档对比 ──
print(f"\n{'='*80}")
print(f"三、三档策略差异")
print(f"{'='*80}")

for tier_name, state_fld, conf_fld in [("standard", "v2_state", "v2_conf"), 
                                         ("conservative", "v2c_state", "v2c_conf"),
                                         ("permissive", "v2p_state", "v2p_conf")]:
    avg_conf = sum(r[conf_fld] for r in results) / len(results)
    states = {}
    for r in results:
        s = r[state_fld]
        states[s] = states.get(s, 0) + 1
    sorted_states = ", ".join(f"{k}={v}" for k, v in sorted(states.items()))
    print(f"  {tier_name:>12}: avg_conf={avg_conf:.4f}  states=[{sorted_states}]")

# ── 具体数据 ──
print(f"\n{'='*80}")
print(f"四、明细数据 (前20条)")
print(f"{'='*80}")
print(f"{'#':>4} {'label':>8} {'v1_state':>10} {'v2_state':>10} {'v2_conf':>8} {'v2_range':>16} {'veto':>30}")
print(f"{'─'*80}")
for r in results[:20]:
    rng = f"[{r['v2_conf']-0.15:.3f},{r['v2_conf']+0.15:.3f}]"  # v1's
    veto_str = str(r["v2_veto"]) if r["v2_veto"] else "[]"
    print(f"{r['idx']:4d} {r['label']:>8} {r['v1_state']:>10} {r['v2_state']:>10} {r['v2_conf']:8.4f} {rng:>16} {veto_str:>30}")

# ── 保存结果 ──
out_path = v2_path.replace("scripts\\assess.py", "_results\\fever_v1_vs_v2.json")
Path(out_path).parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump({
        "total": len(results),
        "summary": {
            "state_changed": len(state_changed),
            "veto_fired": len(veto_fired),
        },
        "veto_type_counts": veto_types,
        "results": results,
    }, f, ensure_ascii=False, indent=2)

print(f"\n结果已保存: {out_path}")
print(f"\n✅ FEVER 100 批量测试完成")
