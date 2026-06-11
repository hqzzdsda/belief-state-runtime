#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""belief-assessor v2 — 完整 28 条手动测试集批量运行"""
import sys, os, json, importlib.util, math
from pathlib import Path

# ── 路径配置 ──
V1_DIRS = [
    Path.home() / ".qclaw" / "skills" / "Belief_State_Runtime",
    Path.home() / ".qclaw" / "skills" / "belief-assessor",
]
V2_PATH = Path(__file__).parent / "scripts" / "assess.py"

# Find v1
v1_path = None
for d in V1_DIRS:
    p = d / "assess.py"
    if p.exists():
        v1_path = str(p)
        break
if not v1_path:
    print("ERROR: v1 not found")
    sys.exit(1)

v2_path = str(V2_PATH)

# Load modules
spec = importlib.util.spec_from_file_location("v1_mod", v1_path)
v1_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v1_mod)

spec2 = importlib.util.spec_from_file_location("v2_mod", v2_path)
v2_mod = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(v2_mod)

# ── Test case definition ──
def tc(claim, evidence, six_bool, group, tag, expect_veto=None, expect_state=None):
    """Test case factory."""
    return {
        "claim": claim,
        "evidence": evidence,
        "six_bool": json.dumps(six_bool),
        "group": group,
        "tag": tag,
        "expect_veto": expect_veto,
        "expect_state": expect_state,
    }

