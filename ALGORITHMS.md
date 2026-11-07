# CetherYH 推荐算法清单

本文档归类整理推荐的算法实现方案，与三份任务书的统一理解对应。算法分为必须实现、推荐实现、可选实现三档。

> 进度边界（2026-11-07）：`src/cether/memory_retrieval.py` 已把角色隔离 L0 检索接入显式对话轮次：中权重走 BM25，并可注入 embedding、图扩散 provider 做加权 RRF；生命周期、反刍、驱力/效价/区域、抖动与六位编码惩罚进入融合评分；高权重仅由独立 spatial provider 返回，低权重不主动注入。当前 L0 API 只产生 `normal/low`，所以高权重需要上游分类与空间索引写入接通后才会有运行数据；默认没有 embedding/图/spatial provider 时不会伪造这些通道。当前主运行时空间索引为 `src/cether/spatial_index.py`，角色注册表为 `src/cether/roles.py`；工作区未跟踪的平行实现需单独确认归属，不作为本清单的集成实现。同步热路径 P99 基准脚本 `benchmarks/retrieval_baseline.py` 目前使用合成 L0 数据，并非 TASK.md 指定随项目提供的验收语料。

## 一、检索与融合算法（记忆召回）

**目标**：300ms 内精准召回相关记忆。

### 算法原语已完成；运行时集成进行中
| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| BM25 词法检索 | ✅ 接入 | 精确关键词匹配，角色 scope 内检索 | `retrieval.py::BM25`、`memory_retrieval.py::L0RetrievalService` |
| Embedding 向量检索 | ⚠️ 可注入 | cosine 通道；embedding provider 未配置时关闭 | `retrieval.py::VectorRetrieval`、`memory_retrieval.py` |
| 加权 RRF 融合 | ✅ 接入 | 按通道权重融合 BM25/向量/图排名 | `memory_retrieval.py::weighted_rrf_fusion` |
| 图扩散简化版 | ✅ 本地接通 | `LocalCooccurrenceGraphProvider` 从角色 normal L0 构建确定性共现图，再按查询 seed 做跳数扩散 | `graph_retrieval.py`、`retrieval.py::GraphRetrieval`、`memory_retrieval.py` |
| 高权重空间召回 | ✅ 本地接通 | `memory_tiering.py` 依据手动标记、情绪、显著性和关系事件分类；`SpatialMemoryProvider` 按查询词激活并沿固定路线返回 | `memory_tiering.py`、`spatial_retrieval.py`、`memory_retrieval.py::L0RetrievalService` |
| 多路乘子与六位惩罚 | ✅ 接入 | lifecycle、rumination、drive、valence、region、jitter、hexbit | `multipliers.py`、`hexbit.py`、`memory_retrieval.py` |
| 同步热路径基准 | ⚠️ 初版 | 1000–3000 合成 L0 条目，报告 P50/P95/P99；不替代验收 corpus | `benchmarks/retrieval_baseline.py` |

### 推荐实现
| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **六位特征编码/六十四卦惩罚** | ✅ | 6个显式语义维度(valence_positive/high_salience/high_emotion/relation_event/self_initiated/flash_weight)编码为0-63，连续同编码递减惩罚 score×decay_factor^repeat_count(默认0.85) | `hexbit.py::encode_six_bits/apply_hexbit_penalty` |
| **复合乘子偏置** | ✅ | 最终得分=RRF×生命周期×反刍抑制×驱力偏置×效价偏置×区域加成×抖动 | `multipliers.py::apply_multipliers` |

**说明**：
- 六十四卦：6维均为显式语义规则（非随机哈希），编码恒定可复算；维度选取基于项目既有状态/记忆字段（valence、salience、emotion、relation_event、self_initiated、flash_weight），`tests/test_hexbit.py`（13条用例）验证编码正确性与递减惩罚边界，2026-11-05 完成。
- 复合乘子：各项乘子独立计算，检索时依次相乘。`memory_retrieval.py` 的 drive/valence/region 只读取记录中实际存在的字段与注入状态；缺字段使用中性默认值。
- 基准结果（2026-11-07，合成热库 2000 条、100 查询，索引缓存开启）：P50 7.075ms / P95 9.077ms / P99 10.613ms / max 11.522ms，0/100 超过 300ms。缓存按 L0 mtime/size 失效，归档追加会重建索引。该数据仅衡量本地 BM25 热路径，语义 provider 关闭，不能据此视为 TASK.md 11.11/验收 25/38 的最终基准通过。

## 二、记忆生命周期算法（存储与遗忘）

**目标**：决定记住什么、忘掉什么、怎么合并。

