# CetherYH UI 方案与路径对齐

> 状态：设计方案，尚未进入 UI 实现。本文记录产品方向、页面内容、后端契约映射和建议代码路径；“建议新增”路径仅用于后续规划，不代表文件已存在。
>
> 本轮只写入本文档；不创建前端组件、不增加 Tauri IPC、不执行测试。

## 1. 设计目标与边界

- 产品主场景是与当前加载角色相处和聊天，不是运行时管理工作台。
- 角色是可替换的外部内容。任何角色的名称、立绘、表达映射、人设、主题和专属行为配置均从角色包/角色工作区读取；通用 UI 不写死艾莉丝或其他角色。
- 启动后恢复最近使用的角色与会话。没有可用角色时呈现通用的选择、导入或创建角色流程，不自动注册默认角色。
- 陪伴模式与工作模式分开呈现。陪伴首屏保持沉浸和低噪音；工作模式承载长文、代码和文件卡片。
- UI 通过稳定的 view/action 契约操作运行时，不直接读写记忆文件、状态文件或模型服务。
- 角色专属配置随角色切换；对话通道、后台通道、技能区属于全局设置。技能全局共享，不随角色包迁移。
- 内部状态指标主要用于后端决策。普通界面优先显示自然语言状态与原因，数值仅在用户主动展开的高级解释中出现。

## 2. 路径标注规则

| 标签 | 含义 |
|---|---|
| **现有实现** | 当前仓库已发现的代码或配置路径；只代表该文件/契约存在，不代表完整 UI 已可用。 |
| **任务依据** | 项目任务或架构文档中的产品要求。 |
| **建议新增** | 后续实现时可以采用的前端或 IPC 路径；目前未发现该源码，不在本次创建。 |
| **待核验** | 需求已有描述，但当前看到的代码不足以确认其已端到端落地。 |

### 当前代码现状

- **现有实现**：`src/cether/ui_contract.py` 定义 `AppView`、`RoleCardView`、`StatusView`、`MemoryTimelineView`、`MemoryNodeView`、`UiAction`、用户动作反馈与星图投影。
- **现有实现**：`src/cether/roles.py` 提供全局单活角色注册、角色工作区隔离、切换进度和失败回滚等运行时能力。
- **现有实现**：`src/cether/runner.py` 与 `src/cether/runtime_services.py` 提供运行循环和角色级服务组合；部分决策、表达、睡眠/反思与检索服务仍由 provider 注入。
- **现有实现**：Tauri 壳入口为 `src-tauri/src/lib.rs`、`src-tauri/src/main.rs`。
- **待实现/待核验**：本次检索未发现应用前端 TS/JS 组件源码；DEVLOG.md 记录 Tauri IPC、视觉面板和端到端验证仍待推进。
- **待核验**：`src/cether/role.py` 与 `src/cether/roles.py` 都定义角色注册/切换概念；本文把 `roles.py` 视作 DEVLOG 与 `ui_contract.py` 当前实际引用的整合契约，不在本方案内合并或删除实现。

## 3. 全局信息架构

```text
陪伴首页
├─ 会话抽屉
│  ├─ 会话搜索 / 新建 / 最近会话
│  ├─ 当前角色与切换入口
│  ├─ 角色管理
│  ├─ 记忆
│  ├─ 它现在怎么样
│  ├─ 工作模式
│  └─ 设置
├─ 当前会话
│  ├─ 消息时间线
│  ├─ 当前角色立绘与表达状态
│  └─ 输入与发送
├─ 角色管理
│  ├─ 角色列表 / 切换
│  ├─ 创建 / 导入 / 封存
│  └─ 角色编辑
├─ 记忆
│  ├─ 列表 / 搜索 / 详情
│  ├─ 星空（后续丰富视图）
│  └─ 冷库时间轴
└─ 设置
   ├─ 对话通道
   ├─ 后台通道
   ├─ 技能（全局）
   ├─ 行为基线（只读说明）
   └─ 记忆管理
```

