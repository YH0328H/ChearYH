# CetherYH 开发日志

## 2026-11-02 (周六)

**工作时间**: 约 4 小时 15 分钟（11:00-15:15）

### 已完成模块

#### 1. 记忆流水线（L1 叙事）
- ✅ L1 存储结构（`L1Record`、`L1Archive`）
- ✅ 候选池（容量限制、过期策略、与热库隔离）
- ✅ 叙事生成（后台槽位调用、结构化返回）
- ✅ L1 触发检测（五个明确条件：手动、关系事件、高情绪/显著、短期重复）
- ✅ 终审逻辑（验证、兜底策略，无运行时随机）

#### 2. 检索融合（三路）
- ✅ BM25 词法检索（k1/b 可配置）
- ✅ 向量语义检索（cosine similarity，BGE-M3 1024维）
- ✅ 图扩散检索（简化版，一跳邻居+共现权重）
- ✅ RRF 融合（k=60）
- ✅ 复合乘子偏置（lifecycle、rumination、drive、valence、region、jitter）

#### 3. 状态演化（第一批）
- ✅ 惊讶度计算（Jaccard 相似度，预测误差驱动）
- ✅ 一阶惯性滤波（平滑状态过渡，α=0.7）
- ✅ 六维驱力→四意愿投影（基于 PSI/SDT/Panksepp 理论）
- ✅ 质地翻译器（数值→自然语言）
- ✅ 艾宾浩斯/Weibull 衰减（记忆权重衰减）

#### 4. 项目架构与文档
- ✅ 三份任务书统一理解（v1.0/v2.0/PRD 协调）
- ✅ 算法清单归档（ALGORITHMS.md，分批次，防遗忘）
- ✅ 架构原则（ARCHITECTURE.md：参数预设化、逻辑与配置解耦、热加载）
- ✅ Tauri 桌宠壳（透明窗口、无边框、置顶）
- ✅ Rust + MSVC 环境配置

### 未完成任务（第二批剩余）

- ⏳ 张力态涌现（多维区间判定，如：连接渴望>0.7且安全感<0.4="想靠近但不敢"）

## 2026-11-04 (周三)

### 任务1完成：挫败冷却 + 随机抖动（测试补齐）

开发前核查发现 `window.py` 中 `next_fixed_interval`/`next_random_interval`/`_frustrated`/`custom_time_offset` 已完整实现挫败冷却（连续≥2次未回应→间隔×1.5，不随次数叠加）与随机抖动（固定间隔三角分布偏右、随机间隔对数正态、自定义偏移双向），`config/window.toml` 配置齐备，仅缺单元测试覆盖。

- ✅ 新建 `tests/test_window.py`（22条用例）：TOML加载校验（含未知mode/skew越界报错）、`active_mode`跨午夜窗口环绕、`checkpoint_block_reason`五级优先级链（sleeping>silent_mode>outside_window>hourly_cap>None）、挫败系数边界（1次不触发/2次触发/3次不叠加）、分布形态统计验证（固定间隔均值右偏、随机间隔中位数贴近基准、自定义偏移双向且在幅度范围内）。
- ✅ ALGORITHMS.md 挫败冷却/随机抖动状态 ⏳→✅。
- ✅ 全量回归：`pytest tests -v` **148 passed**，无回归。

### 任务2完成：上下文预算优先级裁决

对齐 TASK.md 新增 7.8 / 验收 32。新建模块：

- ✅ `src/cether/context_budget.py`：`BudgetConfig`（7段字符预算，TOML可加载）、`ContextSegment`（category+text+timestamp）、`allocate_budget()`（按优先级 人格锚点>硬边界>状态质地>关系摘要>心事匣>召回记忆>会话续接摘要 裁决，段位预算互不借用，同级按timestamp近者优先，超预算片段整段裁剪不做字符级截断）、`BudgetResult`/`BudgetDecision` 提供可观测裁决记录。
- ✅ `config/context_budget.toml`：7段预算默认值（人格锚点400/硬边界200/状态质地150/关系摘要300/心事匣250/召回记忆600/会话续接200字符）。
- ✅ `tests/test_context_budget.py`（13条用例）：TOML加载、未知category报错、核心验收场景（高低优先级同时超预算→低优先级被裁高优先级完整保留）、预算不互相借用、同级时间近者优先、整段裁剪不做半句截断、裁决可观测、输出按优先级排序、渲染拼接顺序。
- ✅ ALGORITHMS.md 上下文预算裁切状态 ⏳→✅。
- ✅ 全量回归：`pytest tests -v` **161 passed**，无回归。

### 测试覆盖

- **测试数量**: 126 条
- **通过率**: 100%
- **模块覆盖**: 感知、视觉、检索、记忆、状态、触发、终审、唤醒、闸门、检查点、运行循环

### Git 提交统计

- **首次提交**: Initial commit
- **最新提交**: `1ace0c1` - Add retrieval score multipliers
- **总提交数**: 约 45 个
- **工作目录**: 干净（无未提交文件）

### 下一步计划

按第二批剩余任务继续：
1. 挫败冷却（1小时）
2. 上下文预算裁切（2小时）
3. 张力态涌现（1.5小时）

然后进入第三批（反刍抑制、Jaccard 合并、随机抖动、六十四卦、玻恩规则）。