### 必须实现
| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|---------------------|
| **惊讶度计算** | ✅ | s=1-Jaccard相似度，计算新记忆初始权重 | `state.py::compute_surprise` |
| **艾宾浩斯/Weibull衰减** | ✅ | w(t)=w0×exp(-Δt/τ)，按天/周级别衰减 | `state.py::ebbinghaus_decay/weibull_decay` |
| **双通道脱水与终审** | ✅ | 副模型结构化提取，主模型工具调用终审 | `finalization.py` |

### 推荐实现
| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **反刍抑制** | ✅ | 短期高频召回节点降权，防过度关注 | `multipliers.py::rumination_multiplier` |
| **Jaccard相似度合并** | ✅ | 相似度≥阈值(默认0.8)触发合并，数字保护+闪光灯节点排除 | `dedup.py::decide_merge/merge_near_duplicates` |

**说明**：
- 惊讶度：新记忆与最近N条记忆的平均Jaccard距离
- Weibull：比指数衰减更灵活，初期快速衰减后趋缓
- 反刍抑制：维护召回计数器，高频召回节点得分降权，`tests/test_multipliers.py` 已覆盖
- 数字保护：正则提取数字，两记忆数字不同→禁止合并；闪光灯节点(flash_weight)优先级高于数字冲突检查，永不参与合并；`tests/test_dedup.py`（15条用例）验证，2026-11-05 完成

## 三、状态与心理演化算法（数字生命的灵魂）

**目标**：情绪平滑过渡、真实感、欲言又止。

### 必须实现
| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|---------------------|
| **一阶惯性滤波** | ✅ | v_t=α×v_{t-1}+(1-α)×v_target，状态平滑 | `state.py::inertial_filter` |
| **四意愿-六维驱力映射** | ✅ | 六维驱动→四意愿投影（社交电量、连接渴望、表达冲动、安全感） | `state.py::project_six_drives_to_four_will` |
| **质地翻译器** | ✅ | 数值→自然语言（疲惫度80→"累得不想说话，但又在等你"） | `state.py::translate_texture` |

### 推荐实现
| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **张力态涌现** | ✅ | 四意愿+关系张力+此刻情绪的区间判定，覆盖4种张力态（想靠近但不敢/累了但舍不得走/想说话但怕说错/期待但失望），不新增状态变量 | `state.py::detect_tension_state` |
| **玻恩规则抽样** | ✅ | 概率振幅P(i)=|c_i|²/Σ|c_j|²计算空闲动作分布（看书/发呆/搭话），阈值过滤+累积概率轮盘抽样 | `idle.py::born_probabilities/sample_action/default_idle_amplitudes` |

**说明**：
- 惯性滤波α推荐0.7（慢变）或0.3（快变），可按状态维度分档
- 四意愿映射表：六维驱动按权重矩阵投影到四意愿，矩阵可配置
- 质地翻译：预设模板库+动态生成（LLM调用）
- 张力态：不硬编码，通过区间规则判定（如：`if desire>0.7 and safety<0.4: return "想靠近但不敢"`）
- 玻恩规则：振幅模由当前状态(social_battery/connection_desire/expression_impulse)加权投影得出，确保语义可解释、可复算；`tests/test_idle.py`（17条用例）验证概率归一化、分布匹配、阈值过滤，2026-11-05 完成

## 四、时序调度与触发算法（主动性控制）

**目标**：管理窗口、检查点节奏、主动搭话频率。

### 必须实现
| 算法 | 状态 | 作用 | 实现位置/预计工作量 |
|------|------|------|---------------------|
| **闸门拦截** | ✅ | 静默时段、今日上限、冷却中→零模型调用 | `gate.py` |
| **多窗口并集与优先级** | ✅ | 重叠触发一次，优先级：睡眠>静默>窗口>检查点 | `checkpoint.py` |

### 推荐实现
| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **随机抖动** | ✅ | 固定间隔三角分布偏右(skew_low/high/mode可配)，随机间隔对数正态(lognormvariate)，自定义偏移±120-300s双向 | `window.py::next_fixed_interval/next_random_interval/custom_time_offset` |
| **挫败冷却** | ✅ | 连续两次未回应→下次间隔×frustration_factor(1.5)，不随次数继续叠加；计数重置由调用方负责 | `window.py::_frustrated` |

| **上下文预算裁切** | ✅ | 单轮注入预算按优先级（人格锚点>硬边界>状态质地>关系摘要>心事匣>召回记忆>会话续接摘要）硬裁，段位预算互不借用，同级按时间近者优先 | `context_budget.py::allocate_budget` |

**说明**：
- 随机抖动/挫败冷却：代码已在 `window.py` 实现并有 `config/window.toml` 配置支持，2026-11-04 补齐 `tests/test_window.py`（22条用例）验证，含TOML加载校验、`active_mode`跨午夜窗口、`checkpoint_block_reason`优先级链、挫败系数触发边界、分布形态采样验证。
- 上下文裁切：字符预算按优先级分段（对齐 TASK.md 新增 7.8），每段独立配额不互相借用，超预算片段整段裁剪而非字符级截断（避免半句话注入），裁决结果通过 `BudgetDecision` 列表可观测；`tests/test_context_budget.py`（13条用例）验证高低优先级同时超预算场景（对应 TASK.md 新增验收 32）。