主界面不显示常驻三栏、会话管理仪表盘、模型参数或记忆图谱。导航采用覆盖式抽屉/轻量侧栏，避免压缩陪伴画面。

## 4. 启动首屏：陪伴与聊天

### 结构草图

```text
┌──────────────────────────────────────────────────────┐
│ ☰                 [当前加载角色名称]              ⋯  │
│                                                      │
│                   当前角色立绘                       │
│                                                      │
│                       对话                           │
│                                                      │
│                                                      │
│       ┌──────────────────────────────────┐           │
│       │ 说点什么……                  发送 │           │
│       └──────────────────────────────────┘           │
└──────────────────────────────────────────────────────┘
```

### 行为与内容

- 顶栏只放抽屉入口、当前角色名称和少量会话/角色快捷操作。角色编辑正式入口放在角色管理；当前会话菜单可提供“编辑当前角色”的快捷跳转。
- 立绘是聊天场景的一部分，不固定为右侧状态仪表盘。消息稀少时立绘更突出，消息变多时适度收敛占比；具体自适应规则需在视觉原型阶段验证。
- 使用角色包中的整张立绘，根据表达标签切换图片并交叉淡入；只做克制的入场/状态变化微动效，不假设素材具有 Live2D 骨骼或透明图层。
- 表达指令与图片切换应通过统一运行时事件/前端状态通道传递，避免前端自行推断角色心理状态。
- 首屏不直接展示四意愿、六维驱力、阈值、模型 ID、检索延迟、后台任务日志。
- 无活跃角色时进入“选择已有角色 / 导入角色包 / 创建角色”的空状态；不以任何角色作为系统默认角色。

**路径对齐**

| UI 能力 | 后端映射 | 依据 / 状态 |
|---|---|---|
| 当前角色名称、状态摘要、首启提示 | `src/cether/ui_contract.py::AppView`、`RoleCardView` | 现有 view model；与 Tauri 的数据传输尚需接线 |
| 聊天内容、会话列表、会话搜索与新建 | 当前尚无已核验的会话 UI/IPC 契约 | **建议新增** `src-tauri/src/commands/conversation.rs` 与 `apps/desktop/src/features/conversation/`（仓库当前未发现 `apps/desktop`） |
| 当前立绘、角色表达映射 | 角色包 `appearance.json`、`expression.json`；`src/cether/roles.py::ROLE_CARD_FILES` | 角色资产归角色；UI 组件路径建议 `apps/desktop/src/features/companion/PortraitStage.tsx` |
| 动作/表情事件 | `src/cether/runner.py::RuntimeEvent` 可供运行过程观测，但并非完整前端表达协议 | **待核验/建议新增** 稳定表达事件 schema 和 Tauri event 映射 |

## 5. 会话与导航抽屉

### 抽屉内容

```text
┌─────────────────────────┐
│ 搜索会话          ＋新会话│
│ 最近会话                 │
│  会话标题           时间 │
│  会话标题           时间 │
│                          │
│ 当前角色                 │
│ 角色管理                 │
│ 记忆                     │
│ 它现在怎么样             │
│ 工作模式                 │
│ 设置                     │
└─────────────────────────┘
```

- 默认覆盖内容，不挤压主聊天画布；宽屏可采用窄抽屉，窄屏全屏覆盖。
- 选择会话后自动收起。会话列表与当前活跃角色清楚区分，避免用户误以为切换会话会切换角色。
- 设置入口不放在桌宠右键菜单；桌宠右键菜单只放高频陪伴动作。

**路径对齐**

- 会话列表/搜索/CRUD：后端会话持久化和 UI 数据契约目前未在所查文件中发现；建议新增 `src/cether/conversations.py`、`src-tauri/src/commands/conversation.rs`、`apps/desktop/src/features/conversation/ConversationDrawer.tsx`。
- 右键快捷动作依据 `TASK.md` 第十章；现有动作可复用 `src/cether/ui_contract.py::CONTEXT_MENU_ACTIONS`，但“它现在怎么样”和角色切换等菜单项尚需补齐契约映射。
- 桌面窗口拖动、置顶和透明行为依据 `TASK.md` 113–116；Tauri 窗口基础壳存在，具体交互需在 `src-tauri/src/lib.rs` 后续核验。

