# Belief Assessor v2 — 投影层升级方案

## 一、现状 v1

```
FeatureExtractor.extract()
  ├── Layer 1: rule layer (4 continuous signals)
  ├── Layer 2: LLM layer (6 boolean features)
  ├── 质量因子 Q = 0.4*src + 0.3*density + 0.2*temporal + 0.1*provenance
  ├── support/refute scores from 6 bools
  ├── raw_conf = 0.6*semantic + 0.4*Q
  ├── incremental_update (alpha=0.5)
  ├── _determine_state: ≥0.65 VERIFIED / ≤0.25 UNCERTAIN / else CONTESTED
  └── confidence_range: [conf-0.15, conf+0.15]  ← 硬编码
```

硬伤: 阈值硬编码、置信区间固定、无约束保护。

## 二、v2 目标

1. **可配置阈值** — replace hardcoded 0.65/0.25/±0.15
2. **4 重约束** — 从完整版 projection.py 搬，只搬最有效的
3. **置信区间公式化** — 基于证据量 + 质量计算宽度
4. **参数化配置** — 一个 Config 对象替代 5 种 Policy 函数

## 三、4 重约束 (从完整版搬)

### 约束 1: Contradiction Cap（矛盾上限）
**来源**: `_project_conservative` / `_project_contradiction_sensitive`

```
if refute_score >= contest_threshold:
    cap = min(cap, contradiction_cap)  # default 0.55

if refute_score > support_score * 2:
    force_state = CONTESTED
```

- 当前 refute_score 来自 direct_refute(1.0) + error_outdated(0.6) / 1.6
- 即有明确反驳或错误信息时 → 置信度硬上限

### 约束 2: Provenance Quality Gate（溯源质量门禁）
**来源**: `_project_conservative` / `_project_authority_first`

```
if quality_factor < min_provenance_quality:
    cap = min(cap, provenance_cap)  # default 0.60
    cannot_be_VERIFIED = True
```

- 当前 quality_factor = 0.4*source_reliability + 0.3*evidence_density + 0.2*temporal_freshness + 0.1*provenance_quality
- 来自未知来源/无实据时 → 不配被标记为 VERIFIED

### 约束 3: Temporal Freshness Gate（时效门禁）
**来源**: `_determine_target_state` decay 分支

```
if temporal_freshness < decay_threshold:
    if state == VERIFIED → DEMOTE to CONTESTED
    cap = min(cap, temporal_cap)  # default 0.50
```

- 当前 temporal_freshness = 1/(1+age)，age 基于证据中最新年份
- 证据过时 → 即便置信度高也降级

### 约束 4: Evidence Density Floor（证据密度底线）
**来源**: `effective_root_count` 概念（统计数据中的根本约束）

```
if evidence_density < density_floor:
    cap = min(cap, density_cap)  # default 0.55
    cannot_be_VERIFIED = True
```

- 当前 evidence_density = min(1.0, 0.3 + segment_count * 0.2)
- 证据太少或太碎 → 不可标记为 VERIFIED

## 四、置信区间 (简化公式)

### 当前
```python
confidence_range = [conf - 0.15, conf + 0.15]  # 在所有情况下都一样
```

### v2 公式（从 `_project_conservative` 搬）
```python
n_eff = max(int(evidence_density * 10), 1)  # 从密度推导有效样本数
uncertainty_margin = (1.0 - quality_factor) * uncertainty_base + \
                     uncertainty_min / math.sqrt(n_eff)
lower = max(scalar - uncertainty_margin, 0.0)
upper = min(scalar + uncertainty_margin, confidence_cap)
```

**语义**: 
- 高质量证据 → 窄区间；低质量证据 → 宽区间
- 证据多 → 窄区间 (1/√n 收敛)；证据少 → 宽区间
- 区间始终受 cap 约束

## 五、ProjectionConfig (参数化替代5种Policy)

