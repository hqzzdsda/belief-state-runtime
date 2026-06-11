# belief-assessor v2 — 挂载 Agent 对比测试集

## 测试目标
证明 v2 的 4 重约束提供了 v1 没有的额外信息（veto_reasons、公式化区间、可切换策略）。

## 测试流程
```
Agent 收到 claim
  → 搜索证据 (online-search / multi-search-engine)
  → 调用 assess_claim_with_response(claim, evidence, ai_6bool)
  → 对比 v1 输出 vs v2 输出
```

## 测试用例 (10 条，覆盖 4 重约束)

### 组 A: 好证据 — 应该 VERIFIED (v1=v2)

| # | Claim | 预期证据来源 | v2 预期 |
|---|-------|------------|---------|
| A1 | "中国高铁运营里程超过4万公里" | 国家铁路局/交通运输部官方数据 | VERIFIED, veto=[] |
| A2 | "2024年全球平均气温创历史新高" | NASA/NOAA/WMO报告 | VERIFIED, veto=[] |
| A3 | "DeepSeek V3在多个基准上超越GPT-4o" | 官方benchmark/第三方评测 | VERIFIED, veto=[] |

### 组 B: 来源质量差 — v1 可能误判，v2 应 gated

| # | Claim | 预期证据 | v1 预期 | v2 预期 |
|---|-------|---------|---------|---------|
| B1 | "某个小币种明天会涨100倍" | 匿名Telegram/微信群转发 | ⚠️ 可能 CONTESTED 但看不出原因 | CONTESTED, veto=[provenance_gated,density_floor] |
| B2 | "喝XX保健品能治愈癌症" | 个人博客/小红书笔记 | ⚠️ 可能 CONTESTED | CONTESTED, veto=[provenance_gated] |
| B3 | "某明星私生活爆料" | 匿名论坛帖子 | ⚠️ 可能 UNCERTAIN | UNCERTAIN, veto=[provenance_gated,density_floor] |

### 组 C: 直接反驳 — v1=v2 状态一致，但 v2 多了原因

| # | Claim | 预期证据 | v2 预期 |
|---|-------|---------|---------|
| C1 | "比特币在2024年跌破1万美元" | 实际数据显示2024年BTC最高超10万 | CONTESTED, veto=[contradiction_capped,contradiction_dominates] |
| C2 | "日本2024年GDP负增长" | IMF/日本内阁府数据显示正增长 | CONTESTED, veto=[contradiction_capped] |

### 组 D: 时效问题 — v1 忽略，v2 应降级

| # | Claim | 预期证据 | v2 预期 |
|---|-------|---------|---------|
| D1 | "COVID-19死亡率约3.4%" | 2020年WHO早期数据 | CONTESTED, veto=[temporal_decayed] |
| D2 | "中国GDP增速超过10%" | 2010年统计数据 | CONTESTED, veto=[temporal_decayed] |

### 组 E: 多约束同时触发 — 验证 cap 取 min 逻辑

| # | Claim | 预期证据特征 | v2 预期 |
|---|-------|------------|---------|
| E1 | "2020年某匿名论坛说XX保健品能治新冠" | 论坛来源(provenance↓) + 2020年数据(temporal↓) + 只有一段话(density↓) | CONTESTED, veto=[provenance_gated,temporal_decayed,density_floor] |
| E2 | "2018年某个个人博客声称比特币会取代美元" | 博客来源(provenance↓) + 2018年(temporal↓) + 一段话(density↓) | CONTESTED, veto=[provenance_gated,temporal_decayed,density_floor] |
| E3 | "Reddit匿名帖说某CEO即将辞职(无时间、无出处)" | 论坛(density↓+provenance↓) + 可能无年份 | CONTESTED, veto=[provenance_gated,density_floor] |

### 组 F: 边界值 — conf 在阈值附近的行为

| # | Claim | 场景设计 | v2 预期 |
|---|-------|---------|---------|
| F1 | evidence支持力度刚好让 raw_conf≈0.68-0.72 | 中等质量证据，在 standard verify_threshold=0.70 附近 | 看具体值，边缘状态应合理 |
| F2 | evidence几乎为空，raw_conf≈0.23-0.27 | 极弱证据，在 contest_threshold=0.25 附近 | 看具体值 |
| F3 | evidence质量刚好 quality_factor≈0.53-0.57 | 在 min_provenance_quality=0.55 边缘 | 看 provenance_gated 是否准确触发 |