## 6. 角色管理与角色编辑

### 角色列表

```text
角色
┌─────────────────────────────────────────────┐
│ [角色图] 角色名称                            │
│          当前使用 / 最近活跃                 │
│          一句状态摘要                        │
│                         [进入] [编辑 ⋯]       │
└─────────────────────────────────────────────┘
[＋创建角色] [导入角色包] [封存室]
```

列表显示活跃/休眠/封存状态；最多五个角色，任一时刻只有一个活跃。切换前显示目标名称、最近活跃、状态摘要、工作区；切换过程中逐步显示保存当前角色、取消任务、释放资源、加载目标、唤醒等进度。失败时内联显示原因，并保留原角色上下文。

### 编辑页面

```text
编辑角色
├─ 基本信息：名称、简介、角色包信息
├─ 人设与边界：persona、hard boundaries
├─ 立绘与表达：资源、表达标签映射、主题色
└─ 行为节奏：角色专属窗口与检查点
```

角色编辑页不放对话模型、后台通道或全局技能配置。导入同名角色包时必须显式选择覆盖或重命名，不静默覆盖。

**路径对齐**

- 角色列表、状态、最近活跃、工作区和切换动作：`src/cether/ui_contract.py::RoleCardView`、`UiAction.SWITCH_ROLE`。
- 生命周期、最大数量、角色包和回滚：`src/cether/roles.py`；角色包文件名定义在 `ROLE_CARD_FILES`。
- 数据契约/操作入口已存在；完整角色编辑、新建和导入 UI、导入冲突交互需要前端与 IPC 补齐。
- 建议新增：`apps/desktop/src/features/roles/RoleListPage.tsx`、`RoleEditorPage.tsx`、`RoleSwitchProgress.tsx`；Tauri 命令放入 `src-tauri/src/commands/roles.rs`。这些路径当前不存在。
- 任务依据：`TASK.md` 第九章、十章第 11 条及修订条款 9.11–9.12；`ARCHITECTURE.md` 配置来源优先级。

## 7. “它现在怎么样”状态面板

### 展示草图

```text
它现在怎么样

“有点累，但还想陪你待一会儿。”

此刻     慵懒、安静
原因     处于静默时段，等你先开口
心事     有件事还没想好怎么说
节奏     晚间陪伴窗口 · 当前清醒
```

- 默认是自然语言说明，解释角色状态质地、沉默原因、心事匣、窗口与睡眠。
- 可展开“状态依据”查看低优先级的数值细节和数据来源；避免把这些数值描述为客观心理诊断。
- 如果无心事、无闸门原因或状态服务不可用，对应行隐藏或明确标注数据暂缺，不填充虚构内容。

**路径对齐**

- 当前可用数据结构：`src/cether/ui_contract.py::StatusView`（`texture`、`gate_reason`、`mind_box`、`window_status`、`sleep_status`、`mode`、`mode_source`）。
- UI 动作和 view 的外壳：`UiContract.app_view()`；具体 `status` provider 注入，尚需在应用 composition 中接线。
- 任务依据：`TASK.md` 第五章第 12 条、第十章第 4 条，以及 `src/cether/gate.py`、`src/cether/state.py`、`src/cether/window.py` 的领域能力。
- 建议新增：`apps/desktop/src/features/status/StatusSheet.tsx`；状态解释文本应由明确的后端状态翻译结果提供，UI 不自行用原始数值拼装情绪结论。

## 8. 记忆面板

### 默认列表与详情

```text
记忆                               [搜索] [近期] [重要] [归档]

记忆摘要
来源：某次会话 · 时间

选中一条后：
正文 / 来源 / 关联会话 / 时间 / 分类
[让它想想] [刻深] [处理]
```

