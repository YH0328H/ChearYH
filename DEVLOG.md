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

### 任务3完成：张力态涌现（第二批收官）

对齐 TASK.md 60（至少覆盖4种张力态）、279（由此刻情绪+关系张力投影得出，不新增状态变量）、227（替换条款：提交两个指定张力态的全程可复算数值推演）。

- ✅ `src/cether/state.py` 新增：`TensionStateConfig`（8个可配置区间阈值，frozen dataclass）、`TensionStateHit`（命中记录，含name/description/evidence可观测字段）、`detect_tension_state(will, relation_tension, momentary_valence, config)` 判定四种张力态：
  - 想靠近但不敢：connection_desire≥0.7 且 security≤0.4
  - 累了但舍不得走：social_battery≤0.3 且 connection_desire≥0.6
  - 想说话但怕说错：expression_impulse≥0.6 且 security≤0.4
  - 期待但失望：expression_impulse≥0.6 且 momentary_valence≤-0.2
  - `relation_tension` 当前仅记入 evidence 供可观测性与未来检索偏置使用，不参与阈值判定（避免在真实关系张力分布未知前编造不可验证的额外阈值）。
- ✅ `tests/test_state.py` 新增 `TensionStateTests`（9条用例），其中两条是 TASK.md 227 要求的全程可复算推演：`test_full_derivation_close_but_afraid_from_six_drives` 与 `test_full_derivation_tired_but_reluctant_from_six_drives`，从六维驱力初值+目标值经惯性滤波（α=0.7）手工复算到四意愿终值，再喂入 `detect_tension_state` 验证区间判定命中，每一步都有显式算式注释可人工复核。
- ✅ ALGORITHMS.md 张力态涌现状态 ⏳→✅。
- ✅ 全量回归：`pytest tests -v` **170 passed**，无回归。

### 第二批收官

挫败冷却、随机抖动、上下文预算裁切、张力态涌现四项全部完成，第二批任务结束。下一步进入第三批：反刍抑制、Jaccard相似度合并、六十四卦编码、玻恩规则抽样。

### 测试覆盖

- **测试数量**: 126 条
- **通过率**: 100%
- **模块覆盖**: 感知、视觉、检索、记忆、状态、触发、终审、唤醒、闸门、检查点、运行循环

### Git 提交统计

- **首次提交**: Initial commit
- **最新提交**: `1ace0c1` - Add retrieval score multipliers
- **总提交数**: 约 45 个
- **工作目录**: 干净（无未提交文件）

## 2026-11-05 (周四)

**工作时间**: 约 2 小时（12:00-13:20，接续前日第二批收尾）

### 第三批：锦上添花算法（全部完成）

摸底发现反刍抑制（`multipliers.py::rumination_multiplier`）与随机抖动（`window.py`）此前已随其他任务一并实现，本次实际新写三项：

#### 1. 六位特征编码/六十四卦惩罚
- ✅ 新建 `src/cether/hexbit.py`：`DIMENSION_NAMES` 定义6个显式语义维度（valence_positive/high_salience/high_emotion/relation_event/self_initiated/flash_weight，全部取自项目既有状态/记忆字段，不新造维度）；`encode_six_bits` 按6维编码为0-63整数，禁止随机哈希，同输入恒定输出；`apply_hexbit_penalty` 连续相同编码递减惩罚 `score × decay_factor^repeat_count`（默认0.85），编码切换即重置计数。
- ✅ 新建 `tests/test_hexbit.py`（13条用例）：编码边界、自定义判定函数覆盖、连续惩罚递减、顺序保持。

#### 2. Jaccard相似度合并（数字保护+闪光灯排除）
- ✅ 新建 `src/cether/dedup.py`：`jaccard_similarity`/`extract_numbers`/`numbers_conflict`（数字集合不同即禁止合并，对齐 TASK.md 48）；`decide_merge` 按优先级判定：闪光灯节点优先于数字冲突检查，永不合并→数字冲突禁止合并→低于相似度阈值(默认0.8)不合并→否则合并；`merge_near_duplicates` 贪心两两比较去重，返回保留列表+全部判定记录（可观测）。
- ✅ 新建 `tests/test_dedup.py`（15条用例）：数字保护阻止高相似合并、闪光灯优先级高于数字检查、链式合并、空输入边界。