```python
@dataclass
class ProjectionConfig:
    # ── 阈值 ──
    verify_threshold: float = 0.75       # ≥此值为 VERIFIED
    contest_threshold: float = 0.25      # ≤此值为 UNCERTAIN (中间为 CONTESTED)

    # ── 约束参数 ──
    contradiction_cap: float = 0.55      # 约束1: 矛盾时的置信度上限
    provenance_cap: float = 0.60         # 约束2: 来源质量低时的置信度上限
    min_provenance_quality: float = 0.55 # 约束2: 来源质量门禁
    decay_threshold: float = 0.40        # 约束3: 时效性阈值
    temporal_cap: float = 0.50           # 约束3: 过时证据的置信度上限
    density_floor: float = 0.30          # 约束4: 证据密度底线
    density_cap: float = 0.55            # 约束4: 低密度时的置信度上限

    # ── 置信区间参数 ──
    uncertainty_base: float = 0.5        # (1-quality) 的缩放系数
    uncertainty_min: float = 0.1         # 1/sqrt(n_eff) 的缩放系数

    # ── 语义更新参数 ──
    alpha: float = 0.5                   # 增量更新混合系数

    # ── 预设 (只保留最有用的3个) ──
    @classmethod
    def conservative(cls) -> "ProjectionConfig":
        return cls(
            verify_threshold=0.78, contest_threshold=0.30,
            contradiction_cap=0.50, provenance_cap=0.55,
            min_provenance_quality=0.60, decay_threshold=0.35,
            temporal_cap=0.50, density_floor=0.35,
            uncertainty_base=0.55, uncertainty_min=0.12,
        )

    @classmethod
    def standard(cls) -> "ProjectionConfig":
        return cls()  # 默认值

    @classmethod
    def permissive(cls) -> "ProjectionConfig":
        return cls(
            verify_threshold=0.65, contest_threshold=0.20,
            contradiction_cap=0.60, provenance_cap=0.65,
            min_provenance_quality=0.45, decay_threshold=0.30,
            temporal_cap=0.55, density_floor=0.20,
            uncertainty_base=0.40, uncertainty_min=0.08,
        )
```

对比旧版5种Policy的公式差异，v2 的保守/标准/宽松 三档足够覆盖所有场景：

| 旧版 Policy | v2 等效 | 说明 |
|-------------|---------|------|
| conservative | `conservative()` | 高阈值 + 严格约束 |
| default / bayesian / authority_first | `standard()` | 标准阈值（均值） |
| contradiction_sensitive | `standard()` with higher contradiction_cap | 矛盾敏感 = 调低 contradiction_cap |

## 六、插入位置

在现有 `FeatureExtractor.extract()` 中，**raw_conf → final_confidence 之间**插入 `_project()` 方法：

```python
def extract(self, claim, evidence, previous_confidence=None, config=None):
    # ... 现有逻辑 ...
    
    # 原始置信度 (保持不变)
    result.raw_confidence = raw_conf
    
    # ★ v2: 投影层 (取代旧的 _incremental_update + _determine_state)
    cfg = config or ProjectionConfig()
    result = self._project(result, previous_confidence, cfg)
    
    return result
```

### `_project()` 实现逻辑

