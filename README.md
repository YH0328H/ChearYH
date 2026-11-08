# CetherYH — 五行认知架构桌面陪伴应用

<div align="center">

**版本**: V3.0 (设计中) | V2.1 (当前稳定版)  
**平台**: Windows / macOS / Linux  
**框架**: Tauri 2.x + Python 3.11+  
**架构**: 五行平衡 × 李雅普诺夫临界态 × PSI 认知

[📖 设计文档](#设计文档) · [🚀 快速开始](#快速开始) · [🎯 核心特性](#核心特性) · [🛣️ 迭代路线](#迭代路线)

</div>

---

## 项目简介

CetherYH 是一款融合**传统五行哲学**与**现代认知科学**的桌面 AI 陪伴应用,采用李雅普诺夫临界态理论保持系统动态平衡,提供**有温度、懂情境、能主动关怀**的智能陪伴体验。

**核心理念(五行平衡)**:
- 🌳 **木(生长)**: 智能感知 + 持续学习 + 好奇心驱动
- 🔥 **火(表达)**: 实时互动 + 情绪表达 + 社交联结
- 🏔️ **土(稳定)**: 本地优先 + 纯文件存储 + 隐私保护
- ⚙️ **金(掌控)**: 决策透明 + 可解释 AI + 用户主权
- 💧 **水(联结)**: 主动关怀 + 深度共情 + 长期记忆

---

## 快速开始

### 环境准备

**必需**:
- Python 3.11+ (推荐使用虚拟环境)
- Node.js 18+ (如需修改前端)
- Rust 1.70+ (如需编译 Tauri)

**可选**:
- Ollama (本地模型推理)
- NVIDIA GPU (本地模型加速)

### 安装步骤

#### 1. 克隆仓库
```bash
git clone https://github.com/your-username/CetherYH.git
cd CetherYH
```

#### 2. 安装 Python 依赖
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

#### 3. 配置 API Key

编辑 `config/api_providers.md` 或在应用内设置面板配置:
- 对话通道: DeepSeek / Claude / GPT-4
- 后台通道: Embedding / TTS / Vision 等

#### 4. 启动应用

**方式 A: 直接运行已编译版本**
```powershell
# Windows
.\start.ps1

# 或带参数
.\start.ps1 -Build  # 开发模式(cargo tauri dev)
.\start.ps1 -DataDirectory "D:\MyData"  # 自定义数据目录
```

**方式 B: 开发模式**
```bash
cd src-tauri
cargo tauri dev
```

**方式 C: 构建生产版本**
```bash
cd src-tauri
cargo tauri build
```

---

## 核心特性

### V2.1 (当前稳定版)

#### ✅ 基础能力
- **对话管理**: 多轮对话 + 会话续接摘要
- **记忆系统**: L0 原始记忆 + L1 摘要 + 冷库归档
- **情绪系统**: PAD 三维模型 + 7 种情绪状态
- **角色系统**: 可切换角色 + 独立配置
- **工作模式**: 陪伴模式 + 工作模式分离

#### ✅ 可视化
- **记忆星图**: 5 种视图(galaxy/nebula/clusters/timeline/list)
- **状态面板**: PAD 情绪图表 + 情绪环 + 心事匣
- **立绘渲染**: 静态 PNG + 7+ 表情切换

#### ✅ 主动能力
- **主动表达**: 心事匣候选生成(定期回顾)
- **门限检查**: window/sleep/mode/cooldown/daily_cap

#### ✅ 工程能力
- **UTF-8 修复**: Windows GBK 环境兼容
- **API 配置**: 对话通道 + 6 个后台通道完整管理
- **文件选择器**: Tauri 原生 pick_file/pick_folder/save_file

### V3.0 (随缘开发中)

#### 🚀 核心升级

**智能调度层** (Sakura 架构启发):
- **ContextOrchestrator**: 多源上下文优先级裁决 + 动态预算分配
- **backchannel**: 用户输入时实时微表情反馈(<500ms)
- **决策透明化**: 所有主动行为记录决策日志

**感知能力**:
- **屏幕感知**: 截图 + 哈希检测 + GPT-4V/Claude Vision 理解
- **语音交互**: Whisper.cpp ASR + Edge TTS / VITS 本地克隆
- **环境感知**: Open-Meteo 天气 + 时区 + 用户活跃度

**主动能力**:
- **周期性观察**: 定期检查(用户离开/工作压力/心事匣/天气)
- **多触发器**: IdleTrigger / StressTrigger / MindBoxTrigger / WeatherTrigger
- **智能调度**: gate 检查 + 优先级裁决 + 频率控制

**记忆升级**:
- **混合检索**: BM25 + Embedding + PPR 图扩散 + MMR 去重
- **召回准确率**: 从 62% 提升到 ≥85%

**本地化**:
- **Ollama 集成**: 本地模型推理(隐私保护 100%)
- **本地 Embedding**: BAAI/bge-m3(1024 维,多语言)

**双模式**:
- **应用模式**: 全屏多面板(深度功能)
- **桌宠模式**: 透明悬浮小窗(轻量陪伴)

---

## 项目结构

```
CetherYH/
├── src/cether/                   # Python 后端核心(五行模块)
│   ├── desktop.py                # 桌面运行时入口
│   ├── runtime_services.py       # 服务编排
│   ├── conversation.py           # 对话管理
│   ├── memory_lifecycle.py       # 记忆生命周期
│   ├── cognition.py              # 决策与表达
│   ├── wuxing_core.py            # (V3.0) 五行驱力系统
│   ├── qiankun_orchestrator.py   # (V3.0) 乾坤上下文编排
│   ├── bagua_emotion.py          # (V3.0) 八卦情绪系统
│   ├── yijing_memory.py          # (V3.0) 易经记忆(六十四卦)
│   ├── taiji_decision.py         # (V3.0) 太极决策(阴阳平衡)
│   ├── backchannel.py            # (V3.0) 快速接话
│   ├── screen_sense.py           # (V3.0) 屏幕感知
│   └── voice.py                  # (V3.0) 语音交互
│
├── src-tauri/                    # Rust Tauri 桌面框架
│   ├── src/lib.rs                # IPC 命令 + Python 桥接
│   ├── Cargo.toml
│   └── tauri.conf.json           # Tauri 配置
│
├── dist/index.html               # 前端单页应用(Vanilla JS)
├── config/                       # 配置文件
│   ├── wuxing_expression.toml    # 五行主动表达配置
│   ├── qiankun_budget.toml       # 乾坤上下文预算
│   ├── bagua_config.toml         # 八卦情绪配置
│   └── api_providers.md          # API 配置说明
│
├── roles/{role_name}/            # 角色包
│   ├── config.yaml               # 角色配置
│   ├── character.yaml            # 角色卡
│   └── portraits/                # 立绘
│
├── docs/                         # 设计文档
│   ├── WUXING_PHILOSOPHY.md      # 五行认知哲学 ★
│   └── legacy/TASK.md            # 历史需求归档
│
├── CetherYH_V3.0_DESIGN.md       # V3.0 完整技术方案 ★
├── ARCHITECTURE.md               # 架构设计 + 五行平衡
├── ALGORITHMS.md                 # 算法详解 + 李雅普诺夫
├── UI_DESIGN.md                  # UI 设计规范
├── DEVLOG.md                     # 开发日志
├── README.md                     # 本文件
└── start.ps1                     # Windows 启动脚本
```

---

## 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| 桌面框架 | Tauri 2.x | 跨平台,轻量级(2MB vs Electron 200MB) |
| 前端 | Vanilla JS (V2.1)<br>React + TS (V4.0 计划) | 当前轻量级,未来工程化 |
| 后端语言 | Python 3.11+ | NLP/ML 生态丰富 |
| 存储 | JSONL + SQLite FTS5 | 纯文件易备份 + 全文检索 |
| LLM(云端) | DeepSeek / Claude / GPT-4 | 用户自选 |
| LLM(本地) | Ollama | 隐私保护,离线可用 |
| Embedding | BAAI/bge-m3 | 本地 1024 维,多语言 |
| 语音识别 | Whisper.cpp | 本地 ASR,保护隐私 |
| 语音合成 | Edge TTS / VITS | 免费 + 可定制音色 |
| 天气 API | Open-Meteo | 免费,无需 API key |

---

## 开发状态

### 模块完成度

| 模块 | V2.1 | V3.0 目标 |
|------|------|----------|
| 情绪系统 | 85% | 90% (情绪留疤) |
| 记忆系统 | 75% | 95% (混合检索 + 图扩散) |
| UI/UX | 70% | 90% (桌宠模式 + Live2D) |
| 时空系统 | 60% | 85% (天气 + 昼夜节律) |
| 感知系统 | 0% | 80% (屏幕 + 语音) |
| 主动能力 | 40% | 90% (周期观察 + 多触发器) |
| 决策透明 | 0% | 100% (决策日志) |
| 本地模型 | 0% | 80% (Ollama 集成) |
| 关系系统 | 40% | 60% (亲密度/信任度模型) |
| 多模态 | 30% | 70% (语音 + 屏幕) |
| 跨端支持 | 0% | 0% (V4.0 计划移动端) |

---

## 设计文档

### 核心设计
- [📘 V3.0 完整技术方案](CetherYH_V3.0_DESIGN.md) ★ **最新最完整**
- [☯️ 五行认知哲学](docs/WUXING_PHILOSOPHY.md) ★ **易经 × 李雅普诺夫**
- [🏗️ 架构设计](ARCHITECTURE.md) — 五行平衡 + 临界态维持
- [🧮 算法详解](ALGORITHMS.md) — 五行驱力 + 李雅普诺夫谱
- [🎨 UI 设计规范](UI_DESIGN.md) — 307 行完整设计

### 开发日志
- [📝 DEVLOG.md](DEVLOG.md) — 开发历史记录
- [🔧 API 配置说明](config/api_providers.md) — 云端通道配置

### 历史归档
- [📦 原始需求文档](docs/legacy/TASK.md) — V1.0 需求(已归档)

---

## 迭代路线

### V3.0 (随缘开发中)
**核心目标**: 从"会对话的工具"到"有温度的陪伴者"

**核心架构升级**:
- [x] UTF-8 编码修复
- [ ] ContextOrchestrator 实现
- [ ] backchannel 快速接话
- [ ] 决策透明化
- [ ] 记忆检索升级(BM25 + PPR + MMR)
- [ ] 会话管理后端集成

**体验提升**:
- [ ] 屏幕感知
- [ ] 语音交互
- [ ] 主动关怀调度
- [ ] 桌宠模式
- [ ] 天气现实锚点

**本地化与集成**:
- [ ] Live2D 立绘
- [ ] Ollama 本地模型
- [ ] 全量测试
- [ ] 文档更新

**验收标准**:
- ✅ 记忆召回准确率 ≥85%
- ✅ backchannel 响应延迟 ≤500ms
- ✅ 主动表达相关性 ≥80%
- ✅ 屏幕感知哈希准确率 ≥95%
- ✅ 决策日志覆盖率 100%

### V3.5 (后续规划)
- 插件市场
- World Info 系统
- 本地视觉理解(LLaVA)

### V4.0 (后续规划)
- 前端迁移 React + TypeScript
- 移动端适配(iOS/Android)
- 云端同步(可选)

### V5.0 (远期规划)
- 情绪留疤
- 睡眠巩固
- 空间记忆宫殿
- 摄像头情绪识别

---

## API 示例

### 发送消息
```python
# Python 后端
from cether import DesktopRuntime

runtime = DesktopRuntime(data_dir="./data")
response = runtime.handle({
    "action": "send_message",
    "message": "今天天气怎么样?"
})
```

```javascript
// 前端 JavaScript
async function send(text) {
  const response = await invoke('send_message', { 
    roleId: active.id, 
    message: text 
  });
  appendMessage('assistant', response.content);
}
```

### 切换角色
```javascript
await invoke('switch_role', { roleId: 'sakura' });
```

### 主动表达(V3.0)
```python
# 触发器检查
trigger = IdleTrigger(threshold=1800)
if trigger.should_fire(context):
    candidate = trigger.generate_candidate()
    runtime.emit_active_expression(candidate)
```

---

## 成本预估

**典型使用场景**(200 turns/day):
- 对话生成: ¥48/月(DeepSeek V4.1 Flash)
- 屏幕感知: ¥42/月(GPT-4V,哈希优化后)
- 记忆巩固: ¥18/月
- 主动表达: ¥12/月
- 其他(Embedding/TTS/ASR): ¥0(本地)

**总计**: ¥75-160/月(取决于屏幕感知使用频率)

**本地模式**(Ollama): ¥0/月 + 硬件成本(RTX 3060 级别 GPU 推荐)

---

## 贡献指南

欢迎贡献代码、文档和建议!

### 如何贡献
1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

### 代码规范
- Python: PEP 8 + Black formatter
- JavaScript: ESLint + Prettier
- Rust: cargo fmt + clippy

### 文档规范
- 中文文档优先
- 代码示例包含注释
- 保持 README 简洁,详细内容放入独立文档

---

## 许可证

MIT License

Copyright (c) 2026 CetherYH Contributors

---

## 致谢

本项目融合以下理论与开源项目:

### 理论基础
- [易经](https://zh.wikipedia.org/wiki/易经) — 阴阳五行哲学
- [黄帝内经](https://zh.wikipedia.org/wiki/黄帝内经) — 天地人三才
- [Lyapunov Spectrum (Clark 2026)](https://arxiv.org/abs/2610.12426) — 临界态动力学
- [PSI (Joscha Bach 2009)](http://www.cognitive-ai.com/) — 驱力认知架构
- [The Synthetic Mind (Ferrer 2026)](https://github.com/joshferrer1/the-synthetic-library) — 赫尔驱力理论

### 开源项目
- [Sakura Desktop Pet](https://github.com/Rvosy/Sakura) — ContextOrchestrator 架构
- [Lararium](https://github.com/lararium-app/lararium) — 纯文件记忆
- [graph-memory](https://github.com/Doodle-Lin/graph-memory) — 混合检索栈
- [Jan](https://github.com/janhq/jan) / [WindowPet](https://github.com/SeakMengs/WindowPet) — 桌面应用范例

特别感谢所有为 AI 陪伴领域与认知科学贡献的开发者和研究者!

---

## 联系方式

- Issues: [GitHub Issues](https://github.com/your-username/CetherYH/issues)
- Discussions: [GitHub Discussions](https://github.com/your-username/CetherYH/discussions)
- Email: your-email@example.com

---

<div align="center">

**⭐ 如果这个项目对你有帮助,请给一个 Star! ⭐**

Made with ❤️ by CetherYH Team

</div>