- 首个可用版本优先完成列表、搜索、分页、详情、来源与关联会话；不要求用户先理解记忆算法。
- “处理”提供明确选择，例如降低权重、移入冷库或删除，并解释影响；客观 L0 记录保持不可变。
- 冷库内容独立浏览，不进入检索范围。
- 星图、聚类和时间轴是记忆页面中的视图切换，不是主导航默认首屏。
- 星图节点以权重映射大小/亮度、分类映射颜色、共现映射连线；新记忆、检索高亮和逐渐沉降属于后续动效。

**路径对齐**

- 现有契约：`src/cether/ui_contract.py::MemoryTimelineView`、`MemoryNodeView`、`UiContract.memory_timeline()`、`memory_starfield()`；动作包含 `OPEN_MEMORIES`、`THINK_AGAIN`、`DEEPEN`、`ARCHIVE_MEMORY`、`RESTORE_MEMORY`、`INJECT_ONCE`。
- 记忆领域当前模块：`src/cether/l0.py`、`src/cether/l1.py`、`src/cether/retrieval.py`、`src/cether/spatial_index.py`。
- `UiContract` 已提供分页契约、星图投影和动作反馈；真实业务持久化/归档恢复回调仍需应用层接线，不能仅凭契约视作已上线。
- 任务依据：`TASK.md` 第四章、第十章第 5–7 条；`PROJECT_GUIDE.md` 第四章记忆分层。
- 建议新增：`apps/desktop/src/features/memory/MemoryListPage.tsx`、`MemoryDetailSheet.tsx`、`MemoryStarfieldPage.tsx`、`ColdArchiveTimeline.tsx`；Tauri command/event 置于 `src-tauri/src/commands/memory.rs`。

## 9. 设置面板

设置按作用范围而非后端 Python 模块逐项铺开：

```text
设置
├─ 对话通道
├─ 后台通道
├─ 技能（全局共享）
├─ 行为基线（只读说明）
├─ 记忆管理
└─ 外观与交互
```

### 对话通道

- 展示单个活跃模型、渠道、模型 ID、连接可用状态和切换提示。
- 切换在下一轮生效，不并发调用多个前台对话模型。
- 凭证只展示“已配置/未配置”，绝不回显密钥。

### 后台通道

- 按职能槽位分组：提取、人设解析、叙事/反思、Embedding、Rerank、TTS、生图。
- 每槽位呈现启用状态、服务类型/本地或云端、模型、降级路径、连接测试结果和内联错误。
- 未配置后台槽位时明确显示可用降级能力；不把降级状态伪装成完整服务正常。

### 技能、行为基线与记忆管理

- 技能是全局共享工具配置，不属于角色包；默认关闭，显示安装/启用状态和跨角色运行状态标识。
- 行为基线为只读解释，说明当前设计规则及来源，不把内部算法参数做成默认调参工作台。
- 记忆管理显示角色工作区归属、存储可用性、整理/归档情况和维护入口；操作须带角色范围确认。

**路径对齐**

- 已发现全局配置文件：`config/state_mapping.toml`、`config/gate.toml`、`config/window.toml`、`config/vision.toml`、`config/narrative.toml`、`config/embedding.toml`、`config/context_budget.toml`。
- 对话/后台通道基础结构：`src/cether/config.py::ChannelConfig`；视觉和叙事、向量配置加载见 `src/cether/vision.py`、`src/cether/narrative.py`、`src/cether/retrieval.py`。当前配置文件覆盖不等于已存在完整的通道配置管理 UI。
- 技能市场/启用 UI 与完整后台槽位统一 CRUD 尚未在本次检查的前端源码中发现；具体服务配置能力需按 TASK.md 与 `CONFIG_FORM.md` 继续核验。
- 任务依据：`TASK.md` 第八章第 5–11 条、第十章第 9–10 条、第十一章第 1–6 条；`ARCHITECTURE.md` 第 1–3 节。
- 建议新增：`apps/desktop/src/features/settings/ConversationChannelPage.tsx`、`BackgroundChannelsPage.tsx`、`SkillsPage.tsx`、`BehaviorBaselinePage.tsx`、`MemorySettingsPage.tsx`。

