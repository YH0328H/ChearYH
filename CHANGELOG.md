# CetherYH 开发日志

## [未发布] - 2026-11-10

### 新增功能

#### 主动表达完整闭环
- 新增 `src/cether/proactive.py` - ProactiveScheduler 调度器
- 新增 `config/proactive.toml` - 四类触发器配置
- 集成到 RuntimeServices 和 DesktopRuntime
- 测试覆盖：7/7 通过（tests/test_proactive_integration.py）

#### 快速接话 TTS 集成
- 新增 `src/cether/tts.py` - Edge TTS 服务
- 新增 `config/tts.toml` - TTS 配置
- BackchannelScheduler 集成真实 TTS 队列
- 测试覆盖：14/15 通过（tests/test_tts.py, tests/test_backchannel_integration.py）

#### 首次引导与本地降级
- 新增 FallbackProvider 三级降级机制（providers.py）
- 新增 OllamaProvider 本地模型支持
- 新增 `config/onboarding.toml` - 六模块引导内容
- bootstrap API 增强，complete_onboarding API
- 测试覆盖：10/10 通过（tests/test_fallback.py, tests/test_onboarding_integration.py）

#### 工作模式产物隔离
- conversation.py：记忆写入条件判断（仅 companion 模式持久化）
- desktop.py：set_mode API（手动模式切换）
- mode.py：ModeController（自动识别 + 手动覆盖）
- 测试覆盖：4/4 通过（tests/test_work_mode_isolation.py）

### 修改

#### conversation.py
- `_respond` 方法新增 `mode` 参数
- 记忆写入改为条件执行：`if mode == "companion"`
- `send` 方法传递 mode 参数

#### desktop.py
- 新增 `_set_mode` 方法
- 新增 `_complete_onboarding` 方法
- `send_message` 动作传递当前模式到 conversation

#### runtime_services.py
- 初始化 ProactiveScheduler
- 初始化 BackchannelScheduler（集成 TTS）
- 初始化 TTS 服务

### 依赖
- 新增 `edge-tts>=7.0.0` (pyproject.toml)

### 测试
- 总计：28/29 测试通过，1 跳过
- 新增测试文件：
  - tests/test_proactive_integration.py (7 tests)
  - tests/test_tts.py (8 tests, 1 skipped)
  - tests/test_backchannel_integration.py (6 tests)
  - tests/test_fallback.py (5 tests)
  - tests/test_onboarding_integration.py (5 tests)
  - tests/test_work_mode_isolation.py (4 tests)

### 已知问题
- edge-tts 未安装时，TTS 测试会跳过（1 个测试）
- 工作模式的文件卡片自动触发需前端集成
- 产物归档到 workspace/ 需定义归档策略

### 下一步
- 外部工具真实执行器（TASK #19, #63）
- 配置持久化与热加载完善
- 星图可视化真实渲染
- 冷库完整交互

---

## 版本说明

- **当前版本**：V3.0 设计中
- **稳定版本**：V2.1
- **开发模式**：随缘开发（2026-11-08 起）

