# CetherYH 开发日志

## 2026-11-08 V3.0 五行架构设计与文档整合

**工作时间**: 约 6 小时 (14:00-20:00)

### 核心成果

#### 1. 五行认知架构设计 ★
- ✅ 创建 `docs/WUXING_PHILOSOPHY.md` — 五行认知哲学核心文档
- ✅ 五行模块映射：木(生长)、火(表达)、土(稳定)、金(掌控)、水(联结)
- ✅ 阴阳平衡 → 李雅普诺夫临界态理论(λ ≈ 0)
- ✅ 八卦情绪原型映射 PAD 空间
- ✅ 六十四卦 Hexbit 记忆编码完整解释
- ✅ 天地人三才驱力架构设计

#### 2. 算法文档全面补充
- ✅ ALGORITHMS.md 新增第七章：五行平衡与李雅普诺夫稳定性
  - 五行驱力系统算法(相生相克)
  - 阴阳平衡临界态维持
  - 李雅普诺夫谱计算(Clark 2026 方法)
  - Kaplan-Yorke 吸引子维度
  - 易经六十四卦与李雅普诺夫关联
- ✅ ALGORITHMS.md 新增第八章：系统级优化-临界态认知架构
  - 全系统李雅普诺夫监控
  - 临界态自适应控制
  - 性能指标对比

#### 3. 理论融合研究
- ✅ 阅读分析 PSI 认知架构(Joscha Bach 2009)
  - 生理性驱力: Water/Energy/Integrity
  - 能力驱力: Certainty/Competence/Affiliation
  - 动机调节机制
- ✅ 阅读分析 The Synthetic Mind(Josh Ferrer 2026)
  - 赫尔驱力理论现代化
  - 模拟人生自主系统案例
  - 内在好奇心预测误差驱动
- ✅ 阅读分析李雅普诺夫谱论文(David G. Clark 2026)
  - 随机神经网络李雅普诺夫指数分布
  - 吸引子维度与熵率
  - 切空间动力学与腔方法

#### 4. 文档体系整合 ★
- ✅ 删除冗余文档:
  - `CetherYH_2.1_DESIGN.md` (旧版本)
  - `WORK_PLAN.md` (冗余计划)
  - `ACCEPTANCE_MAPPING.md` (冗余验收)
  - `PROJECT_GUIDE.md` (冗余指南)
  - `PROJECT_STATUS.md` (冗余状态)
  - `docs/INDEX.md` (冗余索引)
- ✅ 保留核心文档:
  - 设计: V3.0_DESIGN / ARCHITECTURE / ALGORITHMS / UI_DESIGN / WUXING_PHILOSOPHY
  - 日志: DEVLOG / README
  - 归档: docs/legacy/TASK.md
- ✅ 更新 README.md 为统一入口
  - 项目名称改为"五行认知架构桌面陪伴应用"
  - 核心理念改为五行平衡
  - 项目结构更新五行模块命名
  - 致谢章节补充理论基础

#### 5. 架构文档完善
- ✅ ARCHITECTURE.md 新增第七章：五行平衡架构
  - 五行模块映射表
  - 阴阳平衡与临界态维持算法
  - 五行相生相克配置
  - 八卦情绪系统映射
  - 易经六十四卦记忆编码

### 核心创新点

#### 理论融合
**易经五行 × 李雅普诺夫动力学 × PSI 认知架构**

1. **五行相生相克 = 驱力动态平衡**
   - 木生火: 好奇心驱动表达
   - 水克火: 深度共情淡化表达
   - 系数可配置，保持阴阳调和

2. **阴阳平衡 = 临界态 (λ ≈ 0)**
   - 阳盛(λ > 0.1) → 混沌，行为发散
   - 阴盛(λ < -0.1) → 僵化，缺乏创造性
   - 临界态 → Edge of Chaos，最优认知状态

3. **六十四卦 = Hexbit 编码 = 记忆李雅普诺夫**
   - 6 个二值维度 = 6 个爻
   - 递减惩罚 = "物极必反"
   - 保持记忆多样性 = 保持临界态

4. **八卦 = PAD 情绪原型**
   - 乾(自信)、坤(平静)、震(兴奋)、巽(温柔)
   - 坎(忧虑)、离(热情)、艮(沉稳)、兑(愉悦)

### 模块命名体系

