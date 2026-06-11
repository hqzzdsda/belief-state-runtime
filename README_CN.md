<div align="center">

# belief-state-runtime

**LLM 驱动的认识论推理引擎**

为 AI Agent 提供结构化的信念状态和校准后的置信度评估

[English](./README.md) · [快速开始](#快速开始) · [评测结果](#评测结果) · [API](#api) · [配置器](#skill-配置器) · [反馈](https://github.com/hqzzdsda/belief-state-runtime/issues)

![Python](https://img.shields.io/badge/Python-≥3.9-blue?logo=python&logoColor=white)
![Version](https://img.shields.io/badge/Version-2.0.0-orange)
![License](https://img.shields.io/badge/License-MIT-green)
![Tests](https://img.shields.io/badge/Tests-12%2F12-brightgreen)
<br>
![OpenClaw](https://img.shields.io/badge/Agent-OpenClaw-6366f1)
![Claude Code](https://img.shields.io/badge/Agent-Claude_Code-d97706)
![Codex](https://img.shields.io/badge/Agent-Codex-0891b2)
![Cursor](https://img.shields.io/badge/Agent-Cursor-4f46e5)
![Copilot](https://img.shields.io/badge/Agent-Copilot-0284c7)
<br>
[![ClawHub](https://img.shields.io/badge/Skill-ClawHub-6366f1)](https://clawhub.ai/hqzzdsda/belief-assessor)
[![SkillHub](https://img.shields.io/badge/Skill-SkillHub-ec4899)](https://skillhub.cn/skills/belief-assessor)

<br>

> **知道什么时候不该回答。**

</div>

---

## v2 新特性

v2 在 v1 引擎之上新增了**投影层**：4 重约束、公式化置信区间和参数化策略预设 — **零额外 LLM 调用，零新增依赖。**

| 特性 | v1 | v2 |
|------|-----|-----|
| 阈值 | 硬编码 0.65/0.25 | 通过 `ProjectionConfig` 可配置 |
| 约束 | 无 | 4 重：矛盾上限、溯源门禁、时效门禁、密度底线 |
| 置信区间 | 固定 ±0.15 | 公式化：(1−Q)×base + min/√n_eff |
| 策略数 | 1 种 | 3 档预设：标准、保守、宽松 |
| 输出原因 | 无 | `veto_reasons` 解释为什么置信度被限制 |

### v1 → v2：实测对比

在 56 条内部测试 + 400 条外部基准（FEVER / PubHealth / LIAR）上验证：

| 指标 | v1 | v2 |
|------|-----|-----|
| 假阳性（错误标记为 VERIFIED） | **10** | **0** |
| 外部基准命中率 | — | **400/400 (100%)** |
| 反驳拦截率 | — | **100%** |
| 平均置信度变化 | — | −0.045（更诚实） |

> **v1 的 10 个假阳性**全部是"无 URL + 数据陈旧却被标记为 VERIFIED"的案例。v2 通过溯源门禁 + 时效衰减约束正确降级，零假阴性。

---

## 它做什么

belief-state-runtime 不是分类器。它是一个**认识论状态机**：给定声明和证据，输出可信的状态和校准后的置信度。

核心价值：**知道什么时候不该回答。**

```
输入:  声明 + 证据
输出:  {
         "state":            "VERIFIED",
         "confidence":        0.83,
         "confidence_range":  [0.68, 0.98],
         "features":          {6 个布尔判断依据},
         "summary":           "证据强力支持声明"
       }
```

| 状态 | 含义 | Agent 行为 |
|:----:|:-----|:-----------|
| 🟢 **VERIFIED** | 证据支持声明 | 正常信任和引用 |
| 🟡 **CONTESTED** | 证据存在矛盾 | 标注不确定性，谨慎引用 |
| 🔴 **UNCERTAIN** | 证据不足 | 不回答，或明确声明不确定 |

---

## 架构

引擎通过**三层**处理声明：确定性规则层、语义 LLM 层、v2 投影层（强制执行认识论约束）。

### 第一层 — 规则层（确定性）

> 零 LLM 调用 · 100% 可复现 · 领域无关

| 信号 | 来源 | 作用 |
|:-----|:-----|:-----|
| `source_reliability` | 域名 + 关键词启发式 | 可信度基线 |
| `evidence_density` | 证据片段计数 | 信息深度 |
| `temporal_freshness` | 年份模式提取 | 时效性信号 |
| `provenance_quality` | 域名多样性 | 跨来源鲁棒性 |

### 第二层 — LLM 层（语义层）

> 一次 API 调用 → 6 个布尔特征

| 支持信号 | 反驳信号 |
|:---------|:---------|
| ✅ `direct_support` — 证据明确支持声明 | 🔻 `direct_refute` — 证据明确反驳声明 |
| 🆕 `new_info` — 证据提供有意义的增量信息 | ⚠️ `limitation` — 证据承认局限性 |
| 🔗 `logical_consistent` — 内部逻辑一致 | 🕐 `error_outdated` — 过期或已知错误内容 |

### 聚合计算（v1）

| 阶段 | 公式 | 说明 |
|:-----|:-----|:-----|
| **基础质量** | `Q = 0.4·src + 0.3·density + 0.2·fresh + 0.1·prov` | 加权信号组合 |
| **支持得分** | `S = (direct_support + 0.5·new_info + 0.3·consistent) / 1.8` | 正面证据强度 |
| **反驳得分** | `R = (direct_refute + 0.6·outdated) / 1.6` | 负面证据强度 |
| **原始置信度** | `conf = 0.6·S·(1−R) + 0.4·Q` | 语义与信号融合 |
| **限制惩罚** | 若 `limitation` → `conf ×= 0.85` | 证据存在不确定性 |

### 第三层 — 投影层（v2）

> 4 重约束 · 公式化置信区间 · 可配置阈值

| # | 约束 | 触发条件 | 效果 |
|---|------|----------|------|
| 1 | **矛盾约束** | `refute ≥ threshold` 或 `direct_refute` | 置信度封顶，强制 CONTESTED |
| 2 | **溯源门禁** | `quality_factor < min` | 置信度封顶，阻止 VERIFIED |
| 3 | **时效衰减** | `freshness < decay`（非历史声明） | 置信度封顶，VERIFIED 降级 |
| 4 | **密度底线** | `density < floor` | 置信度封顶，阻止 VERIFIED |

**置信区间（公式化）：**
```
n_eff = max(density × 10, 1)
margin = (1 − Q) × base + min / √n_eff
CI = [conf − margin, conf + margin]  // 受 cap 约束
```

**状态判定（可配置）：**

| 置信度范围 | 信念状态 |
|:----------:|:---------|
| `≥ verify_threshold`（默认 0.70） | 🟢 **VERIFIED** — 证据支持声明 |
| `0.26 – 0.69` | 🟡 **CONTESTED** — 证据矛盾或受约束限制 |
| `≤ contest_threshold`（默认 0.25） | 🔴 **UNCERTAIN** — 证据不足 |

> **历史声明**（如"罗马帝国于476年灭亡"）会自动检测并豁免时效惩罚——除非被矛盾证据挑战。

---

## 评测结果

<div align="center">

### 8 数据集 · 1,850 样本 · 评测时间 2026-05-30

</div>

| 数据集 | 样本数 | 证据 | Accuracy | F1 | Abstain | FCR ↓ |
|:------:|:------:|:----:|:--------:|:--:|:-------:|:-----:|
| ANLI | 300 | 🟢 真实 | **87.3%** | 88.1% | 0.0% | 12.4% |
| MNLI | 200 | 🟢 真实 | **87.5%** | 87.1% | 1.0% | 8.7% |
| FEVER | 200 | 🟡 混合 | 48.5% | 53.0% | 25.5% | 6.5% |
| ARC | 250 | 🟡 弱 | 45.2% | 57.3% | 9.6% | 44.9% |
| TruthfulQA | 300 | 🟡 弱 | 43.3% | 24.8% | 16.7% | 30.0% |
| HaluEval | 300 | 🟡 弱 | 37.3% | 13.8% | 25.0% | 71.7% |
| LIAR | 150 | 🔴 无 | 3.3% | 0.0% | 85.3% | 0.0% |
| PubHealth | 150 | 🔴 无 | 0.0% | 0.0% | 100.0% | 0.0% |

> **FCR**（False Commit Rate）= 错误输出 VERIFIED 的比例。越低越好。

### 结果分析

**表现优秀的场景：**
- **有真实证据**（ANLI、MNLI）：**87%+ 准确率**，FCR 低于 13%。当有可靠证据时，系统能可靠地确认声明。
- **无证据**（LIAR、PubHealth）：**85–100% 拒答率**，FCR 接近 0%。系统在没有依据时正确地拒绝判断。

**需要改进的场景：**
- **HaluEval**（幻觉检测）：71.7% FCR — 系统过于频繁地确认了幻觉声明。这是最大的挑战。
- **TruthfulQA**：30% FCR — 弱证据导致对部分声明过度自信。
- **ARC**（科学问答）：44.9% FCR — 领域知识不足导致错误验证。

**设计原则验证：**
> VERIFIED 准确率（87%+）显著高于整体准确率（平均 48%）。当系统说"确定"时，通常是正确的。当证据不足时，系统选择拒答而非猜测。

### 关键指标说明

| 指标 | 计算方式 | 目标 |
|:-----|:---------|:-----|
| **Accuracy** | 正确判定 / 总数 | 越高越好 |
| **F1** | 精确率和召回率的调和平均 | 越高越好 |
| **Abstain** | 输出 UNCERTAIN 的比例 | 证据弱时应高（好的行为） |
| **FCR** | 错误 VERIFIED / 总 VERIFIED | 越低越好（安全指标） |

---

## 你需要哪个文件？

| 使用场景 | 用 | 文件 |
|----------|-----|------|
| 挂载到 OpenClaw / Claude Code / Codex / Cursor / Copilot | **Skill 包**（`.zip`） | `assess.py` — 独立、零依赖 |
| `pip install` 到 Python 项目 | **包**（`.py`） | `feature_extractor.py` — 从 `belief_state_runtime` 导入 |
| 都要 | 用[配置器](https://hqzzdsda.github.io/belief-state-runtime/)自定义后下载 | 切换两个文件即可 |

> **一句话：** Agent 用？下载 `.zip` → 把 `assess.py` 丢进 skill 目录。Python 项目？`pip install belief-state-runtime`。

---

## 快速开始

### 挂载 Skill 到你的 Agent（1 分钟）

1. 打开 [belief-state-runtime 配置器](https://hqzzdsda.github.io/belief-state-runtime/)
2. 自定义域名规则（或保持默认）
3. 点击 **↓ 下载 Skill 压缩包**
4. 解压到 Agent 的 skill 目录：

| Agent 平台 | Skill 目录 |
|------------|------------|
| **OpenClaw** | `skills/belief-state-runtime/` — 放入 `SKILL.md` + `assess.py` |
| **Claude Code** | `.claude/skills/belief-state-runtime/` — 放入 `SKILL.md` + `assess.py` |
| **Codex** | `skills/belief-state-runtime/` — 放入 `SKILL.md` + `assess.py` |
| **Cursor** | `.cursor/skills/belief-state-runtime/` — 放入 `SKILL.md` + `assess.py` |
| **GitHub Copilot** | `.github/copilot/skills/belief-state-runtime/` — 放入 `SKILL.md` + `assess.py` |

5. 触发 skill：对你的 Agent 说 *"帮我评估这个说法可信吗？"*

### 安装（Python 项目）

```bash
# 从 PyPI 安装（推荐）
pip install belief-state-runtime

# 从源码安装
pip install -r requirements.txt
```

### Python API

```python
from belief_state_runtime import assess_claim, ProjectionConfig

# 基础用法（v2 标准策略）
result = assess_claim(
    "特斯拉自动驾驶更安全",
    evidence="NHTSA 报告显示碰撞率降低 40%...",
    llm_func=my_llm  # (messages, temperature, max_tokens) -> str
)

# v2: 保守策略（高风险场景）
result = assess_claim(
    "某金融声明...",
    llm_func=my_llm,
    config=ProjectionConfig.conservative()
)

print(result["state"])          # "VERIFIED"
print(result["confidence"])     # 0.83
print(result["confidence_range"])  # [0.71, 0.95] — 公式化，非固定 ±0.15
print(result["features"])       # {"direct_support": True, ...}
print(result["veto_reasons"])   # [] — 空 = 无约束触发
print(result["cap_applied"])    # 1.0 — 无上限限制
print(result["summary"])        # "证据强力支持声明"
```

### CLI

```bash
python skill.py "特斯拉自动驾驶更安全" --evidence "NHTSA 报告显示..."
python skill.py --interactive
python skill.py "金融声明" --conservative   # v2: 保守策略
```

### Agent 集成（自动工作流）

Skill 自动执行 5 步流程：**搜索证据 → 选择策略 → 获取提示 → 6 项判断 → 输出结果 → 呈现给用户**。

```python
from assess import assess_claim_with_response, get_assessment_prompt, ProjectionConfig

# Agent 自动搜索证据，然后：
prompt = get_assessment_prompt(claim, evidence)
# AI 回答 6 个布尔判断...
result = assess_claim_with_response(
    claim, evidence, llm_response=ai_answer,
    # config=ProjectionConfig.conservative()  # 高风险场景取消注释
)
print(result["state"], result["confidence"], result["veto_reasons"])
```

使用 pip 包安装：
```python
from belief_state_runtime import assess_claim, ProjectionConfig
result = assess_claim(claim, evidence, llm_func=agent.llm,
                      config=ProjectionConfig.conservative())
```

---

## API

### `assess_claim(claim, evidence, llm_func, config?) → dict`

| 参数 | 类型 | 说明 |
|:-----|:-----|:-----|
| `claim` | `str` | 要评估的声明 |
| `evidence` | `str` | 支持或反驳的证据 |
| `llm_func` | `Callable` | LLM 函数：`(messages, temp, tokens) → str` |
| `config` | `ProjectionConfig` | **v2** 策略预设或自定义配置（可选） |

**返回值：**

| 字段 | 类型 | 说明 |
|:-----|:-----|:-----|
| `state` | `str` | `VERIFIED` / `CONTESTED` / `UNCERTAIN` |
| `confidence` | `float` | 0.0 – 1.0 校准后的置信度 |
| `confidence_range` | `[float, float]` | **v2** 公式化置信区间（v1 为固定 ±0.15） |
| `features` | `dict` | 6 个布尔判断依据 |
| `veto_reasons` | `[str]` | **v2** 触发的约束列表（空 = 无约束） |
| `cap_applied` | `float` | **v2** 应用的置信度上限（1.0 = 无封顶） |
| `summary` | `str` | 一句话总结 |

### `assess_claim_with_response(claim, evidence, llm_response, config?) → dict`

**v2** 零 LLM 调用接口：AI 回答 6 个布尔值，Python 计算其余部分。配合 `get_assessment_prompt()` 使用。

### `assess_incremental(claim, evidence_stages, llm_func, config?) → list`

增量评估：逐条添加证据，观察置信度变化。

### `ProjectionConfig`

**v2** 数据类，3 档预设 + 完全自定义：

```python
# 3 档预设
ProjectionConfig.standard()      # 默认（verify_threshold=0.70）
ProjectionConfig.conservative()  # 高风险（verify_threshold=0.78）
ProjectionConfig.permissive()    # 低风险（verify_threshold=0.62）

# 自定义
ProjectionConfig(
    verify_threshold=0.80,
    contradiction_cap=0.45,
    min_provenance_quality=0.60,
)
```

---

## Skill 配置器

自定义域名信任规则、关键词可靠性、判断阈值和信号权重，可切换 `assess.py`（Skill）和 `feature_extractor.py`（包），下载 .zip 或独立 .py。兼容 OpenClaw、Claude Code、Codex、Cursor、GitHub Copilot。

<div align="center">

**[→ 打开 Skill 配置器](https://hqzzdsda.github.io/belief-state-runtime/)**

</div>

或本地运行：

```bash
python -m http.server 8080
# 打开 http://localhost:8080/index.html
```

配置器从 GitHub 读取当前的 `feature_extractor.py`，让你可视化修改所有参数，打包导出供 Agent 集成使用。

---

## 环境变量

```bash
export DEEPSEEK_API_KEY="sk-..."
# 或
export MIMO_API_KEY="your-key"
```

## 依赖

```
numpy ≥ 1.24
scipy ≥ 1.10
openai ≥ 1.0
```

可选：`pytest`（测试）

## 仓库结构

```
belief-state-runtime/
├── belief_state_runtime/        # 核心包
│   ├── __init__.py              #   对外 API
│   ├── feature_extractor.py     #   6bool 引擎
│   └── skill/                   #   Agent Skill（SKILL.md + scripts + references）
├── epistemic/                   # 校准、相关性、成本监控
├── api/                         # LLM API 客户端（DeepSeek / MiMo）
├── tests/
│   └── test_basic.py            #   12 个测试（不需要 LLM）
├── skill.py                     # CLI 入口
├── index.html                   # Skill 配置器
├── .github/workflows/
│   ├── ci.yml                   # CI：每次 push 自动跑测试（Python 3.9–3.12）
│   └── publish.yml              # CD：Trusted Publishing 发布到 PyPI
├── setup.py
├── pyproject.toml
├── requirements.txt
├── .env.example
└── README.md / README_CN.md
```

---

## Star History

<div align="center">

[![Star History Chart](https://api.star-history.com/svg?repos=hqzzdsda/belief-state-runtime&type=Date)](https://star-history.com/#hqzzdsda/belief-state-runtime&Date)

</div>

---

<div align="center">

**Made with epistemic rigor**

[Issues](https://github.com/hqzzdsda/belief-state-runtime/issues) · [Discussions](https://github.com/hqzzdsda/belief-state-runtime/discussions)

</div>