#### 3. 玻恩规则抽样（空闲动作分布）
- ✅ 新建 `src/cether/idle.py`：`born_probabilities` 按 P(i)=|c_i|²/Σ|c_j|² 将振幅列表转概率分布，全零振幅兜底均分；`sample_action` 过滤低于阈值动作后累积概率轮盘抽样；`default_idle_amplitudes(social_battery, connection_desire, expression_impulse)` 从当前状态投影出"看书/发呆/搭话"三个默认动作振幅，投影权重语义可解释、可复算。
- ✅ 新建 `tests/test_idle.py`（17条用例）：概率归一化、2000次采样验证分布匹配（P(a)≈0.9878）、阈值过滤、状态投影方向正确性。

### 第三批收官

反刍抑制、Jaccard相似度合并、随机抖动、六位特征编码、玻恩规则抽样全部完成，第三批任务结束。ALGORITHMS.md 一至四类算法清单除「空间索引巡游」（第四批，低优先级）外全部标记 ✅，同时修正了此前滞后未更新的第一批状态标记（惊讶度/惯性滤波/四意愿映射/质地翻译/艾宾浩斯衰减，代码早已完成但文档仍显示⏳）。

### 测试覆盖

- **测试数量**: 215 条（新增 45 条：hexbit 13 + dedup 15 + idle 17）
- **通过率**: 100%，`pytest tests -v` 全量回归 215 passed，无回归
- **新增模块**: `hexbit.py`、`dedup.py`、`idle.py`

### 第四批：空间索引巡游（全部完成）

对齐 TASK.md 39（固定房间、容量限制、满员开新房、桩位只增不回收、固定路线巡游）。

- ✅ 新建 `src/cether/spatial_index.py`：`SpatialIndexConfig`（room_capacity 默认50，统一容量保证巡游顺序可预测）；`Slot`（room/slot_id/memory_id/occupied，frozen）；`SpatialIndex.place` 填满当前房间后自动开新房，`remove` 只把槛位标记 `occupied=False` 而不回收编号（下次 place 永不复用该编号），`patrol_route` 按房间升序→桩位升序返回固定路线（含已清空槛位，供上层按 occupied 过滤）。
- ✅ 新建 `tests/test_spatial_index.py`（14条用例）：顺序填房、满员开新房、多房连续溢出、移除后编号不复用（验证下一次 place 跳到新房而非回填空槛位）、巡游路线包含已清空槛位且顺序确定可复算、空索引边界。

### 全量算法清单收官

一至五类算法清单（检索融合/记忆生命周期/状态演化/时序调度/感知底层）**全部完成**，无剩余 ⏳ 项。

### 测试覆盖

- **测试数量**: 245 条（新增 14 条：spatial_index）
- **通过率**: 100%，`pytest tests -v` 全量回归 245 passed，无回归

### 第九、十章：角色运行时与交互契约（后端首轮完成）

- ✅ 新建 `src/cether/roles.py`：全局单活角色注册表（最多5个）、角色独立工作区与 scope 校验、切换生命周期 hooks/进度事件、失败回滚及回滚失败只读错误态、唤醒注入首次对话后消费、归档/恢复/双确认删除、角色卡包导入导出。
- ✅ 新建 `src/cether/ui_contract.py`：稳定的导航/右键/角色区动作集合、角色卡与状态视图、记忆时间线和星图投影、查看/暂停/记住/重想/深化/角色切换/归档恢复等动作及可见反馈。
- ✅ 新增 `tests/test_roles.py`、`tests/test_ui_contract.py`；全量回归 `pytest tests -q --tb=short`：268 passed。
- ⚠️ 本轮交付的是 Python 后端运行时管理与 UI 数据/动作契约，不含 Tauri 视觉组件；角色包导入冲突的替换/重命名交互、多文件原子持久化接线、崩溃恢复协调，以及各实际业务模块接入 scope/hooks，仍需在整合阶段完成。

### 后续

先审查并补全角色包导入冲突与持久化/崩溃恢复边界，再将 roles/UI 契约接入实际运行时；之后串联 `runner.py` 主循环，最后实现 Tauri 视觉层并进行端到端验证。