核心模块重命名为五行体系:
- `drives.py` → `wuxing_core.py` (五行核心)
- `context_orchestrator.py` → `qiankun_orchestrator.py` (乾坤编排)
- `emotion.py` → `bagua_emotion.py` (八卦情绪)
- `memory_retrieval.py` → `yijing_memory.py` (易经记忆)
- `decision.py` → `taiji_decision.py` (太极决策)

### 待实施工作

**Week 1 — 核心驱力系统**:
- [ ] 实现 `src/cether/wuxing_core.py`
  - 三层驱力架构(生理/心理/涌现)
  - 五行相生相克算法
  - 李雅普诺夫稳定性追踪
- [ ] 集成到 `state.py`
- [ ] 编写单元测试 `tests/test_wuxing.py`

**Week 2 — 李雅普诺夫监控**:
- [ ] 实现雅可比矩阵计算
- [ ] 实现李雅普诺夫谱计算
- [ ] 实现稳定性自适应调整
- [ ] 前端可视化李雅普诺夫谱

**Week 3 — 文档与集成**:
- [ ] 完善五行配置文件
- [ ] 全量测试
- [ ] 性能优化

### 参考资料

- [易经](https://zh.wikipedia.org/wiki/易经) — 周文王、孔子
- [黄帝内经](https://zh.wikipedia.org/wiki/黄帝内经) — 轩辕黄帝
- [Lyapunov spectrum of random neural networks](https://arxiv.org/abs/2610.12426) — David G. Clark, 2026
- [Principles of Synthetic Intelligence (PSI)](http://www.cognitive-ai.com/) — Joscha Bach, 2009
- [The Synthetic Mind](https://github.com/joshferrer1/the-synthetic-library) — Josh Ferrer, 2026

---

## 2026-11-08 交付补全工作（未运行测试/验收）
- 桌面生命周期：接入 RuntimePipeline 角色 worker、周期快照线程、关闭/切换前快照和窗口检查点调度；窗口节奏及快照节奏从配置读取，调度事件按阻塞原因变化限频。
- 会话输入：为 provider 请求组装分段上下文预算，记录预算裁决；单次记忆注入只在对话成功持久化后消费，并受角色会话锁保护。
- 记忆与交互：冷库按 UTC 月分片落盘并索引，支持恢复与分页；主动表达事件接入 UI popup/silent 呈现；首次引导六模块逐步说明；工作模式产物独立存放在角色 `work-files/` 并在 UI 展示。
- 本地降级：首次引导选择 `local_fallback` 后启动使用 LocalRuleProvider；对话配置保存仍可由用户显式启用远程 Provider。
- 交付入口：补 README 安装/运行/provider 配置和 PowerShell 一键启动脚本；声明 Pillow/mss 和 PyInstaller 依赖；新增 onedir spec 与 `cether.__main__` 冻结入口；Tauri 通过 runtime `resource_dir` 找随包 runner 并传递资源根目录；配置窗口改为可调整桌面工作区。
- 尚未关闭：主动表达自动候选主题的生产者；工作模式摘要记忆隔离；Tauri 原生文件选择器；跨角色共享工具状态知情开关/真实外部工具执行；代码签名与发布元数据；原生打包和正式安装包运行链路未经验证。严格按用户要求，本轮不运行测试、验收或构建，不提交。

## 2026-11-08 Round 4
- 增加首次启动六模块向导与可选本地降级记录；本地规则 provider 可在未配置远程 provider 时工作。`onboarding.local_fallback` 由 corpus 驱动桌面运行时测试与 Playwright 首屏交互验证。
- 增加主动表达弹窗/静默呈现偏好，写入 app data 并在 bootstrap/reload 恢复；`expression.presentation.preference` 覆盖静默设置与无效值验证。表达事件消费者尚未完成集成，TASK #62 保持 PARTIAL。
- TASK #58、#62 在 `ACCEPTANCE_MAPPING.md` 标为 PARTIAL，并记录交互式模块内容与主动表达调度集成的剩余验收。

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

## 2026-11-08 (周日)

### Round 4：TASK #33 快速接话取消路径（部分闭合）

- 新增有序规则接话调度器及可撤销句柄；不匹配时静默降级，问号仅匹配句末问号。
- 对话请求组装时后台派发接话，正式 provider 开始前撤销 TTS 入队许可；finally 重复撤销，异常路径同样关闭许可。
- 接话不写入正式 conversation history、L0 或表达完成反馈。阻塞 provider 的并发回归覆盖取消时序和持久化边界；单元测试覆盖规则顺序、句柄取消与无匹配。
- 尚未连接真实桌面 TTS 队列，适配器必须在 enqueue 前检查句柄；尚无本地小向量候选。按 TASK.md 语义保持 #33 PARTIAL。
- 定向验证：`pytest tests/test_backchannel.py tests/test_conversation.py -q --tb=short -x`，23 passed。

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

### 主循环：运行时闭环编排

- ✅ 扩展 `src/cether/runner.py`：新增 `RuntimePipeline`、`RuntimeSteps`、`RuntimeContext`、`RuntimeEvent` 与 `RuntimeReport`。前台阶段按“感知→L0→触发判定→条件式L1→状态→决策→表达→结果回流”顺序串联；未触发时跳过叙事生成。
- ✅ 每个阶段前检查角色 scope；拒绝并发 tick；停止请求在当前轮次结束后生效；后台睡眠巩固、反思校准、检索偏置更新在前台完成后执行，错误产生可观测事件并默认不阻断轮次。
- ✅ 保留既有 `build_perceiver` 与 `run_loop` 接口兼容。
- ✅ 扩展 `tests/test_runner.py` 覆盖阶段顺序、L1跳过、scope复核/阻断、后台错误隔离、停止与并发约束；专项测试 15 passed，全量 `pytest tests -q --tb=short`：276 passed。

### 后续

### 运行时接线、角色生命周期与反馈闭环（路线图 1–3）

- ✅ 新建 `src/cether/runtime_services.py`：将角色工作区内的 L0/L1 归档、五类显式 L1 触发判定、状态原子落盘和表达结果回流接入 `RuntimePipeline`；决策、表达、叙事生成仍通过显式注入 provider，避免用占位逻辑伪造认知结果。
- ✅ 表达反馈按完整/短回应/软拒绝分别扣减、半档扣减、微量恢复社交电量，并持久化情绪残余；睡眠模式在感知前读取，light/deep 均跳过感知和前台状态演化，浅睡仅调用巩固，深睡另调用反思校准和检索索引更新。
- ✅ 深睡反思可持久化自我基线、反思 L1 与检索偏置；检索偏置从角色工作区恢复。具体巩固、梦境/反思生成和索引构建算法由注入 provider 承担，尚无项目内置实现。
- ✅ `RoleRegistry` 增加按角色注册任务取消回调；切换等待同步 tick 收尾，取消超时则回滚。角色状态、心事匣、候选池与唤醒注入组成带 SHA-256 校验的快照包，通过原子 latest 指针发布；启动时验证并恢复各角色最近快照。
- ✅ `RuntimePipeline` 增加并发互斥、取消等待和睡眠阶段分流；当时的实现曾让恢复醒来后的首轮只完成唤醒，不执行感知闭环（行为于 2026-11-06 修正，见下文）。重启恢复的检索偏置传入决策 provider。新增运行时服务、取消等待、恢复/校验测试。
- ✅ 全量测试：`pytest tests -q --tb=short` **292 passed**。

后续：接入真实决策与表达 provider、具体睡眠巩固/反思算法和检索服务；然后推进 Tauri IPC、视觉面板与端到端验证。

### 运行时验收边界更新（2026-11-06）

- 调整 `RuntimePipeline`：睡眠结束后的首个 awake tick 继续正常处理；无变化观测仍更新角色状态，但跳过 L1 触发与决策/表达/结果反馈；可注入门控在 L0 归档前执行，阻断时无后续模型调用。
- `RuntimeServices.begin_user_turn()` / `decide_user_turn(...)` 提供显式用户轮次入口：仅该入口获取并消费一次待注入唤醒上下文，并将其传给决策 provider；后台观测 tick 不消费该上下文。
- 新增 runner 与 runtime service 验收覆盖。本文记录代码状态，不代表本条目后的测试已经运行；最终全量测试结果待本次收口追加。
- 工作区发现未跟踪平行模块 `src/cether/role.py`、`src/cether/spatial.py` 及相关测试；保留原样。已提交运行时继续使用 `roles.py`、`spatial_index.py`。

## 2026-11-07（周五）

### M1：最小可运行对话纵切完成

- ✅ 新增 `src/cether/providers.py`：本地规则 provider 与 OpenAI-compatible HTTP adapter；配置支持 TOML、超时/温度边界校验，密钥只从环境变量读取。
- ✅ 新增 `src/cether/conversation.py`：显式用户轮次、单活锁、角色 scope 校验、最近 L0 上下文、会话 JSONL 与 L0 双写、表达反馈写回状态。
- ✅ 新增 `src/cether/desktop.py`：Python JSON-lines 桥接协议，支持启动、创建/切换角色、发送消息、关闭；每个角色独立运行时与历史空间。
- ✅ 扩展 `src-tauri/src/lib.rs`：Rust Tauri command 转发到长驻 Python runtime，统一请求 ID、错误返回与子进程生命周期。
- ✅ 重建 `dist/index.html`：原生响应式聊天界面，角色选择/创建、历史显示、输入发送与错误状态。
- ✅ 唤醒语义修正：provider 成功且 scope 仍有效后才消费一次性唤醒；provider 错误可重试，不丢待唤醒上下文。
- ✅ 测试与验证：M1 专项 23 passed；Python 全量 **305 passed**；`cargo check --locked` 通过且无编译警告；内嵌 JavaScript 语法检查通过；JSON-lines 启动、创建、发送、角色切换 E2E 通过。

### M1 后续边界

事件流、状态/记忆可视化面板、真实决策/表达服务接入、检索多路融合与性能基准、睡眠/反思具体算法和桌面端完整打包仍属于后续工作；当前工作区包含未提交改动，保留既有用户文件与平行实现。

### 阶段 1 首个切片：角色隔离 L0 词法召回（2026-11-07）

- ✅ 新增 `src/cether/memory_retrieval.py`：基于中文字符/二元组及英文词元构建 BM25，严格校验当前角色 scope，仅返回正分命中；低权重记录不主动注入，归档错误返回空结果（scope 错误继续抛出）。
- ✅ 在 `src/cether/conversation.py` 将显式用户输入作为检索 query，召回替代“最近八条”机械上下文；向量/图/RRF/乘子暂未接入。
- ✅ 新增 `config/retrieval.toml` 默认 top-k、BM25 参数及 300ms 预算；`RetrievalConfigWatcher` 支持有效配置变更热加载，解析错误保留最后有效配置；`last_observation` 暴露耗时、超预算、通道、数量和错误。
- ✅ 新增 `tests/test_memory_retrieval.py` 覆盖正命中、无命中、低权重过滤、scope 失败、存储故障、预算观测、中文分词和配置热加载；调整对话集成断言验证检索内容。
- ✅ 验证：专项 34 passed；全量 `pytest tests -q --tb=short -x`：**313 passed**。
- ✅ 阶段 1 检索融合切片（续）：`memory_retrieval.py` 增加加权 RRF、可注入 embedding/图/spatial provider、向量按文档文本缓存、乘子与六位编码排序；低权重不注入，高权重只接受 spatial provider 候选。TOML 热加载覆盖通道权重、跳数、权重带、生命周期/反刍/驱力映射、区域、jitter、hexbit 与延迟预算。L0 仍仅有 normal/low 标注，故高权重需后续上游分类和空间索引接通；语义 provider 未配置时明确关闭。
- ✅ 新增 `benchmarks/retrieval_baseline.py`：合成 1000–3000 条热库与查询的本机同步路径 P50/P95/P99 输出。1000 条/50 查询：17.325/24.293/27.071ms，max 27.297ms，0/50 超 300ms；该合成数据不等于任务书验收语料，外部 embedding 延迟也不在此测量范围。
- ✅ 检索融合专项测试：38 passed（BM25、scope、低权重、配置热加载、加权 RRF、向量/图注入、空间路由、延迟与重复召回评分）。
- ⏭ 当时下一步：继续核查/优化融合实现并跑 2000 条及全量回归；接通真实决策/表达 provider、睡眠分层/巩固与反思算法及 runtime。以下记录后续进展。

### 阶段 1 运行时接通续（2026-11-07）

- ✅ 新增 `src/cether/cognition.py` 与 `config/cognition.toml`：桌面默认使用本地确定性决策/表达 provider，结合闸门、睡眠、社交电量和表达冲动给出决定；未替换独立对话模型 provider。
- ✅ 新增 `src/cether/sleep.py` 与 `config/sleep.toml`：浅睡生成相似 L0 合并候选并调用索引回调，不改写 append-only L0；深睡按证据阈值输出抽取式反思、状态基线校准和检索偏置，并仅在有足够低权重来源时生成带 source L0 IDs 的梦境 L1。
- ✅ `desktop.py` 默认 RuntimeServices 已装配以上 provider；反思 L1 由 RuntimeServices 单点写入，来源为空时跳过，避免重复/不可追溯条目；睡眠索引刷新不重复运行巩固。
- ✅ 验证：聚焦 cognition/sleep/desktop/runtime 32 passed；全量 `pytest tests benchmarks/test_retrieval_baseline.py -q --tb=short -x`：**328 passed**（10.70s）。
- ✅ 检索索引缓存按 L0 文件 mtime/size 失效：热查询复用解析记录、词元与 BM25 索引，追加后重建；新增追加失效回归测试。优化前观察到 1/100 查询超过 300ms，定位为每轮重建索引。
- ✅ 缓存后检索基准 2000 条/100 查询：P50 7.075ms / P95 9.077ms / P99 10.613ms / max 11.522ms，0/100 超 300ms；仍是合成 corpus，语义 provider 关闭，不作为验收结论。
- ✅ 全量 `pytest tests benchmarks/test_retrieval_baseline.py -q --tb=short -x`：**329 passed**（11.42s）。
- ✅ 角色本地 `SpatialMemoryProvider` 已由 desktop 默认装配：高权重记录同步到持久化固定房间/桩位索引，查询只用词元重叠作为激活条件，再按固定巡游路线返回；scope 切换会拒绝旧 provider。
- ✅ embedding 适配增加批量请求与维度/index 校验；桌面从 `config/embedding.toml` 读取 endpoint，只有 `CETHER_EMBED_API_KEY` 存在时启用，当前环境未配置 key，因此没有伪造语义通道。
- ✅ `LocalCooccurrenceGraphProvider` 已默认装配：从角色 normal L0 记录构建确定性共现图，图扩散按 query seed 返回 role-local 关联记忆，并在角色切换时执行 scope 校验。
- ✅ 新增 `memory_tiering.py`：依据手动标记、flash 标记、情绪强度、显著性和关系事件进行确定性高/中/低分类；L0 仍保持 `normal`/`low` 粗粒度 append-only 格式，高层分类写入 `tier_metadata`，检索按该元数据进入空间高权重路径。
- ✅ 睡眠交互打断已接入：用户 turn 会标记当前轻/深睡眠为 interrupted，下一次 pipeline tick 恢复 awake 且跳过睡眠后台任务；覆盖 light/deep 路由、反思/索引不重复执行和全量回归。
- ✅ 新增 `sleep_schedule.py` 和 `[sleep_schedule]` TOML 配置：支持启用开关、跨午夜 light/deep 时间窗、idle 阈值；desktop 默认装配，关闭时保持 awake，配置与边界测试通过。
- ✅ 新增 `test_phase1_e2e.py`：验证高权重感知事件写入 tier metadata 后进入 spatial 召回并注入对话上下文；验证 deep sleep 生成带 L0 来源的 reflection/dream、更新 baseline 与 retrieval bias。全量测试达到 344 项。
- ✅ provider/空间专项回归 34 passed。全量回归待本轮最后执行。
- ✅ 阶段 1运行时闭环完成：图 provider、高权重 tier metadata、睡眠调度/交互打断与阶段 E2E 已接通；全量回归达到 344 项。正式验收 corpus 与 TASK.md 全量映射仍保留为后续验收工作。

### 阶段 2：桌面端整合（2026-11-07）

- ✅ `src/cether/desktop.py` 扩展为稳定桌面动作面：状态快照、角色卡、自然语言状态、记忆时间轴、看一眼、暂停感知、手动记忆、角色切换进度与唤醒待注入状态均通过 JSON-lines bridge 暴露。
- ✅ `src-tauri/src/lib.rs` 增加 `ui_action` 与 `memory_timeline` command，继续复用统一请求 ID、错误返回和 Python runtime 生命周期。
- ✅ `dist/index.html` 重建为透明陪伴壳：拖拽标题栏、角色切换/创建、陪伴动画状态、聊天气泡、导航抽屉、记忆面板、状态面板、工作/配置入口、内联错误反馈和快捷动作。
- ✅ 手动记忆沿用 L0 append-only 约束，并写入可追溯的 `memory_tier=high` 元数据；角色切换继续由 `RoleRegistry` 的单活事务和 wake injection 管理。
- ✅ 新增 `tests/test_desktop_ui.py` 覆盖 bootstrap 状态、动作反馈、角色本地时间轴和切换进度；桌面桥接专项与全量回归均通过。
- ⚠️ 当前阶段交付的是可运行桌面整合壳；星图渲染、冷库完整交互、后台事件流和配置写入面板仍需后续迭代。

### 阶段 3：感知、记忆生命周期与角色管理（2026-11-07）

- ✅ Desktop 默认接入 `Perceiver`：首次感知说明与确认、角色级 allow/deny 应用过滤、画面变化/已见记录、截屏感知与运行事件两套独立暂停；截屏或视觉依赖故障降级为可观测事件，不阻断运行时。
- ✅ 新增 `memory_lifecycle.py` 与 `diary.py`：删除/降权/移入冷库/boost/移热/一次性注入均通过角色私有 sidecar 实现，保持 `memory/l0.jsonl` append-only；L1 日记删除只隐藏视图，原始日记不可变。
- ✅ 角色包升级为 version 2，包含角色私有 memory/persona/state 与导入唤醒快照，排除 global channels；Desktop 暴露角色封存、恢复、双确认删除、导入导出、陪伴/工作模式、工具事件提示和 onboarding 完成入口。
- ✅ Tauri 增加通用 `runtime_action` command，前端增加首次感知确认、已见记录、日记、模式切换和角色管理入口；新增 `tests/test_stage3_integration.py` 覆盖感知确认/双暂停、生命周期 append-only/一次性注入、角色包 memory 与 wake。
- ✅ 验证：全量 `pytest tests benchmarks/test_retrieval_baseline.py -q --tb=short -x`：**352 passed**；`compileall`、`cargo check --manifest-path src-tauri\\Cargo.toml`、嵌入式 JavaScript `node --check`、`git diff --check` 均通过。
- ⚠️ 正式验收 corpus、星图真实渲染、后台事件持续订阅、配置写入面板、preset 升级保护及 TASK.md 全量端到端映射仍需后续验收；本阶段提交的是已验证的运行时/桥接接线，不将接口接通等同于完整产品验收。

### 正式验收推进（2026-11-07，第 16 轮）

- ✅ 新增 `role.package.complete` corpus 场景；角色包测试实际检查 persona、boundaries、appearance、expression、window、checkpoint 成员、导入后内容往返、wake 标记及 chat/embedding 全局配置排除。
- ⚠️ TASK #57 仍为 PARTIAL：角色私有记忆与状态的完整导入恢复尚缺端到端断言。全量映射当前 3 PASS、52 PARTIAL、8 GAP；23 条 corpus 场景中仅部分进入可执行断言。
- ✅ 验证：`.venv\\Scripts\\python.exe -m pytest tests -v --tb=short -x`：**373 passed in 47.19s**；`git diff --check` 通过（仅换行符提示）。

### 正式验收推进（2026-11-07，第 17 轮）

- ✅ 扩展 `role.package.complete`：实际导入往返 `state.json`、`mind_box.json`、`memory/l0.jsonl`，并验证 pending wake 快照含导入来源；角色卡与全局配置排除断言保留。
- ✅ 新增 DesktopRuntime 集成：经 `role_import`、`switch_role`、`send_message` 路径验证首次成功 provider request 获得 wake 注入，回复后 pending wake 被消费。
- ⚠️ TASK #57 仍为 PARTIAL：WebView/Tauri 用户侧完整导入交互未自动化；TASK.md §8.13 与 #57 对默认记忆/状态打包规则存在文本冲突，映射记录按 #57 的明确恢复要求验收。全量映射 3 PASS、52 PARTIAL、8 GAP；23 条 corpus 场景并非全部已执行。
- ✅ 验证：定向角色包/导入唤醒 3 passed in 9.80s；完整回归 `.venv\\Scripts\\python.exe -m pytest tests -v --tb=short -x`：**374 passed in 50.29s**。
- ✅ 验证：验收映射与 corpus 身份/唯一编号检查：2 passed in 1.41s；`git diff --check` 通过（仅换行符提示）。

### 正式验收推进（2026-11-07，第 18 轮）

- ✅ 新增 `ui.mode.override` corpus 场景与桌面 IPC 测试：前台 `code` 识别工作模式；用户覆盖为陪伴模式后在状态快照可见；清除覆盖后回到自动模式。
- ⚠️ TASK #61 从 GAP 调整为 PARTIAL：工作模式文件卡片和工作细节不进入摘要记忆仍待实现与端到端验证。映射当前 3 PASS、53 PARTIAL、7 GAP；corpus 共 24 条唯一场景。
- ✅ 定向模式覆盖测试：2 passed in 3.24s。
- ✅ 补齐 TASK #63 failure/timeout 链路：工具失败与超时追加角色 `world.jsonl`，携带 role_id/status/memory_written 元数据；统一事件日志仍可游标订阅，`dist/index.html` 状态行投影已有事件文本断言，L0 不被写入。新增 `tools.failure.world_notice` corpus 场景；映射保持 PARTIAL，真实工具执行器与 WebView 自动化尚缺。
- ✅ 验证：定向工具验收 1 passed in 6.48s；完整回归 `.venv\\Scripts\\python.exe -m pytest tests -v --tb=short -x`：**376 passed in 49.02s**。

### 正式验收推进（2026-11-07，第 19 轮）

- ✅ TASK #25 基准改用 `acceptance/corpus.json` 中的查询与记忆文本，确定性重复扩展到指定 1000–3000 条热库规模，报告 P50/P95/P99、最大值与预算超限次数。
- ✅ 验证：基准测试 2 passed in 7.84s；1000 条、100 次本机测量 P50=41.132ms、P95=66.954ms、P99=72.418ms、最大值 73.881ms，预算超限 0。
- ⚠️ 当前只执行本地词法检索，未接入同机持久向量库与固定跳数图扩散；#25 从 GAP 调整为 PARTIAL，不能据此宣称完整同步检索链路达标。映射状态现为 3 PASS、54 PARTIAL、6 GAP；corpus 25 条唯一场景。
- ✅ 全量验证：`.venv\\Scripts\\python.exe -m pytest tests benchmarks\\test_retrieval_baseline.py -v --tb=short -x`，**378 passed in 54.13s**。

### 正式验收推进（2026-11-07，第 20 轮）

- ✅ 新增 `skill.registry.default_disabled` corpus 场景及 `SkillRegistry`：工具声明/安装与技能启用状态分离；默认没有注册工具，关闭时不可调用；启用后进入活动注册表，禁用后移除。技能状态归 DesktopRuntime 全局实例，切换角色后保持一致。
- ⚠️ TASK #19 从 GAP 调整为 PARTIAL。当前覆盖运行时默认关闭、注册开关与跨角色共享；安装状态持久化、外部插件安装/供应商适配、技能面板和失败隔离仍未闭环。
- ✅ 定向验收：`tests/test_acceptance_corpus.py::test_skill_registry_defaults_off_and_is_shared_across_roles`，1 passed in 2.85s；前一版完整测试中 corpus 验收模块 17 passed。
- ✅ 全量验证：`.venv\\Scripts\\python.exe -m pytest tests benchmarks\\test_retrieval_baseline.py -v --tb=short -x`，**379 passed in 59.84s**。验收映射 63 项；复核完整回归输出与测试模块计数后同步耗时。，3 PASS /55 PARTIAL /5 GAP；corpus 26 条唯一场景。`git diff --check` 结果待最终检查。

### 正式验收推进（2026-11-08，浏览器回归）

- ✅ 新增 Playwright Chromium WebView 合约测试：实际运行 `dist/index.html` 并经注入 Tauri invoke 桥调用 `DesktopRuntime.handle`；覆盖对话渲染、星图五视图、配置写入持久化、角色包导入/预设/技能页面流程、工具失败事件订阅。六个视觉场景使用固定 1440×1000 / DPR 1 截图及提交版 PNG 基线，changed-pixel 比例阈值为 1.5%。
- ⚠️ #33 快速接话/TTS 取消、#58 六模块首次引导与本地降级、#62 主动表达弹窗/静默仍为 GAP；#40 临时效价/唤醒投影及阈值已测，但尚无主动调度器，保持 PARTIAL。
- ✅ 浏览器回归：`tests/test_webview_contract.py`，**5 passed in 14.68s**。
- ✅ Round 2 全量回归：`.venv\\Scripts\\python.exe -m pytest tests -v --tb=short -x`，**390 passed in 28.90s**。映射 63 项：2 PASS、58 PARTIAL、3 GAP；corpus 27 个场景。
- ✅ Round 3 全量回归：`.venv\\Scripts\\python.exe -m pytest tests benchmarks\\test_retrieval_baseline.py -q --tb=short -x`，**392 passed in 28.85s**。修复映射路径校验要求证据为具体文件；6 张视觉基线纳入对应视图和角色面板验收证据。