## 五、感知与底层对比算法

### 必须实现（已完成）
| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **图像哈希比对** | ✅ | 画面无变化→零模型调用，省钱 | `perception.py::average_hash` |

### 可选实现
| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **空间索引巡游** | ✅ | 固定房间+容量限制，满员开新房，桩位只增不回收，固定路线巡游(房间升序→桩位升序) | `spatial_index.py::SpatialIndex` |

**说明**：
- 哈希比对：已用Hamming距离，阈值5
- 空间索引：房间容量统一(默认50)保证巡游顺序可预测；桩位被移除后标记unoccupied但编号永不复用，保证坐标对"记忆星空"可视化稳定；`tests/test_spatial_index.py`（14条用例）验证容量溢出开新房、桩位不复用、巡游顺序确定性，2026-11-05 完成

## 算法实现优先级总览

### 第一批（核心闭环必需，3-4小时）
1. 惊讶度计算（30分钟）
2. 一阶惯性滤波（1小时）
3. 四意愿映射（1小时）
4. 质地翻译器（30分钟）
5. 艾宾浩斯衰减（1小时）

### 第二批（提升体验，4-5小时）
6. 复合乘子偏置（2小时）
7. 挫败冷却（1小时）
8. 上下文预算裁切（2小时）
9. 张力态涌现（1.5小时）

### 第三批（锦上添花，7-8小时）✅ 已完成（2026-11-05）
10. 反刍抑制（1.5小时）✅
11. Jaccard相似度合并（1.5小时）✅
12. 随机抖动（30分钟）✅（第二批随挫败冷却一并完成）
13. 六位特征编码/六十四卦（3小时）✅
14. 玻恩规则抽样（2小时）✅

### 第四批（可选增强，4小时+）✅ 已完成（2026-11-05）
15. 空间索引巡游（4小时）✅

## 当前进度与下一步

**算法原语状态**：第一批5项、第二批4项、第三批5项、第四批1项均有实现；检索原语包括 BM25、向量/图适配器、加权 RRF 和乘子。算法测试数以当前 pytest 结果为准，不沿用历史快照 245。

**运行时接通状态（2026-11-07）**：
- 对话 L0 BM25 检索已接入角色 scope、TOML 参数热加载和延迟观测；向量/图通道为可注入接口，未配置 provider 时明确关闭。
- 本地决策/表达 provider 已接入 desktop 默认 RuntimeServices；表达生成仍由独立对话 provider 负责。
- 浅睡可对近期 L0 产生去重候选 ID 并调用角色本地索引回调，不改写 append-only L0。
- 深睡反思与梦境产物带 source L0 IDs；反思按配置阈值从文本证据抽取摘要并校准状态基线，检索偏置在索引刷新 stage 更新。
- 同步检索基准目前仅为合成 L0/BM25 基线；缺少项目验收 corpus，语义 provider 关闭，不能视为最终 P99 验收。

**阶段 2桌面整合状态（2026-11-07）**：Python desktop bridge 已暴露状态快照、记忆时间轴、上下文动作、角色切换进度与 wake injection；Tauri 已转发 `ui_action`/`memory_timeline`，透明陪伴壳已接入聊天、角色管理、状态和记忆面板。`tests/test_desktop_ui.py` 覆盖核心动作反馈与角色本地数据边界。

**阶段 3运行时与生命周期接线（2026-11-07）**：默认 desktop runtime 已接入 `Perceiver`、首次感知确认、角色级 allow/deny 配置、已见记录、独立截屏/运行事件暂停；`MemoryLifecycleService` 通过 `memory/lifecycle.json` 实现删除/降权/冷库/捞回/一次性注入而不改写 L0，`DiaryService` 以隐藏侧车保持 L1 日记不可变。Tauri 新增通用 `runtime_action`，桌面入口覆盖日记/已见、角色封存恢复双确认删除、角色包导入导出、陪伴/工作模式和工具事件提示；角色包包含角色私有 memory/persona/state，并排除 global channels。`tests/test_stage3_integration.py` 验证首次确认、双暂停、生命周期 append-only、一次性注入和角色包唤醒。

**当前验证边界**：本轮全量 Python 回归为 352 passed，Rust `cargo check`、嵌入式前端 JavaScript 语法检查和 `git diff --check` 通过。正式项目验收 corpus、星图真实渲染、后台事件流持续订阅、配置写入面板、preset 升级保护和 TASK.md 全量端到端映射仍需后续验收；这些未被本轮的接口接通替代。阶段1关键运行时闭环（检索融合、决策表达、睡眠调度/打断、巩固反思）已接通并通过回归。
