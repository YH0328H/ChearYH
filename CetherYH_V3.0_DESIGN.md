# CetherYH V3.0 技术方案

**版本**: 3.0  
**更新时间**: 2026-11-08  
**状态**: 设计阶段

---

## 目 录

1. [项目概述](#1-项目概述)
2. [总体架构](#2-总体架构)
3. [层面一：上下文编排与智能调度](#3-层面一上下文编排与智能调度)
4. [层面二：情绪与认知系统](#4-层面二情绪与认知系统)
5. [层面三：记忆系统](#5-层面三记忆系统)
6. [层面四：感知与输入](#6-层面四感知与输入)
7. [层面五：表达与输出](#7-层面五表达与输出)
8. [层面六：主动能力与调度](#8-层面六主动能力与调度)
9. [层面七：角色与多模态](#9-层面七角色与多模态)
10. [成本与性能优化](#10-成本与性能优化)
11. [硬件与资源方案](#11-硬件与资源方案)
12. [维护与运维](#12-维护与运维)
13. [迭代路线](#13-迭代路线)
14. [风险与对策](#14-风险与对策)
    - [附录 A：技术选型清单](#附录-a技术选型清单)
    - [附录 B：参数配置表](#附录-b参数配置表)

---

## 1 项目概述

### 1.1 背景

CetherYH 是一款基于 Tauri 的桌面 AI 陪伴应用,致力于提供有温度、懂情境、能主动关怀的智能陪伴体验。V2.1 版本已实现基础对话、记忆管理、情绪系统和角色切换功能,但在实时反馈、屏幕感知、语音交互等核心陪伴能力上存在显著差距。

V3.0 版本通过借鉴 Sakura、Lararium、MnemoCore、HippoRAG 等优秀开源项目的设计理念,全面升级为"全能型桌面陪伴应用",实现从"会对话的工具"到"有温度的陪伴者"的质变。

### 1.2 建设目标

1. **智能感知**：屏幕感知 + 天气感知 + 用户状态检测,实现情境化陪伴
2. **实时互动**：backchannel 快速接话 + 语音交互,陪伴感提升 80%
3. **主动关怀**：周期性观察 + 多触发器主动表达,主动性提升 60%
4. **决策透明**：完整决策日志 + 可解释 AI,用户信任度提升 40%
5. **本地优先**：Ollama 本地模型 + 纯文件存储,隐私保护 100%
6. **双模式支持**：应用模式(深度功能) + 桌宠模式(轻量陪伴)

### 1.3 设计原则

- **用户主权**：决策透明、可覆盖、可关闭,用户始终掌控
- **本地优先**：记忆纯文件存储、支持本地模型,数据不出本地
- **渐进增强**：核心功能优先云端 API,本地模型作为增强选项
- **模块解耦**：各子系统独立可测,通过 IPC 和事件通信
- **性能优先**：backchannel 延迟 <500ms,主动表达响应 <3s

### 1.4 范围与前提

**包含范围**：
- 桌面原生应用(Windows/macOS/Linux)
- 单用户本地运行
- 云端 API + 本地模型混合架构
- 陪伴模式 + 工作模式双场景

**不包含**：
- 移动端(iOS/Android)
- 多用户协作
- 云端同步服务
- 语音唤醒(硬件依赖)

**前提条件**：
- 用户需自备 LLM API key(云端模式)或本地模型(Ollama)
- 屏幕感知需要用户授权截图权限
- 语音交互需要麦克风/扬声器权限

### 1.5 术语

| 术语 | 含义 |
|------|------|
| ContextOrchestrator | 上下文编排器,负责多源上下文的优先级裁决和预算分配 |
| backchannel | 快速接话机制,用户输入时实时显示微表情反馈,无需等待完整回复 |
| 主动表达 | AI 角色根据观察到的情境(时间/用户状态/记忆)主动发起对话 |
| 决策日志 | 记录所有主动行为的触发原因、评分依据、门限检查等信息 |
| L0/L1 记忆 | L0 为原始记忆(append-only),L1 为摘要记忆(定期巩固生成) |
| 冷库 | 长期归档记忆,按 UTC 月 JSONL 分片存储,支持检索恢复 |
| PAD 模型 | Pleasure-Arousal-Dominance 三维情绪空间模型 |
| 心事匣 | 用户心事/困扰的临时存储,定期触发主动关怀 |

### 1.6 总体指标

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 记忆召回准确率 | ≥ 85% | BM25 + Embedding + PPR 混合检索 |
| backchannel 响应延迟 | ≤ 500ms | 微表情切换延迟 |
| 主动表达相关性 | ≥ 80% | 用户反馈主动话题相关度 |
| 屏幕感知哈希准确率 | ≥ 95% | 无变化时跳过 API 调用比例 |
| 语音识别准确率 | ≥ 90% | Whisper.cpp 本地 ASR |
| 本地模型推理速度 | ≤ 3s/回复 | 7B 模型,RTX 3060 级别 GPU |
| 决策日志覆盖率 | 100% | 所有主动行为可解释 |
| 应用启动时间 | ≤ 2s | 冷启动到首屏可交互 |

---

## 2 总体架构

### 2.1 分层结构

CetherYH V3.0 采用经典的五层架构 + 独立的智能调度层:

```
┌─────────────────────────────────────────────────────┐
│  用户界面层 (UI Layer)                              │
│  - Web UI (应用模式): 记忆星图/状态面板/会话管理    │
│  - 桌宠 UI (桌宠模式): 立绘/气泡/右键菜单           │
├─────────────────────────────────────────────────────┤
│  交互层 (Interaction Layer)                         │
│  - 对话管理: 消息路由/会话续接/上下文注入           │
│  - backchannel: 实时微表情反馈                      │
│  - 输入处理: 文本/语音/屏幕截图                     │
├─────────────────────────────────────────────────────┤
│  智能调度层 (Orchestration Layer) ★核心创新★       │
│  - ContextOrchestrator: 优先级裁决/动态预算分配     │
│  - 主动关怀调度: 周期性观察/多触发器                │
│  - 决策透明化: 决策日志记录/可解释 AI               │
├─────────────────────────────────────────────────────┤
│  认知核心层 (Cognitive Core)                        │
│  - 情绪系统: PAD 三维模型/7 种情绪状态              │
│  - 记忆系统: L0/L1/冷库/混合检索                    │
│  - 关系系统: 亲密度/信任度/互动历史                 │
│  - 时空系统: 时间感知/昼夜节律/天气影响             │
├─────────────────────────────────────────────────────┤
│  感知层 (Perception Layer)                          │
│  - 屏幕感知: 截图/哈希检测/多模态理解               │
│  - 语音感知: ASR 转文字/情绪识别                    │
│  - 环境感知: 天气 API/时区/用户活跃度               │
├─────────────────────────────────────────────────────┤
│  输出层 (Output Layer)                              │
│  - 立绘渲染: 静态 PNG / Live2D(可选)                │
│  - 语音合成: Edge TTS / VITS 本地克隆               │
│  - 表达生成: LLM 生成/规则模板/情绪映射             │
├─────────────────────────────────────────────────────┤
│  基础设施层 (Infrastructure Layer)                  │
│  - 存储: JSONL + SQLite FTS5                        │
│  - LLM 路由: 云端 API / Ollama 本地模型             │
│  - IPC: Tauri Command / Event                       │
└─────────────────────────────────────────────────────┘
```

**关键设计亮点**：
1. **智能调度层独立**：ContextOrchestrator 统一管理所有上下文源,避免各模块直接竞争 token 预算
2. **感知层解耦**：屏幕/语音/环境感知独立采集,通过事件通知调度层
3. **决策透明化**：所有主动行为经过调度层,自动记录决策日志

### 2.2 核心数据流

**典型对话流程**：
1. 用户输入 → backchannel 实时分析(微表情) → 完整输入提交
2. ContextOrchestrator 编排上下文:
   - 紧急源(系统警告/提醒) 优先级 100
   - 主动源(主动表达候选) 优先级 80
   - 响应源(相关记忆) 优先级 60
   - 背景源(天气/时间/屏幕状态) 优先级 20
3. 按优先级 + 预算裁决,注入 LLM
4. LLM 生成回复 → 情绪分析 → 立绘切换 → 语音合成(可选)
5. 回复写入 L0 记忆 + 更新情绪状态 + 记录决策日志

**主动表达流程**：
1. 主动关怀调度器每 5 分钟检查:
   - 用户离开检测(30 分钟无互动)
   - 工作压力检测(屏幕内容: bug/error/deadline)
   - 日程提醒(calendar 事件)
   - 心事匣候选(14 天回顾窗口)
2. 触发条件满足 → 候选生成 → gate 检查(窗口/睡眠/模式/冷却/每日上限)
3. 通过 gate → ContextOrchestrator 编排 → LLM 生成 → 主动发送
4. 记录决策日志(触发原因/评分/gate 结果)

### 2.3 架构示意图

```
用户界面
  ↓ 输入(文本/语音/点击)
交互层 → backchannel(微表情) → 用户界面
  ↓ 完整输入
┌─────────────────────────────────────┐
│ ContextOrchestrator (智能调度层)    │
│  ┌─────────────────────────────┐   │
│  │ 优先级裁决                  │   │
│  │  Urgent (100)  ┐            │   │
│  │  Active (80)   ├─→ 预算分配 │   │
│  │  Reactive (60) │            │   │
│  │  Background(20)┘            │   │
│  └─────────────────────────────┘   │
│         ↓                           │
│  Context (2000 tokens)             │
└─────────────────────────────────────┘
  ↓
LLM (云端 API / Ollama 本地)
  ↓ 回复
情绪分析 + 立绘切换 + 语音合成
  ↓
记忆写入(L0) + 决策日志
```

### 2.4 模式设计

| 维度 | 陪伴模式 (Companion) | 工作模式 (Work) |
|------|---------------------|-----------------|
| **目标** | 日常陪伴/情感支持 | 任务辅助/知识工作 |
| **会话摘要** | session-continuation.json | work-session-continuation.json |
| **主动表达** | 开启(心事匣/日程提醒) | 关闭(避免打扰) |
| **记忆召回** | 优先情感记忆 | 优先工作相关记忆 |
| **立绘表现** | 丰富表情变化 | 专注状态(减少动画) |
| **语音** | TTS 输出开启 | TTS 可选关闭 |
| **工作文件** | 不记录 | 记录到 work-files/ |

**模式切换逻辑**：
- 自动识别：屏幕内容包含 IDE/文档/终端 → 建议工作模式
- 手动覆盖：用户点击模式切换按钮
- 持久化：当前模式存储到 `mode_state.json`

### 2.5 部署形态

| 进程/模块 | 职责 | 技术形态 | 常驻 |
|-----------|------|----------|------|
| cether.exe | 桌面主进程,Tauri 窗口 | Rust + Tauri 2.x | 是 |
| Python 后端 | 认知核心/记忆/情绪/LLM 路由 | Python 3.11+ subprocess | 是 |
| SQLite | 记忆索引/FTS5 全文检索 | 嵌入式数据库 | 否(按需加载) |
| Ollama (可选) | 本地模型推理 | 独立服务(HTTP API) | 可选 |
| Web UI | 前端界面(应用模式) | dist/index.html (Vanilla JS) | 否(Tauri WebView) |

### 2.6 技术选型总表

| 能力 | 首选 | 备选 | 取舍理由 |
|------|------|------|----------|
| 桌面框架 | Tauri 2.x | Electron | Tauri 更轻量(2MB vs 200MB),资源占用低 |
| 前端框架 | Vanilla JS | React + TypeScript | 当前轻量级,V4.0 可考虑迁移 React |
| 后端语言 | Python | Rust | Python 生态丰富(NLP/ML),开发效率高 |
| 记忆存储 | JSONL + SQLite | PostgreSQL | 纯文件易备份,FTS5 支持全文检索 |
| 语音识别 | Whisper.cpp | Azure STT | 本地优先,保护隐私 |
| 语音合成 | Edge TTS | VITS 本地克隆 | Edge TTS 免费且质量高,VITS 可选 |
| 本地模型 | Ollama | llama.cpp | Ollama API 兼容 OpenAI,易集成 |
| Embedding | BAAI/bge-m3 | OpenAI text-embedding-3 | 本地 1024 维,多语言支持好 |
| 立绘渲染 | 静态 PNG | Live2D Cubism | PNG 轻量,Live2D 可选升级 |
| 天气 API | Open-Meteo | OpenWeatherMap | Open-Meteo 免费且无需 API key |

---

## 3 层面一：上下文编排与智能调度

### 3.1 功能构成

| 模块 | 功能要点 | 实现方式 |
|------|----------|----------|
| ContextOrchestrator | 多源上下文优先级裁决、动态预算分配 | 四级优先级队列 + 预算分配算法 |
| 主动关怀调度 | 周期性观察、多触发器、gate 检查 | asyncio 定时任务 + 触发器工厂模式 |
| 决策日志 | 记录所有主动行为、可解释 AI | decision_log.jsonl (append-only) |
| backchannel | 用户输入时实时微表情反馈 | 前端分块监听 + 后端情绪快速分析 |

### 3.2 ContextOrchestrator 设计

**核心思想**：多个上下文源(记忆/主动表达/环境状态/系统通知)竞争有限的 token 预算,需要智能裁决优先级并动态分配预算,避免低优先级内容挤占高优先级内容。

**四级优先级队列**：

| 优先级 | 典型内容 | 预算上限 | 说明 |
|--------|----------|----------|------|
| Urgent (100) | 系统警告、紧急提醒、用户明确指令 | 30% | 优先满足,不可被挤占 |
| Active (80) | 主动表达候选、心事匣项 | 40% | 主动能力核心,次优先 |
| Reactive (60) | 相关记忆、对话历史、会话摘要 | 50% | 响应式内容,标准优先级 |
| Background (20) | 天气、时间、屏幕状态 | 10% | 环境信息,可压缩 |

**预算分配算法**：
1. 收集各源候选内容及其优先级
2. Urgent 优先满足,最多占 30% 预算
3. 剩余预算按优先级加权分配: Active 40% / Reactive 50% / Background 10%
4. 每个源内部按重要度/相关性排序,裁剪到预算内
5. 组装最终 Context,总 token 数不超过预算

**代码结构**：
```python
# src/cether/context_orchestrator.py
class ContextOrchestrator:
    def __init__(self):
        self.sources = {
            "urgent": UrgentSourceManager(),
            "active": ActiveExpressionManager(),
            "reactive": MemoryRetrievalManager(),
            "background": EnvironmentManager()
        }
    
    def orchestrate(self, user_message, total_budget=2000):
        # 1. 收集各源候选
        urgent_candidates = self.sources["urgent"].get_candidates()
        active_candidates = self.sources["active"].get_candidates()
        reactive_candidates = self.sources["reactive"].retrieve(user_message)
        background_candidates = self.sources["background"].get_state()
        
        # 2. 紧急源优先满足
        urgent_tokens = min(sum(len(c) for c in urgent_candidates), total_budget * 0.3)
        remaining = total_budget - urgent_tokens
        
        # 3. 动态预算分配
        context = {
            "urgent": self._select_top(urgent_candidates, urgent_tokens),
            "active": self._select_top(active_candidates, remaining * 0.4),
            "reactive": self._select_top(reactive_candidates, remaining * 0.5),
            "background": self._select_top(background_candidates, remaining * 0.1)
        }
        
        return context
```

### 3.3 主动关怀调度器

**触发器类型**：

| 触发器 | 检测条件 | 典型行为 | 冷却时间 |
|--------|----------|----------|----------|
| IdleTrigger | 30 分钟无互动 | "好久没见到你了,在忙什么呢?" | 3600s |
| StressTrigger | 屏幕内容: bug/error/deadline | "看起来遇到困难了,需要帮助吗?" | 7200s |
| CalendarTrigger | 日程提醒时间到 | "记得 15 分钟后有会议哦" | 无(按日程) |
| MindBoxTrigger | 心事匣 14 天回顾 | "你之前提到的[心事],现在怎么样了?" | 86400s |
| WeatherTrigger | 极端天气(雨天/高温) | "今天下雨了,记得带伞~" | 43200s |

**gate 检查机制**：每个候选在发送前必须通过所有 gate:

| gate | 检查内容 | 失败处理 |
|------|----------|----------|
| window | 用户当前是否活跃(非离开/睡眠) | 延后到下次检查 |
| sleep | 角色是否清醒(睡眠时不打扰) | 延后到下次检查 |
| mode | 当前模式是否允许主动表达 | 跳过此候选 |
| cooldown | 距上次主动表达是否超过冷却时间 | 延后到冷却结束 |
| daily_cap | 今日主动表达次数是否未达上限 | 延后到明天 |

**调度循环**：
```python
# src/cether/active_care.py
class ActiveCareScheduler:
    async def run(self):
        while True:
            await asyncio.sleep(300)  # 每 5 分钟检查
            
            for trigger in self.care_triggers:
                if trigger.should_fire(self.runtime.context):
                    candidate = trigger.generate_candidate()
                    
                    # gate 检查
                    gate_result = self._check_gates(candidate)
                    if not gate_result.passed:
                        self._log_decision("gate_failed", candidate, gate_result)
                        continue
                    
                    # 通过 gate,发送主动表达
                    await self.runtime.emit_active_expression(candidate)
                    self._log_decision("emitted", candidate, gate_result)
                    break  # 每次只触发一个
```

### 3.4 决策日志

**日志结构**：
```json
{
  "timestamp": "2026-11-08T17:30:00+08:00",
  "type": "active_expression",
  "trigger": {
    "source": "mind_box",
    "item_id": "mb_20261108_003",
    "importance": 0.78,
    "age_hours": 12.5,
    "text": "用户今天没提到周末计划"
  },
  "decision": {
    "action": "emit_candidate",
    "gate_checks": {
      "window": {"passed": true, "reason": "用户活跃"},
      "sleep": {"passed": true, "reason": "清醒"},
      "mode": {"passed": true, "reason": "陪伴模式"},
      "cooldown": {"passed": true, "reason": "距上次 3200s"},
      "daily_cap": {"passed": true, "reason": "今日 1/3"}
    },
    "score": 0.85,
    "reason": "心事匣重要度高 + 时间窗口合适 + 日常互动关联"
  }
}
```

**UI 展示**：状态面板添加"决策日志"标签,时间线视图,点击展开详情。

### 3.5 backchannel 快速接话

**前端监听**：
```javascript
// dist/index.html
let inputBuffer = "";
$('#userInput').addEventListener('input', (e) => {
  inputBuffer = e.target.value;
  
  // 每输入 15 个字符触发一次
  if (inputBuffer.length > 0 && inputBuffer.length % 15 === 0) {
    runtimeAction('backchannel', { text: inputBuffer });
  }
});
```

**后端快速分析**：
```python
# src/cether/backchannel.py
class BackchannelEngine:
    def process_chunk(self, text_chunk):
        sentiment = self._fast_sentiment(text_chunk)  # 规则 + 关键词,<100ms
        
        if sentiment > 0.5:
            return {"micro_expression": "smile", "duration": 0.8}
        elif sentiment < -0.5:
            return {"micro_expression": "concerned", "duration": 0.8}
        else:
            return {"micro_expression": "listening", "duration": 0.8}
```

**微表情切换**：
```javascript
function handleBackchannel(response) {
  updatePortrait(response.micro_expression, active.name);
  setTimeout(() => {
    updatePortrait(status?.expression || 'neutral', active.name);
  }, 800);
}
```

---

## 4 层面二：情绪与认知系统

### 4.1 设计思路

情绪系统采用 **PAD 三维模型** + **7 种离散情绪状态**的混合方案。PAD 模型提供连续的情绪空间,便于情绪演化计算;7 种离散状态用于立绘表情映射和用户可读展示。

| 机制/模型 | 工程对应 | 数据形态 |
|-----------|----------|----------|
| PAD 三维模型 | emotion_pad: {pleasure, arousal, dominance} | 浮点数 [-1, 1] |
| 7 种情绪状态 | emotion: joy/sadness/anger/fear/surprise/disgust/neutral | 枚举字符串 |
| 情绪衰减 | 每个 tick 向基准值回归(衰减系数 0.05) | 线性插值 |
| 事件驱动 | 用户输入/LLM 回复/屏幕内容 → 情绪偏移 | 增量更新 |

### 4.2 PAD 模型

**三个维度**：
- **Pleasure (愉悦度)**: [-1, 1],负值为不愉快,正值为愉快
- **Arousal (唤起度)**: [-1, 1],负值为平静,正值为兴奋
- **Dominance (控制感)**: [-1, 1],负值为被动,正值为主动

**PAD → 7 种情绪映射**：
```python
def pad_to_emotion(p, a, d):
    if p > 0.3 and a > 0.2:
        return "joy" if d > 0 else "surprise"
    elif p < -0.3:
        return "sadness" if a < 0 else "anger"
    elif a < -0.3:
        return "disgust"
    elif abs(p) < 0.2 and abs(a) < 0.2:
        return "neutral"
    else:
        return "fear"
```

**情绪衰减公式**：
```
P_new = P_current * 0.95 + P_baseline * 0.05
A_new = A_current * 0.95 + A_baseline * 0.05
D_new = D_current * 0.95 + D_baseline * 0.05
```

每个 tick(约 5 秒),情绪向基准值回归 5%,模拟情绪的自然衰减。

### 4.3 情绪处理管线

| 步骤 | 处理 | 执行位置 | 耗时/预算 |
|------|------|----------|-----------|
| 1 | 事件触发(用户输入/回复/屏幕) | Python 后端 | <10ms |
| 2 | 情绪分析(关键词 + LLM 可选) | Python 后端 | <200ms |
| 3 | PAD 增量计算 | Python 后端 | <5ms |
| 4 | PAD → 离散情绪映射 | Python 后端 | <1ms |
| 5 | 立绘表情切换 | 前端 | <50ms |
| 6 | 情绪状态持久化 | Python 后端 | <10ms |

### 4.4 情绪 → 立绘表情映射

| 情绪 | PAD 区间 | 立绘表情 | 颜色(情绪环) |
|------|----------|----------|--------------|
| joy | P>0.3, A>0.2, D>0 | smile / happy | #8ed1ae (绿色) |
| sadness | P<-0.3, A<0 | sad / cry | #93c9ff (蓝色) |
| anger | P<-0.3, A>0 | angry / annoyed | #eb9e8f (红色) |
| fear | A<-0.2, D<0 | scared / worried | #b8a4d5 (紫色) |
| surprise | P>0.3, A>0.2, D<0 | surprised / shocked | #e4b878 (暖黄色) |
| disgust | A<-0.3 | disgusted / displeased | #9eb89a (灰绿色) |
| neutral | \|P\|<0.2, \|A\|<0.2 | neutral / calm | #8fa49a (灰色) |

**表情文件命名规范**：
```
roles/{role_name}/portraits/
  neutral.png
  smile.png
  happy.png
  sad.png
  cry.png
  angry.png
  annoyed.png
  scared.png
  worried.png
  surprised.png
  shocked.png
  disgusted.png
  displeased.png
```

---

## 5 层面三：记忆系统

### 5.1 分层设计

| 层级 | 内容 | 容量 | 读写策略 |
|------|------|------|----------|
| L0 | 原始对话记录/事件 | 无限(append-only) | 仅追加,不修改 |
| L1 | 摘要记忆/关键事件 | 约 1000 条 | 定期巩固生成,可覆盖 |
| 冷库 | 归档记忆(UTC 月分片) | 无限(JSONL 文件) | 按需检索恢复 |
| 心事匣 | 用户心事/困扰 | 约 50 条 | 用户明确标记,可删除 |

**数据流向**：
```
用户对话 → L0 (立即写入)
      ↓ (每 100 条或每天)
    L1 巩固 (摘要生成)
      ↓ (30 天后或超容量)
    冷库归档 (JSONL 分片)
      ↓ (主动召回或检索)
    恢复到 L1
```

### 5.2 L0 原始记忆

**存储位置**：`{data_dir}/memory/L0/{role_name}/events.jsonl`

**数据模型**：
```json
{
  "id": "l0_20261108_173000_abc123",
  "timestamp": "2026-11-08T17:30:00+08:00",
  "type": "conversation",
  "role": "user",
  "content": "今天天气真好",
  "emotion_pad": {"pleasure": 0.5, "arousal": 0.2, "dominance": 0.3},
  "mode": "companion"
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 唯一标识,包含时间戳 |
| timestamp | ISO 8601 | 事件发生时间 |
| type | enum | conversation / tool_call / active_expression / screen_observe |
| role | enum | user / assistant / system |
| content | string | 文本内容 |
| emotion_pad | object | 当时的 PAD 情绪状态 |
| mode | enum | companion / work |

### 5.3 L1 摘要记忆

**生成时机**：
- L0 积累 100 条新记录
- 或距上次巩固超过 24 小时

**生成方式**：
1. 提取 L0 最近 100 条记录
2. LLM 生成摘要(Prompt: "总结以下对话的关键信息、情感变化和重要事件")
3. 写入 L1,包含反向索引(指向 L0 原始记录 ID)

**数据模型**：
```json
{
  "id": "l1_20261108_summary_001",
  "timestamp": "2026-11-08T18:00:00+08:00",
  "summary": "用户分享了今天的天气,心情愉快。后来讨论了周末计划,决定去公园。",
  "importance": 0.7,
  "source_ids": ["l0_20261108_173000_abc123", "l0_20261108_173500_def456"],
  "tags": ["天气", "周末计划", "公园"]
}
```

### 5.4 混合检索管线

**V3.0 核心升级**：BM25 + Embedding + PPR + MMR 四阶段混合检索

1. **BM25 关键词检索**(SQLite FTS5)
   - 输入：用户 query
   - 输出：top 20 候选(按 BM25 分数排序)

2. **Embedding 语义检索**(BAAI/bge-m3)
   - 输入：用户 query
   - 输出：top 20 候选(按余弦相似度排序)

3. **RRF 融合**(Reciprocal Rank Fusion)
   - 合并 BM25 + Embedding 结果
   - 公式: `score(d) = sum(1/(k + rank_i(d)))`,k=60
   - 输出：top 30 候选(按 RRF 分数排序)

4. **PPR 图扩散**(Personalized PageRank)
   - 基于共现关系构建记忆图(节点=记忆,边=共现次数)
   - 从 top 30 候选出发,执行 2-hop PPR
   - 输出：top 50 候选(包含间接关联记忆)

5. **MMR 去重**(Maximal Marginal Relevance)
   - 平衡相关性和多样性
   - 公式: `MMR(d) = λ * sim(d, query) - (1-λ) * max_sim(d, selected)`,λ=0.7
   - 输出：top 10 最终结果

### 5.5 检索预算分配

**ContextOrchestrator 中的记忆预算**：

| 组成 | 预算/权重 | 说明 |
|------|-----------|------|
| 用户最新输入 | 15% | 固定保留 |
| 系统提示词 | 10% | 角色设定 + 指令 |
| 会话续接摘要 | 20% | session-continuation.json |
| 检索记忆 | 30% | 本节描述的混合检索结果 |
| 近期对话 | 15% | 最近 5 轮对话 |
| 主动表达/环境 | 10% | 主动候选 + 天气等 |

### 5.6 冷库归档机制

**归档条件**：
- L0 记录距今超过 30 天
- 或 L0 总量超过 10000 条

**归档流程**：
1. 按 UTC 月分片: `cold/{role_name}/2026-11.jsonl`
2. 建立索引: `cold/{role_name}/index.json` 记录每条记录的 ID 和分片名
3. 原始 L0 记录保持不变(仅标记为 cold)
4. 冷态记录不参与主动检索,需明确召回

**恢复流程**：
- 用户点击"冷库"面板 → 分页浏览
- 点击某条记录 → 查询 index.json 找到分片 → 加载完整内容
- 可选：恢复到 L1(重新加权)

---

## 6 层面四：感知与输入

### 6.1 屏幕感知

**采集方式**：

| 信号/条件 | 采集/触发方式 | 判读/行为 |
|-----------|---------------|----------|
| 用户活跃 | 定时截图(每 60s) | 哈希检测 → 无变化跳过 |
| 屏幕内容 | 截图 → GPT-4V/Claude Vision | 提取活动类型/关键内容/情绪 |
| 工作压力 | 关键词检测(bug/error/deadline) | 触发 StressTrigger |
| 模式建议 | 检测 IDE/文档/终端 | 建议切换工作模式 |

**哈希检测优化**：
```python
# src/cether/screen_sense.py
import imagehash
from PIL import Image

class ScreenSensor:
    def __init__(self):
        self.last_hash = None
    
    async def capture_and_analyze(self):
        screenshot = await tauri.screenshot()
        current_hash = imagehash.average_hash(Image.open(screenshot))
        
        # 哈希相同,跳过 API 调用
        if current_hash == self.last_hash:
            return None
        
        self.last_hash = current_hash
        
        # 多模态理解
        result = await vision_api.analyze(screenshot, 
            prompt="用户正在做什么?关键内容?情绪状态?")
        
        return {
            "activity": result.activity,
            "content": result.content,
            "emotion": result.emotion,
            "timestamp": datetime.now()
        }
```

**隐私保护**：
- 截图加密存储,仅保留最近 10 张
- 用户可随时关闭屏幕感知
- 敏感区域遮罩(密码输入/银行页面,基于窗口标题检测)

### 6.2 语音输入(ASR)

**技术选型**：

| 环节 | 方案 | 说明 |
|------|------|------|
| 录音 | Tauri 麦克风 API | 采样率 16kHz,单声道 |
| VAD | WebRTC VAD | 语音活动检测,过滤静音 |
| ASR | Whisper.cpp (本地) | tiny/base/small 模型可选 |
| 备选 | Azure STT / Edge STT | 云端备选,准确率更高 |

**流程**：
1. 用户按住"语音"按钮 → 开始录音
2. 实时 VAD 检测,静音 > 1s 自动停止
3. 音频发送到 Whisper.cpp → 转文字
4. 文字注入输入框,触发 backchannel

### 6.3 环境感知

**天气 API(Open-Meteo)**：
```python
# src/cether/weather.py
async def get_current_weather(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,weather_code,is_day"
    }
    response = await httpx.get(url, params=params)
    return response.json()["current"]
```

**天气影响情绪**：
```python
# 雨天降低 pleasure
if weather["weather_code"] in [51, 53, 55, 61, 63, 65]:  # 雨
    emotion_modifier["pleasure"] = -0.1
# 高温降低 arousal
if weather["temperature_2m"] > 35:
    emotion_modifier["arousal"] = -0.15
```

---

## 7 层面五：表达与输出

### 7.1 立绘渲染

**V2.1 现状**：静态 PNG,淡入淡出切换(0.4s)

**V3.0 升级路径**：
- 短期(V3.0)：保持静态 PNG,优化加载性能
- 中期(V3.5)：集成 dsh-live2d-avatar,支持 Live2D 模型
- 长期(V4.0)：WebP 帧动画 + Live2D 双模式

**表情切换逻辑**：
```javascript
// dist/index.html
function updatePortrait(expression, roleName) {
  const path = `roles/${roleName}/portraits/${expression}.png`;
  const img = new Image();
  img.src = path;
  img.onload = () => {
    // 淡出当前
    const current = $('.portrait img.active');
    if (current) current.classList.remove('active');
    // 淡入新表情
    img.classList.add('active');
    $('.portrait').appendChild(img);
  };
  img.onerror = () => {
    console.warn(`表情文件缺失: ${path}`);
    // 回退到 neutral
    if (expression !== 'neutral') {
      updatePortrait('neutral', roleName);
    }
  };
}
```

### 7.2 语音合成(TTS)

**技术选型**：

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| Edge TTS | 免费,质量高,无需 API key | 需联网,声音不可定制 | 默认方案 |
| VITS 本地克隆 | 完全本地,可定制音色 | 需训练数据,模型文件大 | 高级用户 |
| Azure TTS | 质量最高,多音色 | 需 API key,按量付费 | 商业场景 |

**集成 Edge TTS**：
```python
# src/cether/voice.py
import edge_tts

async def synthesize_edge_tts(text, voice="zh-CN-XiaoxiaoNeural"):
    communicate = edge_tts.Communicate(text, voice)
    audio_file = f"temp_tts_{uuid.uuid4()}.mp3"
    await communicate.save(audio_file)
    return audio_file
```

**角色专属音色**：
```yaml
# roles/{role_name}/config.yaml
voice:
  provider: edge_tts
  voice_id: zh-CN-XiaoxiaoNeural  # 或 VITS 模型路径
  rate: "+0%"    # 语速
  pitch: "+0Hz"  # 音调
```

### 7.3 表达生成

**生成方式**：

| 场景 | 生成方式 | 示例 |
|------|----------|------|
| 正常对话 | LLM 生成 | "今天天气真好呀~要不要出去走走?" |
| 主动提醒 | 模板 + 变量 | "记得{时间}有{事件}哦" |
| backchannel | 规则映射 | "嗯" / "啊?" / "哦..." |
| 情绪反馈 | 情绪词库 | "😊" / "😟" / "🤔" |

---

## 8 层面六：主动能力与调度

### 8.1 主动表达触发器

**触发器工厂**：
```python
# src/cether/active_care.py
class TriggerFactory:
    @staticmethod
    def create(trigger_type, config):
        if trigger_type == "idle":
            return IdleTrigger(threshold=config["threshold"])
        elif trigger_type == "stress":
            return StressTrigger(keywords=config["keywords"])
        elif trigger_type == "calendar":
            return CalendarTrigger(events=config["events"])
        elif trigger_type == "mind_box":
            return MindBoxTrigger(lookback_days=config["lookback_days"])
        elif trigger_type == "weather":
            return WeatherTrigger(conditions=config["conditions"])
```

**每个触发器实现两个方法**：
1. `should_fire(context) -> bool`：判断是否应该触发
2. `generate_candidate() -> dict`：生成候选主动表达

### 8.2 调度策略

**调度频率**：

| 触发条件 | 行为 | 频率上限 |
|----------|------|----------|
| 用户离开 30min | 主动问候 | 2 次/天 |
| 工作压力检测 | 安慰/建议 | 3 次/天 |
| 日程提醒 | 提前提醒 | 按日程 |
| 心事匣候选 | 回访关心 | 3 次/天 |
| 天气变化 | 提醒/关心 | 1 次/天 |

**gate 优先级**：
1. window gate: 用户离开/睡眠时不打扰
2. sleep gate: 角色睡眠时不主动
3. mode gate: 工作模式关闭主动表达
4. cooldown gate: 全局冷却 1800s(30 分钟)
5. daily_cap gate: 每日上限 3 次

---

## 9 层面七：角色与多模态

### 9.1 角色包结构

**标准目录**：
```
roles/{role_name}/
  config.yaml           # 角色配置
  character.yaml        # 角色卡(性格/背景/口癖)
  portraits/            # 立绘(7+ 表情)
    neutral.png
    smile.png
    sad.png
    angry.png
    ...
  voice/                # 语音参考(可选)
    sample_01.wav
  gpt_sovits/           # VITS 权重(可选)
    sovits_model.pth
    gpt_model.ckpt
```

**config.yaml 示例**：
```yaml
name: Sakura
display_name: 樱
gender: female
age: 16
personality:
  - 活泼
  - 善解人意
  - 略带天然呆
catchphrase:
  - "嗯嗯~"
  - "诶?"
  - "那个..."
voice:
  provider: edge_tts
  voice_id: zh-CN-XiaoxiaoNeural
emotion_baseline:
  pleasure: 0.3
  arousal: 0.2
  dominance: 0.1
```

### 9.2 角色切换

**切换流程**：
1. 保存当前角色状态(emotion_pad / L0 offset / mode)
2. 加载新角色配置
3. 恢复新角色上次状态(如果有)
4. 通知前端更新立绘/名称
5. 清空当前会话(可选,用户确认)

**数据隔离**：
- 每个角色独立的 L0/L1/冷库
- 共享的 world.jsonl(跨角色事件,如工具调用结果)
- 角色切换不丢失记忆

### 9.3 多模态集成路径

**V3.0 范围**：
- ✅ 文本对话
- ✅ 静态立绘
- ✅ 语音输入(Whisper.cpp)
- ✅ 语音输出(Edge TTS)
- ✅ 屏幕感知(GPT-4V/Claude Vision)

**V3.5+ 扩展**：
- 🔲 Live2D 立绘
- 🔲 本地视觉理解(LLaVA)
- 🔲 摄像头情绪识别
- 🔲 手势识别

---

## 10 成本与性能优化

### 10.1 成本构成

**月度预估(200 turns/day)**：

| 项目 | 计费/消耗方式 | 占比 | 优化空间 |
|------|---------------|------|----------|
| 对话生成 | DeepSeek V4.1 Flash ¥1/M tokens | 40% | 本地模型替代 |
| 情绪分析 | 规则 + 关键词(免费) | 0% | 已优化 |
| 记忆检索 | BM25(免费) + Embedding(本地) | 0% | 已优化 |
| 屏幕感知 | GPT-4V ¥10/M tokens | 35% | 哈希检测减少 60% 调用 |
| 语音识别 | Whisper.cpp(本地) | 0% | 已优化 |
| 语音合成 | Edge TTS(免费) | 0% | 已优化 |
| 记忆巩固 | DeepSeek ¥1/M tokens | 15% | 每 100 条执行 1 次 |
| 主动表达 | DeepSeek ¥1/M tokens | 10% | 每日上限 3 次 |

**总计**：¥75-160/月(取决于屏幕感知使用频率)

### 10.2 路由与降级策略

**LLM 路由**：

| 任务 | 执行位置 | 判据 | 失败回退 |
|------|----------|------|----------|
| 对话生成 | 云端 API 优先 | 用户配置 | 本地模型(Ollama) |
| backchannel | 规则(本地) | 固定 | 无需回退 |
| 屏幕感知 | GPT-4V 云端 | 哈希变化 | 跳过分析 |
| 记忆巩固 | 云端 API | 积累 100 条 | 延后到下次 |
| Embedding | 本地(bge-m3) | 固定 | 无需回退 |

**降级策略**：
1. 云端 API 失败 → 尝试本地模型(Ollama)
2. 本地模型失败 → 规则模板生成
3. 规则失败 → 返回"抱歉,我需要休息一下"

### 10.3 Token 优化

**Context 预算管理**：
- 总预算 2000 tokens(约 1500 汉字)
- ContextOrchestrator 动态分配,避免浪费
- 会话摘要自动退出,避免无限增长

**Prompt 优化**：
- 角色设定精简到 200 tokens
- 记忆注入采用摘要而非原文
- 情绪状态用数值而非文字描述

---

## 11 硬件与资源方案

### 11.1 最低要求与推荐配置

| 硬件/资源 | 最低要求 | 推荐配置 | 说明 |
|-----------|----------|----------|------|
| CPU | x64 双核 2.0GHz | x64 四核 3.0GHz+ | Whisper.cpp 需多核加速 |
| 内存 | 4GB | 8GB+ | 本地模型需 6GB+ |
| 硬盘 | 2GB 可用空间 | 10GB+ SSD | 记忆文件 + 本地模型 |
| GPU | 无(可选) | NVIDIA RTX 3060+ | 本地模型推理加速 |
| 网络 | 1Mbps | 10Mbps+ | 云端 API 调用 |
| 操作系统 | Windows 10 / macOS 11 / Ubuntu 20.04 | Windows 11 / macOS 14 / Ubuntu 22.04 | Tauri 2.x 兼容性 |

**本地模型配置**：
- 7B 模型(Qwen2.5-7B-Instruct)：6GB RAM(CPU) / 8GB VRAM(GPU)
- 14B 模型：12GB RAM / 16GB VRAM
- 推荐 GPU：RTX 3060 12GB / RTX 4060 Ti 16GB

### 11.2 存储占用预估

**按角色划分**：

| 数据类型 | 容量(90 天) | 增长速率 |
|----------|-------------|----------|
| L0 记忆 | ~50MB | 0.5MB/天 |
| L1 摘要 | ~5MB | 0.05MB/天 |
| 冷库归档 | ~200MB | 2MB/月 |
| 立绘资源 | 10-50MB | 固定(按角色包) |
| 决策日志 | ~10MB | 0.1MB/天 |
| 配置文件 | <1MB | 固定 |

**总计**：约 300MB/角色/90 天

---

## 12 维护与运维

### 12.1 进程守护

**Tauri 自动重启**：
- cether.exe 崩溃 → 自动重启(最多 3 次)
- Python 后端崩溃 → 自动重启子进程

**日志监控**：
- `logs/cether.log`：主进程日志
- `logs/python_backend.log`：Python 后端日志
- `logs/decision_log.jsonl`：决策日志

### 12.2 日志与可观测

| 日志类型 | 内容 | 保留 |
|----------|------|------|
| 应用日志 | 启动/关闭/错误/警告 | 30 天 |
| Python 后端日志 | LLM 调用/记忆操作/情绪变化 | 30 天 |
| 决策日志 | 主动表达/gate 检查/评分 | 90 天 |
| 屏幕感知日志 | 截图哈希/分析结果 | 7 天 |

**日志轮转**：超过保留期限自动删除旧日志

### 12.3 备份与恢复

**备份策略**：
- 自动备份：每周一次,压缩到 `backups/`
- 手动备份：用户点击"导出数据"
- 备份内容：L0/L1/冷库/配置/角色包

**恢复流程**：
1. 选择备份文件(.zip)
2. 解压到临时目录
3. 验证完整性(检查必需文件)
4. 覆盖当前数据(用户确认)
5. 重启应用

### 12.4 安全与隐私

**本地优先**：
- 所有记忆文件本地存储,不上传云端
- 屏幕截图临时存储,定期清理
- API key 加密存储(Windows DPAPI / macOS Keychain)

**权限最小化**：
- 屏幕感知需用户授权
- 麦克风/扬声器需用户授权
- 文件访问限制在数据目录内

### 12.5 常见故障

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 应用启动失败 | Python 环境缺失 | 检查 `CETHER_PYTHON` 环境变量 |
| UTF-8 错误 | Windows GBK 编码 | 已修复(V2.1),升级到最新版 |
| 记忆检索慢 | SQLite 索引缺失 | 运行 `REINDEX` 命令 |
| 语音识别失败 | Whisper 模型缺失 | 下载 tiny/base 模型到 `models/` |
| 屏幕感知无响应 | API key 无效 | 检查 settings 中的 Vision API 配置 |

---

## 13 迭代路线

| 阶段 | 周期 | 核心内容 | 验收标准 |
|------|------|----------|----------|
| **V3.0** | 3 周 | ContextOrchestrator + backchannel + 屏幕感知 + 语音交互 + 决策透明 + 本地模型 + 桌宠模式 | 记忆召回准确率 ≥85%,backchannel 延迟 ≤500ms,屏幕感知哈希准确率 ≥95% |
| **V3.5** | 4 周 | Live2D 立绘 + 本地视觉理解(LLaVA) + 插件市场 + World Info 系统 | Live2D 表情切换流畅,本地视觉准确率 ≥70%,插件安装成功率 100% |
| **V4.0** | 6 周 | 前端迁移 React + TypeScript + 移动端适配 + 云端同步(可选) + 多用户支持 | 前端构建时间 <10s,移动端适配 iOS/Android,云端同步延迟 <1s |
| **V5.0** | 8 周 | 情绪留疤 + 睡眠巩固 + 空间记忆宫殿 + 摄像头情绪识别 + 手势识别 | 情绪留疤影响可观测,睡眠巩固规则验证,摄像头情绪识别准确率 ≥80% |

---

## 14 风险与对策

| 风险 | 影响 | 对策 |
|------|------|------|
| **LLM API 成本超支** | 月度成本超预算 | 1. 本地模型替代<br>2. 用户自定义预算上限<br>3. 智能缓存(相似 query 复用结果) |
| **屏幕感知隐私争议** | 用户不信任 | 1. 截图本地加密存储<br>2. 用户可随时关闭<br>3. 敏感区域自动遮罩 |
| **Tauri 框架升级破坏兼容性** | 应用无法启动 | 1. 锁定 Tauri 2.x 版本<br>2. 定期测试新版本<br>3. 提供回退方案 |
| **本地模型性能不足** | 推理速度 >10s | 1. 推荐用户使用云端 API<br>2. 提供模型压缩版本(量化)<br>3. GPU 加速提示 |
| **记忆文件损坏** | 数据丢失 | 1. append-only 日志不可篡改<br>2. 自动备份(每周)<br>3. 文件完整性校验 |
| **backchannel 延迟过高** | 体验下降 | 1. 规则优先(无 LLM 调用)<br>2. 关键词快速匹配<br>3. 用户可关闭 backchannel |
| **多语言支持不足** | 国际化受限 | 1. i18n 框架集成<br>2. 社区翻译贡献<br>3. LLM 自动翻译 |

---

## 附录 A：技术选型清单

| 类别 | 组件 | 版本/形态 | 用途 |
|------|------|-----------|------|
| **桌面框架** | Tauri | 2.x | 跨平台桌面应用 |
| **前端** | Vanilla JS | ES6+ | 轻量级 UI(V3.0) |
| **后端语言** | Python | 3.11+ | 认知核心/记忆/情绪 |
| **存储** | SQLite | 3.40+ | FTS5 全文检索 + 索引 |
| **存储** | JSONL | append-only | L0/L1 记忆 + 决策日志 |
| **LLM(云端)** | DeepSeek V4.1 Flash | API | 对话生成/摘要 |
| **LLM(云端)** | Claude 3.5 Sonnet | API | 备选 |
| **LLM(本地)** | Ollama | 最新版 | 本地模型推理 |
| **Embedding** | BAAI/bge-m3 | 1024 维 | 本地语义检索 |
| **BM25** | SQLite FTS5 | 内置 | 关键词检索 |
| **图扩散** | NetworkX | 3.x | PPR 算法 |
| **ASR** | Whisper.cpp | tiny/base/small | 本地语音识别 |
| **TTS** | Edge TTS | 免费 | 语音合成 |
| **TTS(可选)** | VITS | 本地克隆 | 定制音色 |
| **Vision** | GPT-4V / Claude Vision | API | 屏幕感知 |
| **天气** | Open-Meteo | 免费 | 天气数据 |
| **立绘** | 静态 PNG | - | 表情渲染(V3.0) |
| **立绘(可选)** | Live2D Cubism | SDK | 动态表情(V3.5+) |

---

## 附录 B：参数配置表

### B.1 ContextOrchestrator 参数

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| total_budget | 2000 | 1000-4000 | 总 token 预算 |
| urgent_ratio | 0.3 | 0.2-0.5 | Urgent 源最大占比 |
| active_ratio | 0.4 | 0.2-0.6 | Active 源权重 |
| reactive_ratio | 0.5 | 0.3-0.7 | Reactive 源权重 |
| background_ratio | 0.1 | 0.05-0.2 | Background 源权重 |

### B.2 主动表达参数

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| check_interval | 300 | 60-600 | 调度检查间隔(秒) |
| idle_threshold | 1800 | 600-7200 | 离开检测阈值(秒) |
| global_cooldown | 1800 | 600-3600 | 全局冷却时间(秒) |
| daily_cap | 3 | 1-10 | 每日主动表达上限 |
| lookback_days | 14 | 7-30 | 心事匣回顾窗口(天) |

### B.3 情绪系统参数

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| decay_rate | 0.05 | 0.01-0.1 | 情绪衰减系数 |
| pad_neutral_threshold | 0.2 | 0.1-0.3 | Neutral 判定阈值 |
| emotion_update_interval | 5 | 1-10 | 情绪更新间隔(秒) |

### B.4 记忆系统参数

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| l0_consolidation_threshold | 100 | 50-200 | L1 巩固触发条件(条) |
| l0_archive_days | 30 | 14-90 | 冷库归档天数 |
| retrieval_top_k | 10 | 5-20 | 最终检索结果数 |
| bm25_weight | 0.5 | 0.3-0.7 | BM25 权重(vs Embedding) |
| mmr_lambda | 0.7 | 0.5-0.9 | MMR 相关性权重 |

### B.5 屏幕感知参数

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| capture_interval | 60 | 30-300 | 截图间隔(秒) |
| hash_similarity_threshold | 0.95 | 0.9-1.0 | 哈希相似度阈值 |
| screenshot_retention | 10 | 5-20 | 截图保留数量 |

---

**文档版本历史**：
- V3.0 (2026-11-08)：初始版本,完整技术方案
- 后续版本记录在此处追加

---

**参与贡献**：
- 技术讨论：GitHub Issues
- 代码贡献：提交 Pull Request
- 文档更新：直接编辑本文档并提交 PR

**许可证**：MIT License

---

*本文档基于 CetherYH V2.1 现状,参考 Sakura、Lararium、MnemoCore、HippoRAG、graph-memory、dsh-ikaros-pet、agent-terrarium、Jan、SillyTavern、N.E.K.O.、WindowPet 等优秀开源项目设计理念编写。*
