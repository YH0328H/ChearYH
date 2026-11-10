# 主动表达闭环实现 - 错误教训记录

## 时间：2026-11-10

### 1. 类方法位置错误
**错误**: 将方法添加到类外函数内部（desktop.py 1062行，_post_json函数内）
**后果**: 方法不属于类，无法调用
**正确**: 必须在类结束前（def _context之前）插入方法
**教训**: 修改大文件时，先精确定位类边界，避免插入到错误作用域

### 2. 配置路径计算错误
**错误**: workspace.parent = data/roles（实际应该是 data/roles/default 的父级）
**正确**: workspace.parent.parent / "config" / "proactive.toml"
**教训**: Path 对象的 parent 属性含义要清楚，必要时打印验证

### 3. 函数签名不匹配
**错误**: ProactiveScheduler(config, clock) - 多传了 clock 参数
**正确**: ProactiveScheduler(config) - 只需配置对象
**教训**: 调用前检查 __init__ 签名，不要凭记忆猜测参数

### 4. 状态访问模式混乱
**错误**: 
- self.runtime.role_state（不存在）
- runtime.role.state（错误的访问路径）
**正确**: 
- self.runtime._read_state() 返回 dict
- state.get("last_interaction_ts")
**教训**: 状态访问必须通过明确的 API，不要假设属性存在

### 5. 过度设计新 API
**错误**: 试图在 RuntimeServices 添加 tick_proactive_scheduler() 和 generate_proactive_expression()
**后果**: 多处需要同步修改，容易遗漏
**正确**: 在 desktop.py 中直接调用 scheduler.tick() 和内置模板
**教训**: 简单任务优先选择直接调用，避免过度抽象

### 6. 测试代码破坏生产代码
**错误**: 测试中 runtime._state = dict，但 _read_state() 期望 StateSnapshot 对象
**后果**: 'dict' object has no attribute 'dimensions'
**正确**: 修改 _read_state() 支持 isinstance(dict) 判断
**教训**: 测试 mock 必须考虑生产代码的类型期望，或修改生产代码兼容测试场景

### 7. 变量名错误
**错误**: 测试中使用 services.events（变量未定义）
**正确**: runtime_with_proactive.runtime 或 runtime_with_proactive._events
**教训**: 复制粘贴测试代码后，必须检查所有变量引用是否正确

## 通用原则
1. **修改前先读懂**: 不要凭印象修改，先用 read 确认结构
2. **小步验证**: 每次改动后立即测试，不要累积多个修改
3. **类型一致**: mock 对象必须与生产代码类型期望一致
4. **API 优先**: 优先使用现有 API，避免假设内部属性
5. **简单直接**: 能直接调用就不要新增中间层


## 任务2：快速接话TTS集成 - 错误教训

### 时间：2026-11-10

#### 1. 导入成功但初始化缺失
**错误**: 在 RuntimeServices 添加了导入语句，但初始化代码未正确插入
**原因**: 正则替换失败，没有找到正确的插入点
**后果**: 运行时 AttributeError: 'RuntimeServices' object has no attribute 'backchannel'
**正确**: 
  - 先精确定位插入位置（如 proactive_scheduler 初始化后）
  - 使用行号直接插入，而非复杂正则
  - 插入后立即验证属性存在
**教训**: **导入 ≠ 初始化**，两个步骤必须分别验证

#### 2. 模块名猜测错误
**错误**: 
  - 第一次尝试：from cether.registry import RoleRegistry
  - 第二次尝试：from cether.roles import Roles
**原因**: 没有先查看实际文件内容，凭印象猜测
**正确**: 实际是 from cether.roles import RoleRegistry
**教训**: 
  - 不要猜测导入路径，先 ls src/cether 列出文件
  - 再检查文件中的实际类名（class RoleRegistry）
  - 参考现有测试的导入（test_proactive_integration.py）

#### 3. 过度依赖其他测试的模式
**错误**: test_proactive_integration.py 不导入 RoleRegistry，我以为可以跳过
**真相**: test_proactive_integration.py 直接用 DesktopRuntime(data_dir)，因为它会自动创建 registry
**教训**: 
  - 理解模式背后的原因，不要盲目复制
  - DesktopRuntime.__init__ 会自动创建 RoleRegistry
  - 简化测试时，优先模仿已通过的测试结构

#### 4. 正则替换的脆弱性
**错误**: 多次使用复杂正则尝试在 RuntimeServices.__init__ 中插入代码
**问题**: 
  - 正则匹配失败，没有插入任何内容
  - 没有验证插入是否成功
  - 后续测试直接失败，浪费时间
**正确**: 
  - 使用行号直接插入（找到 line 111，在其后插入）
  - 插入后用简单的 includes() 验证
  - 小文件优先读取整个文件，按行操作
**教训**: **避免复杂正则，优先使用确定性的行号插入**

#### 5. 测试先于验证
**错误**: 添加集成代码后，直接运行测试，没有先验证初始化
**后果**: 6 个测试全失败，错误信息相同（backchannel 不存在）
**正确**: 
  - 集成后，先用简单脚本验证属性存在
  - 或者先写一个最小测试（只检查 runtime.backchannel is not None）
  - 验证通过后再运行完整测试套件
**教训**: **先验证基础结构，再验证行为**

## 任务2总结原则
1. **验证层次**: 导入 → 初始化 → 属性存在 → 方法调用 → 行为正确
2. **查看胜于猜测**: 先 ls/grep/read，后 import/call
3. **确定性插入**: 行号 > 正则 > 字符串查找
4. **最小验证**: 先验证结构，后验证行为
5. **模仿已知**: 参考已通过的测试，理解其原因
