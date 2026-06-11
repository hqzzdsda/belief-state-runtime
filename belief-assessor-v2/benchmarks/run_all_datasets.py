"""
belief-assessor v2 — 多数据集通用测试运行器
加载 tests/dataset_*.json → 运行评估 → 生成对比报告
"""
import sys, json, glob, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
from assess import FeatureExtractor, assess_claim_with_response

DATASETS_DIR = os.path.join(os.path.dirname(__file__), "tests")
SEPARATOR = "─" * 90

# ── 颜色/标记 ──
GREEN  = "\033[92m" if os.name == "nt" else "\033[92m"
RED    = "\033[91m" if os.name == "nt" else "\033[91m"
YELLOW = "\033[93m" if os.name == "nt" else "\033[93m"
RESET  = "\033[0m" if os.name == "nt" else "\033[0m"
CHECK  = "✓"; CROSS = "✗"; WARN = "⚠"

def _load_datasets():
    """Load all dataset_*.json files from tests/"""
    datasets = []
    for fp in sorted(glob.glob(os.path.join(DATASETS_DIR, "dataset_*.json"))):
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
            datasets.append(data)
    return datasets

def _check_case(result, expected):
    """Compare a single result against expected values."""
    checks = []
    if "state" in expected and expected["state"]:
        ok = result["state"] == expected["state"]
        checks.append((ok, f"state={result['state']} (expect {expected['state']})", ok))
    if "conf_floor" in expected and expected["conf_floor"] is not None:
        ok = result["confidence"] >= expected["conf_floor"]
        checks.append((ok, f"conf={result['confidence']:.4f} >= {expected['conf_floor']:.4f}", ok))
    if "conf_ceiling" in expected and expected["conf_ceiling"] is not None:
        ok = result["confidence"] <= expected["conf_ceiling"]
        checks.append((ok, f"conf={result['confidence']:.4f} <= {expected['conf_ceiling']:.4f}", ok))
    if "veto_contains" in expected:
        ok = expected["veto_contains"] in str(result.get("veto_reasons", []))
        checks.append((ok, f"veto contains '{expected['veto_contains']}'", ok))
    return checks, result["state"], round(result["confidence"], 4), result.get("veto_reasons", [])

def run_param_dataset(dataset):
    """Run a parametric/scenario dataset (flat cases list)."""
    name = dataset.get("name", dataset.get("id", "unknown"))
    cases = dataset.get("cases", [])
    if not cases:
        return []
    results = []
    for case in cases:
        r = assess_claim_with_response(case["claim"], case["evidence"], json.dumps(case["features"]))
        checks, state, conf, veto = _check_case(r, case["expected"])
        results.append({**case, "result": r, "checks": checks, "state": state, "conf": conf, "veto": veto})
    return results

def run_chain_dataset(dataset):
    """Run a sequential chain dataset (steps per chain)."""
    chains = dataset.get("chains", [])
    if not chains:
        return []
    results = []
    for chain in chains:
        prev_conf = None
        chain_results = []
        for i, step in enumerate(chain["steps"]):
            r = assess_claim_with_response(
                step["claim"], step["evidence"],
                json.dumps(step["features"]),
                previous_confidence=prev_conf
            )
            checks, state, conf, veto = _check_case(r, step["expected_after"])
            chain_results.append({**step, "result": r, "checks": checks,
                                  "state": state, "conf": conf, "veto": veto})
            prev_conf = round(r["confidence"], 4)
        results.append({**chain, "steps": chain_results})
    return results

def print_results(param_results, chain_results):
    """Print formatted results."""
    all_pass = 0; all_fail = 0; all_warn = 0

    # ── Parametric datasets ──
    for dataset, results in param_results:
        name = dataset.get("name", dataset.get("id", "?"))
        total = len(results)
        if total == 0:
            continue
        print(f"\n{'='*60}")
        print(f"  {name}  ({total} 条)")
        print(f"{'='*60}")
        print(f"  {'ID':>8} {'state':>10} {'conf':>8} {'veto':>55} {'checks':>36}")
        print(SEPARATOR)
        for r in results:
            pec = sum(1 for _, _, ok in r["checks"] if ok)
            pfc = sum(1 for _, _, ok in r["checks"] if not ok)
            tag = GREEN + CHECK + RESET if pfc == 0 else RED + CROSS + RESET
            veto_str = ", ".join(r["veto"]) if r["veto"] else "[]"
            icon = CHECK if pfc == 0 else CROSS
            state_str = f"{r['state']:<10}"
            print(f"  {tag} {r['id']:>6} {state_str} {r['conf']:>8.4f} {veto_str:>55} {icon} {pec}/{pec+pfc}")
            if pfc > 0:
                all_fail += 1
            else:
                all_pass += 1

    # ── Chain datasets ──
    for dataset, chain_results in chain_results:
        name = dataset.get("name", dataset.get("id", "?"))
        total_chains = len(chain_results)
        if total_chains == 0:
            continue
        print(f"\n{'='*60}")
        print(f"  {name}  ({total_chains} 条链)")
        print(f"{'='*60}")
        for chain in chain_results:
            pat = chain.get("expected_pattern", "")
            steps = chain["steps"]
            confs = ", ".join(f"{s['conf']:.4f}" for s in steps)
            states = " → ".join(s["state"] for s in steps)
            all_chain_ok = all(all(ok for _, _, ok in s["checks"]) for s in steps)
            icon = GREEN + CHECK + RESET if all_chain_ok else RED + CROSS + RESET
            print(f"  {icon} {chain['id']:>10}: [{confs}]")
            print(f"     states: {states}  pattern: {pat}")
            if not all_chain_ok:
                all_fail += 1
                for s in steps:
                    fails = [(c, d) for c, d, ok in s["checks"] if not ok]
                    if fails:
                        print(f"     ◆ step fail: {fails[0][0]} | {fails[0][1]}")
            else:
                all_pass += 1

    # ── Summary ──
    print(f"\n{'='*60}")
    print(f"  汇总: {GREEN}{CHECK}{RESET} 通过 {all_pass}  |  {RED}{CROSS}{RESET} 失败 {all_fail}")
    print(f"{'='*60}")

def main():
    datasets = _load_datasets()
    print(f"加载 {len(datasets)} 个数据集")
    for d in datasets:
        typ = d.get("type", "parametric")
        cnt = len(d.get("cases", [])) or len(d.get("chains", []))
        print(f"  • {d['name']}  [{typ}]  ({cnt} 条)")

    param_results = []
    chain_results = []
    for dataset in datasets:
        typ = dataset.get("type", "parametric")
        if typ in ("parametric", "parametric_and_edge", "scenario"):
            r = run_param_dataset(dataset)
            param_results.append((dataset, r))
        elif typ == "sequential":
            r = run_chain_dataset(dataset)
            chain_results.append((dataset, r))

    print_results(param_results, chain_results)

if __name__ == "__main__":
    main()