### 组 G: 混合证据 — 同一证据内质量参差

| # | Claim | 证据内容 | v2 预期 |
|---|-------|---------|---------|
| G1 | "中国新能源汽车销量全球第一" | 混合: 工信部官网链接 + 一篇知乎分析文章 | source_reliability 取平均，但高质量证据整体拉高 Q |
| G2 | "某AI模型性能超越人类" | 混合: arxiv论文链接 + Twitter网友评价 | 两个来源，provenance_quality 因双域名提高，但 source_reliability 平均 |
| G3 | 同 G2，但去掉论文只留Twitter | Twitter单来源 vs G2 双来源 | 对比 G2 看 source_reliability 和 Q 的差异 |

### 组 H: 空/极弱证据

| # | Claim | 证据 | v2 预期 |
|---|-------|------|---------|
| H1 | "XX技术是未来趋势" | evidence="" | UNCERTAIN, 验证默认值 (source=0.4, density=0.0, temporal=0.7, provenance=0.5) |
| H2 | 同 H1 | evidence="是的" (只有2个中文字) | density 应极低，可能触发 density_floor |
| H3 | 同 H1 | evidence="https://gov.cn 官方报告显示..." 但文字极少 | 与 H1/H2 对比，有 gov 域名但内容少 |

### 组 I: 增量多步 — 信念随证据演化

| # | Claim | 证据序列 | v2 预期 |
|---|-------|---------|---------|
| I1 | "维生素D能预防COVID" | Step1: 2020西班牙观察性研究(暗示相关) → Step2: 2021英国RCT(无显著效果) → Step3: 2022荟萃分析(证据不足) | conf 应逐步降低，Step2/3 触发 temporal_decayed |
| I2 | "某公司Q3财报超预期" | Step1: 官方财报(好) → Step2: 做空机构报告(反驳) → Step3: 公司回应澄清(支持) | conf 好→骤降→回升，Step2 触发 contradiction |
| I3 | "某个城市房价要涨" | Step1: 一篇自媒体文章 → Step2: 统计局数据 → Step3: 多家机构研报 | conf 应从低位逐步提升，Step1 触发约束 |

### 组 J: 三档预设同条对比

| # | Claim | 关注 |
|---|-------|------|
| J1 | 好证据(cf. A1) | standard→VERIFIED, conservative→是否降为CONTENTED? |
| J2 | 差证据(cf. B1) | 三档是否一致 CONTESTED，conservative conf 更低？ |
| J3 | 边界证据(cf. F1) | standard 和 conservative 可能状态不同 — 这正是策略切换的意义 |

## 对比关注点

对每条 claim 记录：

| 维度 | 看什么 |
|------|--------|
| 状态一致性 | v1.state vs v2.state 是否一致？不一致是否合理？ |
| 置信度差异 | v2 的 cap 是否压低了不该高的置信度？ |
| veto_reasons | 约束触发是否合理？（B组应触发、A组不应） |
| 置信区间 | v2 区间是否更窄（好证据）或更宽（差证据）？v1固定±0.15 |
| 策略切换 | 同一条claim，conservative vs permissive 输出差异是否合理？ |

## 运行方式

1. 安装 belief-assessor-v2 skill
2. 逐条扔给 agent，让 agent 搜索 → 评估 → 输出
3. 同时跑 v1 做基线对比（同一套 6 bool）
4. 记录每条结果的 state/confidence/veto_reasons/confidence_range

## 最小可行测试（5条快速验证）

如果时间有限，先跑这 5 条就能覆盖核心差异：

1. ✅ A1 高铁里程（好证据 → VERIFIED, veto=[]）
2. ❌ B1 小币种暴涨（差证据 → CONTESTED, veto 非空）
3. ⏰ D1 COVID死亡率3.4%（过时证据 → CONTESTED, veto 含 temporal_decayed）
4. ⚡ E1 三约束同时触发（过时+论坛+稀疏 → 验证 cap 取 min）
5. 🔀 I2 增量反驳（好→反驳→澄清 → 验证增量多步）