CASES = [
    # ── A组: 好证据 — 应 VERIFIED ──
    tc("中国高铁运营里程超过4万公里",
       "交通运输部2025年公布的数据显示：中国高铁运营里程已超过4.5万公里，占全球高铁总里程的三分之二以上。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "A", "A1", expect_veto=[], expect_state="VERIFIED"),
    tc("2024年全球平均气温创历史新高",
       "NASA和NOAA2025年1月联合发布的报告确认：2024年全球平均气温比工业化前水平高出1.46°C，超过了2023年的纪录。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "A", "A2", expect_veto=[], expect_state="VERIFIED"),
    tc("DeepSeek V3在多个基准上超越GPT-4o",
       "第三方评测平台Artificial Analysis发布的2025年Q1报告显示，DeepSeek-V3在MMLU、HumanEval和GSM8K等基准上得分超过GPT-4o。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "A", "A3", expect_veto=[], expect_state="VERIFIED"),

    # ── B组: 来源差 — 应 gated ──
    tc("某个小币种明天会涨100倍",
       "在Telegram中文群里，一个刚注册三天的账号发消息说：\"内部消息！XX币今晚团队要宣布重大合作，明天至少100倍！赶紧上车！\" 群里没有管理员，也没有其他来源证实。",
       {"direct_support":True,"new_info":False,"logical_consistent":False,"direct_refute":False,"limitation":False,"error_outdated":False},
       "B", "B1", expect_veto=lambda v: any(v)),
    tc("喝XX保健品能治愈癌症",
       "小红书一篇笔记写道：\"我爸喝了XX灵芝孢子粉三个月，医院查出来癌细胞全部消失了！不是广告，真心推荐！\" 下面是几条\"真的吗？\"\"哪里买？\"的评论。",
       {"direct_support":True,"new_info":False,"logical_consistent":False,"direct_refute":False,"limitation":False,"error_outdated":False},
       "B", "B2", expect_veto=lambda v: any(v)),
    tc("某明星私生活爆料",
       "在百度贴吧匿名帖子里，一个\"路人甲\"声称某明星有私生子。帖子只有一句话，没有图没有来源。回帖都是\"无图无真相\"。",
       {"direct_support":True,"new_info":False,"logical_consistent":False,"direct_refute":False,"limitation":False,"error_outdated":False},
       "B", "B3", expect_veto=lambda v: any(v)),

    # ── C组: 直接反驳 ──
    tc("比特币在2024年跌破1万美元",
       "CoinMarketCap实际数据显示：比特币在2024年最高价格超过10万美元，最低也未跌破15000美元。",
       {"direct_support":False,"new_info":True,"logical_consistent":False,"direct_refute":True,"limitation":False,"error_outdated":False},
       "C", "C1", expect_veto=lambda v: "contradiction_capped" in v),
    tc("日本2024年GDP负增长",
       "日本内阁府2025年3月发布的数据：2024年日本实际GDP增长率为1.2%，虽低于预期但仍为正增长。",
       {"direct_support":False,"new_info":True,"logical_consistent":False,"direct_refute":True,"limitation":False,"error_outdated":False},
       "C", "C2", expect_veto=lambda v: "contradiction_capped" in v),

    # ── D组: 时效降级 ──
    tc("COVID-19死亡率约3.4%",
       "WHO于2020年3月发布的早期报告中估计COVID-19死亡率为3.4%。该数据基于当时有限的临床数据。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":True,"error_outdated":False},
       "D", "D1", expect_veto=lambda v: "temporal_decayed" in v),
    tc("中国GDP增速超过10%",
       "2010年中国国家统计局数据显示：当年GDP增长率达到10.6%。",
       {"direct_support":True,"new_info":False,"logical_consistent":True,"direct_refute":False,"limitation":True,"error_outdated":False},
       "D", "D2", expect_veto=lambda v: "temporal_decayed" in v),

    # ── E组: 多约束同时触发 ──
    tc("XX保健品能治新冠",
       "2020年3月在一个中文论坛上，一个匿名用户发了一篇帖子说\"我舅舅喝了XX牌中药，三天新冠症状全没了\"。帖子只有这一段话，无出处。",
       {"direct_support":True,"new_info":False,"logical_consistent":False,"direct_refute":False,"limitation":False,"error_outdated":False},
       "E", "E1", expect_veto=lambda v: len(v) >= 2),
    tc("比特币会取代美元",
       "2018年有个个人博客写了一篇文章，猜测比特币未来会成为全球储备货币。文章只有观点没有数据。",
       {"direct_support":True,"new_info":False,"logical_consistent":False,"direct_refute":False,"limitation":True,"error_outdated":False},
       "E", "E2", expect_veto=lambda v: len(v) >= 2),
    tc("某CEO即将辞职",
       "Reddit上一个匿名帖说\"内部消息：某科技公司CEO下周就会辞职\"。没有时间没有出处。",
       {"direct_support":True,"new_info":False,"logical_consistent":False,"direct_refute":False,"limitation":False,"error_outdated":False},
       "E", "E3", expect_veto=lambda v: len(v) >= 1),

    # ── F组: 边界值 ──
    tc("新能源车渗透率持续提升",
       "中国汽车工业协会2025年6月发布的数据显示新能源汽车渗透率达到44.6%。这是一份中等质量的市场报告。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "F", "F1"),
    tc("某项前沿技术在实验室有突破",
       "某个大学实验室官网发布了一条简短的科研成果信息，没有具体数据，没有同行评审。",
       {"direct_support":True,"new_info":True,"logical_consistent":False,"direct_refute":False,"limitation":True,"error_outdated":False},
       "F", "F2"),
    tc("某社交媒体平台数据表现好",
       "某个中小型自媒体公众号引用了一些数据说某平台月活增长。来源不够明确但有一定可信度。",
       {"direct_support":True,"new_info":False,"logical_consistent":True,"direct_refute":False,"limitation":True,"error_outdated":False},
       "F", "F3"),

    # ── G组: 混合证据 ──
    tc("中国新能源汽车销量全球第一",
       "工信部官网文件显示2024年中国新能源汽车销量超1200万辆，占全球60%以上。此外知乎上有行业分析师验证了这一数据的准确性。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "G", "G1"),
    tc("AI模型在翻译任务上超越人类水平",
       "arXiv上DeepMind 2025年发布的论文证明其模型在WMT翻译基准上BLEU得分首次超过人类平均。另有一个AI博主在Twitter上转发了论文结果。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "G", "G2"),
    tc("AI模型在翻译任务上超越人类水平(仅Twitter)",
       "Twitter上一个AI博主说\"听说有篇论文证明AI在翻译上超过人类了\"。只有一个来源，没有论文链接。",
       {"direct_support":True,"new_info":False,"logical_consistent":False,"direct_refute":False,"limitation":False,"error_outdated":False},
       "G", "G3"),

    # ── H组: 空/极弱证据 ──
    tc("XX技术是未来趋势", "",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "H", "H1"),
    tc("XX技术是未来趋势", "是的",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "H", "H2"),
    tc("XX技术是未来趋势", "https://gov.cn 官方报告显示支持该技术的发展前景。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "H", "H3"),

    # ── I组: 增量多步 ──
    # I1: 维生素D能预防COVID → 三步
    tc("维生素D能预防COVID",
       "2020年西班牙一项观察性研究发现维生素D缺乏与COVID重症有一定相关性(n=200)。发表于Journal of Clinical Endocrinology & Metabolism。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":True,"error_outdated":False},
       "I", "I1a"),
    tc("维生素D能预防COVID",
       "2021年英国一项RCT(维生素D组vs安慰剂组，n=6200)发现补充维生素D对预防COVID感染无显著效果。发表于BMJ。",
       {"direct_support":False,"new_info":True,"logical_consistent":False,"direct_refute":True,"limitation":False,"error_outdated":False},
       "I", "I1b"),
    tc("维生素D能预防COVID",
       "2022年荟萃分析(涵盖20项研究，n=11200)结论是：目前证据不足以支持维生素D用于COVID预防。发表于Cochrane Library。",
       {"direct_support":False,"new_info":True,"logical_consistent":False,"direct_refute":True,"limitation":False,"error_outdated":False},
       "I", "I1c"),

    # I2: 某公司Q3超预期 → 三步
    tc("某公司Q3财报超预期",
       "公司官方发布2025年Q3财报：营收同比增长32%，净利润增长28%，均超出市场预期。经审计的财务数据。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "I", "I2a"),
    tc("某公司Q3财报超预期",
       "做空机构Hindenburg发布报告声称该公司Q3财报中的营收数据存在水分，实际增长可能只有15%。报告列出了详细疑点。",
       {"direct_support":False,"new_info":True,"logical_consistent":False,"direct_refute":True,"limitation":False,"error_outdated":False},
       "I", "I2b"),
    tc("某公司Q3财报超预期",
       "公司发布澄清公告，逐一回应Hindenburg质疑，附上了审计师的独立验证文件。股价回升至财报发布后的水平。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "I", "I2c"),

    # I3: 城市房价要涨 → 三步
    tc("某个城市房价要涨",
       "自媒体一篇文章说\"很多人在讨论这个城市的房价会涨，因为最近利好政策多\"。全文只有观点没有数据。",
       {"direct_support":True,"new_info":False,"logical_consistent":False,"direct_refute":False,"limitation":True,"error_outdated":False},
       "I", "I3a"),
    tc("某个城市房价要涨",
       "国家统计局发布的70个大中城市房价数据显示该城市2025年新房价格环比上涨0.3%。数据来源明确。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "I", "I3b"),
    tc("某个城市房价要涨",
       "多家机构发布研报：中信、中金、国泰君安一致认为该城市因人口净流入和政策支持，2025-2026年房价有3%-8%的上涨空间。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "I", "I3c"),

    # ── J组: 三档预设同条对比 ──
    tc("中国高铁运营里程超过4万公里",
       "交通运输部2025年公布的数据显示：中国高铁运营里程已超过4.5万公里，占全球高铁总里程的三分之二以上。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "J", "J1"),
    tc("某个小币种明天会涨100倍",
       "在Telegram中文群里，一个刚注册三天的账号发消息说：\"内部消息！XX币今晚团队要宣布重大合作，明天至少100倍！赶紧上车！\" 群里没有管理员，也没有其他来源证实。",
       {"direct_support":True,"new_info":False,"logical_consistent":False,"direct_refute":False,"limitation":False,"error_outdated":False},
       "J", "J2"),
    tc("新能源车渗透率持续提升",
       "中国汽车工业协会2025年6月发布的数据显示新能源汽车渗透率达到44.6%。中等质量市场报告。",
       {"direct_support":True,"new_info":True,"logical_consistent":True,"direct_refute":False,"limitation":False,"error_outdated":False},
       "J", "J3"),
]

print(f"共 {len(CASES)} 条测试用例\n")

# ── 批量运行 ──
results = []
for i, c in enumerate(CASES):
    claim = c["claim"]
    evidence = c["evidence"]
    six = c["six_bool"]

    try:
        features = json.loads(six)
        
        # ── I组: 增量多步 ──
        if c["group"] == "I":
            base_claim = claim
            # Find all I-group cases with same claim prefix
            # Build chain manually based on tag
            
            # Use _compute_from_features for incremental chain
            def run_step(prev):
                return v2_mod._compute_from_features(claim, evidence, features, previous_confidence=prev)
            
            if c["tag"].endswith("a"):
                # First step: no previous
                r2 = run_step(None)
                # Also run v1 first step
                r1_v2 = v2_mod._compute_from_features(claim, evidence, features)  
                r1 = {"state": r1_v2["state"], "confidence": r1_v2["confidence"]}
            else:
                # Find previous step result
                prev_tag = c["tag"][:-1] + chr(ord(c["tag"][-1]) - 1)
                prev_r = next((x for x in results if x.get("tag") == prev_tag), None)
                if prev_r:
                    prev_conf = prev_r.get("incremental_conf")
                    r2 = run_step(prev_conf)
                    r1_r = run_step(None)  # v1 doesn't have incremental
                    r1 = {"state": r1_r["state"], "confidence": r1_r["confidence"]}
                else:
                    r2 = run_step(None)
                    r1 = {"state": r2["state"], "confidence": r2["confidence"]}

            result_entry = {
                "idx": i,
                "group": c["group"],
                "tag": c["tag"],
                "claim": claim[:50],
                "v1_state": r1["state"],
                "v1_conf": round(r1["confidence"], 4),
                "v2_state": r2["state"],
                "v2_conf": round(r2["confidence"], 4),
                "v2_veto": r2.get("veto_reasons", []),
                "v2_cap": r2.get("cap_applied", None),
                "v2_range": [round(v, 4) for v in r2.get("confidence_range", [0,0])],
                "qual": round(r2.get("quality_factor", 0), 4),
                "support": round(r2.get("support_score", 0), 4),
                "refute": round(r2.get("refute_score", 0), 4),
                "incremental_conf": r2["confidence"],
            }
            # Also do conservative/permissive for tracking
            r2c = v2_mod._compute_from_features(claim, evidence, features, previous_confidence=result_entry.get("incremental_conf") if c["tag"].endswith("a") else None, config=v2_mod.ProjectionConfig.conservative())
            # This is extra - just use the first step prev
            result_entry["v2c_state"] = r2c["state"]
            result_entry["v2c_conf"] = round(r2c["confidence"], 4)
            results.append(result_entry)
            continue

        # ── 常规测试 (非I组) ──
        r1 = v1_mod.assess_claim_with_response(claim, evidence, six)
        r2 = v2_mod.assess_claim_with_response(claim, evidence, six)
        r2c = v2_mod.assess_claim_with_response(claim, evidence, six, config=v2_mod.ProjectionConfig.conservative())
        r2p = v2_mod.assess_claim_with_response(claim, evidence, six, config=v2_mod.ProjectionConfig.permissive())

        results.append({
            "idx": i,
            "group": c["group"],
            "tag": c["tag"],
            "claim": claim[:50],
            "v1_state": r1["state"],
            "v1_conf": round(r1["confidence"], 4),
            "v2_state": r2["state"],
            "v2_conf": round(r2["confidence"], 4),
            "v2_veto": r2["veto_reasons"],
            "v2_cap": r2.get("cap_applied", None),
            "v2_range": [round(v, 4) for v in r2["confidence_range"]],
            "v2c_state": r2c["state"],
            "v2c_conf": round(r2c["confidence"], 4),
            "v2c_veto": r2c["veto_reasons"],
            "v2c_range": [round(v, 4) for v in r2c["confidence_range"]],
            "v2p_state": r2p["state"],
            "v2p_conf": round(r2p["confidence"], 4),
            "v2p_veto": r2p["veto_reasons"],
            "v2p_range": [round(v, 4) for v in r2p["confidence_range"]],
            "qual": round(r2.get("quality_factor", 0), 4),
            "support": round(r2.get("support_score", 0), 4),
            "refute": round(r2.get("refute_score", 0), 4),
        })
    except Exception as e:
        import traceback
        results.append({
            "idx": i, "group": c["group"], "tag": c["tag"], "claim": claim[:50],
            "error": str(e) + " | " + traceback.format_exc()[:200]
        })

# ── 输出 ──
# 按组分
groups = sorted(set(r.get("group","?") for r in results))
for g in groups:
    grp_results = [r for r in results if r.get("group") == g]
    print(f"\n{'='*90}")
    print(f"  组 {g}: {len(grp_results)} 条")
    print(f"{'='*90}")
    print(f"{'Tag':>6} {'v1_state':>10} {'v1_conf':>8} {'v2_state':>10} {'v2_conf':>8} {'cap':>5} {'veto':>40} {'range':>18}")
    print(f"{'─'*90}")
    for r in grp_results:
        if "error" in r:
            print(f"  {r['tag']:>6}  ERROR: {r['error']}")
            continue
        veto_str = ", ".join(r["v2_veto"]) if r["v2_veto"] else "[]"
        rng = f"[{r['v2_range'][0]},{r['v2_range'][1]}]"
        cap_str = f"{r['v2_cap']:.2f}" if r["v2_cap"] else "-"
        print(f"  {r['tag']:>6} {r['v1_state']:>10} {r['v1_conf']:7.4f}  {r['v2_state']:>10} {r['v2_conf']:7.4f} {cap_str:>5} {veto_str:>40} {rng:>18}")

# ── 增量多步：I2 跟踪 ──
print(f"\n{'='*90}")
print(f"  增量多步跟踪 (I2 好→反驳→澄清)")
print(f"{'='*90}")
print(f"{'step':>8} {'claim':>50} {'v1_state':>10} {'v1_conf':>8} {'v2_state':>10} {'v2_conf':>8}")
i2 = [r for r in results if r.get("group") == "I"]
config_standard = v2_mod.ProjectionConfig()
prev_conf = None
for step in ["I1a","I1b","I1c","I2a","I2b","I2c","I3a","I3b","I3c"]:
    r = next((x for x in i2 if x["tag"]==step), None)
    if not r:
        continue
    print(f"  {step:>8} {r['claim']:>50} {r['v1_state']:>10} {r['v1_conf']:8.4f} {r['v2_state']:>10} {r['v2_conf']:8.4f}")
    if step in ("I3c",):
        print()

# ── J组三档对比 ──
print(f"\n{'='*90}")
print(f"  J组: 三档策略同条对比")
print(f"{'='*90}")
print(f"{'Tag':>6} {'standard':>20} {'conservative':>20} {'permissive':>20}")
print(f"{'─'*90}")
for r in results:
    if r.get("group") != "J":
        continue
    std = f"{r['v2_state']} {r['v2_conf']:.4f}"
    con = f"{r['v2c_state']} {r['v2c_conf']:.4f}"
    per = f"{r['v2p_state']} {r['v2p_conf']:.4f}"
    print(f"  {r['tag']:>6} {std:>20} {con:>20} {per:>20}")

# ── 验证检查 ──
print(f"\n{'='*90}")
print(f"  验证检查")
print(f"{'='*90}")
pass_count = 0
fail_count = 0
for r in results:
    if "error" in r:
        continue
    # Find original case
    orig = next(c for c in CASES if c["tag"] == r["tag"])
    checks = []
    if orig["expect_state"] is not None:
        ok = r["v2_state"] == orig["expect_state"]
        checks.append(("state", ok, r["v2_state"]))
    if orig["expect_veto"] is not None:
        if callable(orig["expect_veto"]):
            ok = orig["expect_veto"](r["v2_veto"])
        else:
            ok = r["v2_veto"] == orig["expect_veto"]
        checks.append(("veto", ok, r["v2_veto"]))
    
    if checks:
        passed = all(c[1] for c in checks)
        if passed:
            pass_count += 1
        else:
            fail_count += 1
            fails = [c for c in checks if not c[1]]
            print(f"  [{r['tag']}] FAIL: ", "; ".join(f"{f[0]} got {f[2]}" for f in fails))

print(f"\n  验证: {pass_count} passed / {fail_count} failed / {len(results)} total")
