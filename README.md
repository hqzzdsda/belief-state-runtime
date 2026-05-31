<div align="center">

# belief-state-runtime

**LLM-driven epistemic reasoning engine**

Structured belief states and calibrated confidence for AI Agents

[中文](./README_CN.md) · [Quick Start](#quick-start) · [Benchmarks](#benchmarks) · [Skill](#skill-configurator) · [Feedback](https://github.com/hqzzdsda/belief-state-runtime/issues)

![Python](https://img.shields.io/badge/Python-≥3.9-blue?logo=python&logoColor=white)
![Version](https://img.shields.io/badge/Version-1.0.0-orange)
![License](https://img.shields.io/badge/License-MIT-green)
![Tests](https://img.shields.io/badge/Tests-12%2F12-brightgreen)
<br>
![OpenClaw](https://img.shields.io/badge/Agent-OpenClaw-6366f1)
![Claude Code](https://img.shields.io/badge/Agent-Claude_Code-d97706)
![Codex](https://img.shields.io/badge/Agent-Codex-0891b2)
![Cursor](https://img.shields.io/badge/Agent-Cursor-4f46e5)
![Copilot](https://img.shields.io/badge/Agent-Copilot-0284c7)

<br>

> **Know when not to answer.**

</div>

---

## What It Does

belief-state-runtime is not a classifier. It is an **epistemic state machine**: given a claim and evidence, it outputs a trustworthy state and calibrated confidence.

Core value: **knowing when not to answer.**

```
Input:  claim + evidence
Output: {
          "state":            "VERIFIED",
          "confidence":        0.83,
          "confidence_range":  [0.68, 0.98],
          "features":          {6 boolean judgments},
          "summary":           "Evidence strongly supports the claim"
        }
```

| State | Meaning | Agent Behavior |
|:-----:|:--------|:---------------|
| 🟢 **VERIFIED** | Evidence supports claim | Trust and cite normally |
| 🟡 **CONTESTED** | Evidence contradicts | Flag uncertainty, cite cautiously |
| 🔴 **UNCERTAIN** | Insufficient evidence | Abstain — don't answer |

---

## Architecture

The engine processes claims through **two complementary layers**, then aggregates results into a calibrated belief state.

### Layer 1 — Rules (Deterministic)

> Zero LLM calls · 100% reproducible · Domain-agnostic

| Signal | Source | Purpose |
|:-------|:-------|:--------|
| `source_reliability` | Domain + keyword heuristics | Trustworthiness baseline |
| `evidence_density` | Fragment count | Information depth |
| `temporal_freshness` | Year pattern extraction | Recency signal |
| `provenance_quality` | Domain diversity | Cross-source robustness |

### Layer 2 — LLM (Semantic)

> One API call → 6 boolean features

| Supporting Signals | Refuting Signals |
|:-------------------|:-----------------|
| ✅ `direct_support` — evidence explicitly backs claim | 🔻 `direct_refute` — evidence explicitly contradicts |
| 🆕 `new_info` — evidence adds meaningful content | ⚠️ `limitation` — evidence acknowledges gaps |
| 🔗 `logical_consistent` — internal logic holds | 🕐 `error_outdated` — stale or known-error content |

### Aggregation

| Stage | Formula | Notes |
|:------|:--------|:------|
| **Baseline quality** | `Q = 0.4·src + 0.3·density + 0.2·fresh + 0.1·prov` | Weighted signal composite |
| **Support score** | `S = (direct_support + 0.5·new_info + 0.3·consistent) / 1.8` | Positive evidence strength |
| **Refute score** | `R = (direct_refute + 0.6·outdated) / 1.6` | Negative evidence strength |
| **Raw confidence** | `conf = 0.6·S·(1−R) + 0.4·Q` | Blend of semantics and signals |
| **Limitation penalty** | If `limitation` → `conf ×= 0.85` | Evidence admits uncertainty |
| **Direct refute cap** | If `direct_refute` → `conf ≤ 0.60` | Cannot exceed CONTESTED boundary |

| Confidence Range | Belief State |
|:----------------:|:-------------|
| `≥ 0.65` | 🟢 **VERIFIED** — Claim supported by evidence |
| `0.26 – 0.64` | 🟡 **CONTESTED** — Mixed or contradictory |
| `≤ 0.25` | 🔴 **UNCERTAIN** — Insufficient basis |

---

## Benchmarks

<div align="center">

### 8 Datasets · 1,850 Samples

</div>

| Dataset | Samples | Evidence | Accuracy | F1 | Abstain | FCR ↓ |
|:-------:|:-------:|:--------:|:--------:|:--:|:-------:|:-----:|
| ANLI | 300 | 🟢 Real | **87.3%** | 88.1% | 0.0% | 12.4% |
| MNLI | 200 | 🟢 Real | **87.5%** | 87.1% | 1.0% | 8.7% |
| FEVER | 200 | 🟡 Mixed | 48.5% | 53.0% | 25.5% | 6.5% |
| ARC | 250 | 🟡 Weak | 45.2% | 57.3% | 9.6% | 44.9% |
| TruthfulQA | 300 | 🟡 Weak | 43.3% | 24.8% | 16.7% | 30.0% |
| HaluEval | 300 | 🟡 Weak | 37.3% | 13.8% | 25.0% | 71.7% |
| LIAR | 150 | 🔴 None | 3.3% | 0.0% | 85.3% | 0.0% |
| PubHealth | 150 | 🔴 None | 0.0% | 0.0% | 100.0% | 0.0% |

> **FCR** (False Commit Rate) = fraction of VERIFIED outputs that are wrong. Lower is better.

### Metric Definitions

| Metric | Formula | Goal |
|:-------|:--------|:-----|
| **Accuracy** | Correct / Total | Higher is better |
| **F1** | Harmonic mean of precision & recall | Higher is better |
| **Abstain** | % outputting UNCERTAIN | High when evidence is weak (safe behavior) |
| **FCR** | Wrong VERIFIED / Total VERIFIED | Lower is better (safety metric) |

<div align="center">

**Design Principles**
VERIFIED accuracy > overall accuracy · UNCERTAIN is a valid output · Confidence is calibratable

</div>

---

## Which File Do I Need?

| Scenario | Use | File |
|----------|-----|------|
| Mount skill in OpenClaw / Claude Code / Codex / Cursor / Copilot | **Skill package** (`.zip`) | `assess.py` — self-contained, zero-dependency |
| `pip install` in your Python project | **Package** (`.py`) | `feature_extractor.py` — import from `belief_state_runtime` |
| Both | Use [configurator](https://hqzzdsda.github.io/belief-state-runtime/) to customize and download | Toggle between the two files |

> **TL;DR:** Agent? Download `.zip` → drop `assess.py` in your skill folder. Python project? `pip install belief-state-runtime`.

---

## Quick Start

### Mount Skill in Your Agent (1 minute)

1. Go to [belief-state-runtime configurator](https://hqzzdsda.github.io/belief-state-runtime/)
2. Customize domain rules (or keep defaults)
3. Click **↓ DOWNLOAD .ZIP**
4. Extract to your agent's skill directory:

| Agent Platform | Skill directory |
|----------------|-----------------|
| **OpenClaw** | `skills/belief-state-runtime/` — drop `SKILL.md` + `assess.py` |
| **Claude Code** | `.claude/skills/belief-state-runtime/` — drop `SKILL.md` + `assess.py` |
| **Codex** | `skills/belief-state-runtime/` — drop `SKILL.md` + `assess.py` |
| **Cursor** | `.cursor/skills/belief-state-runtime/` — drop `SKILL.md` + `assess.py` |
| **GitHub Copilot** | `.github/copilot/skills/belief-state-runtime/` — drop `SKILL.md` + `assess.py` |

5. Trigger the skill: ask your agent *"Is this claim trustworthy?"*

### Install (Python project)

```bash
# From PyPI (recommended)
pip install belief-state-runtime

# From source
pip install -r requirements.txt
```

### Python API

```python
from belief_state_runtime import assess_claim

result = assess_claim(
    "Tesla FSD is safer than human drivers",
    evidence="NHTSA reports show collision rate reduced by 40%...",
    llm_func=my_llm  # (messages, temperature, max_tokens) -> str
)

print(result["state"])       # "VERIFIED"
print(result["confidence"])  # 0.83
print(result["features"])    # {"direct_support": True, ...}
print(result["summary"])     # "Evidence strongly supports the claim"
```

### CLI

```bash
python skill.py "Tesla FSD is safer" --evidence "NHTSA reports show..."
python skill.py --interactive
```

### Agent Integration (AUTO WORKFLOW)

The skill auto-executes a 5-step workflow: **search evidence → get prompt → 6 judgments → result → present to user**.

```python
from assess import assess_claim_with_response, get_assessment_prompt

# Agent searches evidence automatically, then:
prompt = get_assessment_prompt(claim, evidence)
# AI answers the 6 boolean judgments...
result = assess_claim_with_response(claim, evidence, llm_response=ai_answer)
print(result["state"], result["confidence"])
```

Using package install:
```python
from belief_state_runtime import assess_claim
result = assess_claim(claim, evidence, llm_func=agent.llm)
```

---

## API

### `assess_claim(claim, evidence, llm_func) → dict`

| Param | Type | Description |
|:------|:-----|:------------|
| `claim` | `str` | Claim to assess |
| `evidence` | `str` | Supporting or refuting evidence |
| `llm_func` | `Callable` | LLM function: `(messages, temp, tokens) → str` |

**Returns:**

| Field | Type | Description |
|:------|:-----|:------------|
| `state` | `str` | `VERIFIED` / `CONTESTED` / `UNCERTAIN` |
| `confidence` | `float` | 0.0 – 1.0 calibrated confidence |
| `confidence_range` | `[float, float]` | Confidence interval |
| `features` | `dict` | 6 boolean judgments |
| `summary` | `str` | One-sentence explanation |

### `assess_incremental(claim, evidence_stages, llm_func) → list`

Incremental assessment: add evidence stage by stage, observe confidence evolution.

---

## Skill Configurator

Customize domain trust rules, keyword reliability, judgment thresholds, and signal weights. Toggle between `assess.py` (skill) and `feature_extractor.py` (package), then download as .zip or standalone .py. Compatible with OpenClaw, Claude Code, Codex, Cursor, and GitHub Copilot.

<div align="center">

**[→ Open Skill Configurator](https://hqzzdsda.github.io/belief-state-runtime/)**

</div>

Or run locally:

```bash
python -m http.server 8080
# Open http://localhost:8080/index.html
```

The configurator reads your current `feature_extractor.py` from GitHub, lets you modify all parameters visually, and packages your customized skill for agent integration.

---

## Environment

```bash
export DEEPSEEK_API_KEY="sk-..."
# or
export MIMO_API_KEY="your-key"
```

## Dependencies

```
numpy ≥ 1.24
scipy ≥ 1.10
openai ≥ 1.0
```

## Repository Structure

```
belief-state-runtime/
├── belief_state_runtime/        # Core package
│   ├── __init__.py              #   Public API
│   ├── feature_extractor.py     #   6-bool engine
│   └── skill/                   #   Agent Skill (SKILL.md + scripts + references)
├── epistemic/                   # Calibration, correlation, cost monitoring
├── api/                         # LLM API client (DeepSeek / MiMo)
├── tests/
│   └── test_basic.py            #   12 tests (no LLM needed)
├── skill.py                     # CLI entry
├── index.html                   # Skill configurator
├── .github/workflows/
│   ├── ci.yml                   # CI: test on push (Python 3.9–3.12)
│   └── publish.yml              # CD: Trusted Publishing to PyPI
├── setup.py
├── pyproject.toml
├── requirements.txt
├── .env.example
└── README.md / README_CN.md
```

## Star History

<div align="center">

[![Star History Chart](https://api.star-history.com/svg?repos=hqzzdsda/belief-state-runtime&type=Date)](https://star-history.com/#hqzzdsda/belief-state-runtime&Date)

</div>

---

<div align="center">

**Made with epistemic rigor**

[Issues](https://github.com/hqzzdsda/belief-state-runtime/issues) · [Discussions](https://github.com/hqzzdsda/belief-state-runtime/discussions)

</div>