```python
def _project(self, result, prev_conf, cfg):
    scalar = result.raw_confidence
    cap = 1.0
    veto_reason = []
    
    # ── 4 重约束 ──
    
    # 约束 1: Contradiction Cap
    if result.refute_score >= cfg.contest_threshold:
        cap = min(cap, cfg.contradiction_cap)
        veto_reason.append("contradiction_capped")
    if result.refute_score > result.support_score * 2:
        result.state = "CONTESTED"
        veto_reason.append("contradiction_dominates")
    
    # 约束 2: Provenance Quality Gate
    if result.quality_factor < cfg.min_provenance_quality:
        cap = min(cap, cfg.provenance_cap)
        veto_reason.append("provenance_gated")
    
    # 约束 3: Temporal Freshness Gate
    if result.temporal_freshness < cfg.decay_threshold:
        cap = min(cap, cfg.temporal_cap)
        veto_reason.append("temporal_decayed")
    
    # 约束 4: Evidence Density Floor
    if result.evidence_density < cfg.density_floor:
        cap = min(cap, cfg.density_cap)
        veto_reason.append("density_floor")
    
    # ── 应用 cap ──
    scalar = min(scalar, cap)
    
    # ── 增量更新 (保留现有逻辑) ──
    if prev_conf is not None:
        scalar = self._incremental_update(scalar, prev_conf, cfg.alpha)
    
    # ── 置信区间 ──
    n_eff = max(int(result.evidence_density * 10), 1)
    uncertainty_margin = (
        (1.0 - result.quality_factor) * cfg.uncertainty_base +
        cfg.uncertainty_min / math.sqrt(n_eff)
    )
    lower = max(scalar - uncertainty_margin, 0.0)
    upper = min(scalar + uncertainty_margin, cap)
    
    result.final_confidence = scalar
    result.confidence_lower = lower
    result.confidence_upper = upper
    
    # ── 状态判定 (if not already set by constraints) ──
    if result.state != "CONTESTED":  # 约束可能已设
        cannot_verify = (
            result.quality_factor < cfg.min_provenance_quality or
            result.evidence_density < cfg.density_floor
        )
        if scalar >= cfg.verify_threshold and not cannot_verify:
            result.state = "VERIFIED"
        elif scalar <= cfg.contest_threshold:
            result.state = "UNCERTAIN"
        else:
            result.state = "CONTESTED"
    
    return result
```

## 七、变更文件清单

| 文件 | 变更 |
|------|------|
| `belief_state_runtime/projection.py` | **新建** — 包含 ProjectionConfig + `_project()` |
| `belief_state_runtime/feature_extractor.py` | 修改 `extract()` — 接入 `_project()`，移除旧的 `_determine_state()`<br>新增 `confidence_lower/confidence_upper` 到 FeatureResult |
| `belief_state_runtime/__init__.py` | `assess_claim()` 接受 `config: ProjectionConfig = None`<br>返回 `confidence_range` 改为使用 projection 计算的区间 |
| `belief_state_runtime/skill/SKILL.md` | 更新 API 文档 |

## 八、向 Agent 暴露的方式

```python
from belief_state_runtime import assess_claim, ProjectionConfig

# 默认 (标准策略)
result = assess_claim("声称", evidence="证据", llm_func=agent.llm)

# 保守策略
result = assess_claim("声称", llm_func=agent.llm, 
                      config=ProjectionConfig.conservative())

# 自定义
result = assess_claim("声称", llm_func=agent.llm,
                      config=ProjectionConfig(verify_threshold=0.80, 
                                              contradiction_cap=0.45))
```

## 九、不改的 (保持 v1 好的部分)

- ✅ Rule layer 4个信号 — 保持不变
- ✅ LLM layer 6个布尔特征 — 保持不变
- ✅ quality_factor 加权公式 — 保持不变
- ✅ support_score / refute_score 计算公式 — 保持不变
- ✅ incremental_update 逻辑 — 保持不变
- ✅ FeatureExtractor 自包含 + llm_func 注入 — 保持不变
- ✅ 零外部依赖（只依赖 math, re, json, dataclasses）— 保持不变

## 十、总结：v1 → v2 diff

| 维度 | v1 | v2 |
|------|------|------|
| 阈值 | 硬编码 0.65/0.25 | `ProjectionConfig` 可配置，3档预设 |
| 约束 | 无 | 4重：矛盾上限、来源门禁、时效门禁、密度底线 |
| 置信区间 | 固定 ±0.15 | 公式: (1-Q)×base + min/√n_eff |
| 策略数 | 1种(硬编码) | 1个Config类，3档预设，agent可自定义 |
| 复杂度增量 | — | +~80行 `projection.py`，extract 入口 +15行 |
| 外部依赖 | 0 | 0（只新增 math.sqrt） |