## 10. 工作模式

- 从抽屉或会话菜单进入；不在陪伴首页并列展示工作台工具栏。
- 长文、代码和文件结果采用清楚的消息排版与文件卡片；保留当前角色和会话连续性。
- 自动识别仅作为建议，并提供可见的手动切换/覆盖。模式切换不更换角色，不改变记忆 scope。
- 工作过程细节不自动进入摘要记忆。

**路径对齐**

- 产品要求见 `TASK.md` 第十章第 8 条、修订条款 61 及项目路线相关章节。
- 尚未发现模式识别和工作消息卡片的 UI/IPC 实现；建议新增 `apps/desktop/src/features/work/WorkModeView.tsx` 和会话消息 renderer 扩展。

## 11. 视觉与交互配置建议

- 整体风格：安静、有角色氛围、内容优先；不套用仪表盘卡片网格。仅对重复实体（角色列表项、记忆条目、文件结果）使用轻量边界容器。
- 色彩：应用有独立中性基础主题；角色包只覆写允许的主题 token，不控制全局可读性、状态语义色和焦点环。浅色/深色均可选，深色不强制为默认。
- 立绘：保留完整画面和适配裁切控制；利用角色包的不同姿态/表情做小幅交叉淡入。不假设用户素材透明或可分层。
- 动效：仅用于抽屉进入/退出、立绘表达切换、消息发送状态和重要运行状态变化；避免无目的持续动画。提供减少动态效果选项。
- 可访问性：键盘可达、焦点清楚、对比度合格、状态不只依赖颜色、动效可减少、窄窗口下文本和控件不重叠。
- 自适应：窗口较窄时抽屉覆盖；聊天始终占据主视觉；立绘在消息多时收敛但保持可达；布局变化不应自行重排导航或隐藏用户控制。

## 12. 实施顺序建议（仅路线，不执行）

1. **IPC 与会话基础**：确认 Tauri 与 Python runtime 的启动/通信机制；实现当前角色/会话读取、消息发送/接收、事件推送和恢复上次会话。
2. **陪伴首屏**：顶栏、消息、输入、角色立绘与无角色空状态；验证角色资产可替换。
3. **角色管理**：列表、切换进度、创建/导入/编辑入口；覆盖失败回滚和单活展示。
4. **状态与记忆**：状态解释面板、记忆列表/详情/分页和真实动作回调；保证角色 scope 可见且隔离。
5. **设置与工作模式**：通道配置、技能、行为基线、记忆管理及文件卡片模式。
6. **增强视图和收口**：星空与冷库高级视图、可访问性/窄窗/动效检查、端到端验证。

此顺序是建议。现有后端有部分契约和能力，但 Tauri IPC 与前端源码尚未在本次检索中发现，故第 1 步应先验证真实工程结构与数据流再定组件拆分。

## 13. 参考资料

- SillyTavern 角色卡与对话模型：[docs.sillytavern.app](https://docs.sillytavern.app/)
- Project N.E.K.O. 开源桌面陪伴项目：[GitHub](https://github.com/Project-N-E-K-O/N.E.K.O)
- 桌面聊天与本地模型产品参考：[Jan](https://github.com/janhq/jan)
- 桌宠/陪伴项目目录（用于观察品类范围，不作为质量排行）：[GitHub desktop-pet topic](https://github.com/topics/desktop-pet)
- 2026 产品 UX 结构趋势（可检查/可覆盖的 AI、可访问性、个性化；视觉潮流需审慎采纳）：[FuseLab Creative](https://fuselabcreative.com/ui-ux-design-trends-2026-modern-ui-trends-ux-trends-guide/)
- 情境适配与对话式界面趋势（文章偏移动端，作为方向性参考）：[UX Pilot](https://uxpilot.ai/blogs/mobile-app-design-trends)
