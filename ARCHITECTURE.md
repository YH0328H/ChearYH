# CetherYH 项目架构设计

**版本**: V3.0 (设计阶段) | V2.1 (当前实现)  
**更新时间**: 2026-11-08

---

## 目录

1. [一、参数管理原则](#一参数管理原则全局约束)
2. [二、V3.0 核心架构](#二v30-核心架构)
3. [三、智能调度层设计](#三智能调度层设计)
4. [四、实现指南](#四实现指南)
5. [五、验收标准](#五验收标准)
6. [六、现有代码对齐计划](#六现有代码对齐计划)

---

## 一、参数管理原则(全局约束)

### 1. 参数预设化
所有涉及参数的地方(系数、阈值、权重、时间常数等)一律采用合理的预设值,**不因调参停滞进度**。预设值基于:
- 心理学理论(PSI、SDT、Panksepp等)
- 经验推荐值(如 BM25 的 k1=1.5, b=0.75)
- 简单合理假设(如衰减 τ=7天)

### 2. 逻辑与配置解耦
所有核心参数必须与业务逻辑解耦:
- ❌ **错误**: `if emotion > 0.7: ...`(硬编码阈值)
- ✅ **正确**: `if emotion > config.emotion_high_threshold: ...`(从配置读取)

参数来源优先级:
1. 角色卡配置文件(优先级最高)
2. 全局配置文件(默认值)
3. 代码内 fallback 常量(最后兜底)

### 3. 未来可动态调试
系统必须具备未来在 UI 界面进行动态配置与热更新的能力:
- 配置文件采用易读格式(TOML/JSON)
- 配置变更后无需重启(热加载)
- UI 界面可实时调整参数并观察效果
- 提供配置导出/导入功能

---

## 二、V3.0 核心架构

### 2.1 分层结构

CetherYH V3.0 采用经典的**五层架构 + 独立的智能调度层**:

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

**关键设计亮点**:
1. **智能调度层独立**: ContextOrchestrator 统一管理所有上下文源,避免各模块直接竞争 token 预算
2. **感知层解耦**: 屏幕/语音/环境感知独立采集,通过事件通知调度层
3. **决策透明化**: 所有主动行为经过调度层,自动记录决策日志

### 2.2 核心数据流

**典型对话流程**:
```
用户输入 → backchannel 微表情(<500ms)
         ↓
ContextOrchestrator 编排上下文
  - Urgent (100): 系统警告/提醒
  - Active (80): 主动表达候选
  - Reactive (60): 相关记忆
  - Background (20): 天气/时间/屏幕
         ↓
按优先级 + 预算裁决,注入 LLM
         ↓
回复 → 情绪分析 → 立绘切换 → 语音合成
         ↓
L0 记忆 + 决策日志
```

**主动表达流程**:
```
主动关怀调度器(每 5 分钟)
  - IdleTrigger: 离开 30min
  - StressTrigger: 屏幕检测压力
  - CalendarTrigger: 日程提醒
  - MindBoxTrigger: 心事匣回顾
  - WeatherTrigger: 天气变化
         ↓
候选生成 + gate 检查
  ✓ window: 用户活跃
  ✓ sleep: 角色清醒
  ✓ mode: 允许主动
  ✓ cooldown: 超过 1800s
  ✓ daily_cap: 未达 3 次
         ↓
ContextOrchestrator 编排 → LLM → 发送
         ↓
决策日志(trigger/score/gate/reason)
```

### 2.3 模式设计

| 维度 | 陪伴模式 | 工作模式 |
|------|----------|----------|
| **目标** | 日常陪伴/情感支持 | 任务辅助/知识工作 |
| **会话摘要** | session-continuation.json | work-session-continuation.json |
| **主动表达** | ✅ 开启 | ❌ 关闭(避免打扰) |
| **记忆召回** | 优先情感记忆 | 优先工作记忆 |
| **立绘** | 丰富表情变化 | 专注状态 |
| **语音** | TTS 开启 | TTS 可选关闭 |
| **工作文件** | 不记录 | 记录到 work-files/ |

---

## 三、智能调度层设计

### 3.1 ContextOrchestrator — 上下文编排器

**核心思想**: 多个上下文源竞争有限的 token 预算,需要智能裁决优先级并动态分配。

#### 3.1.1 四级优先级队列

| 优先级 | 典型内容 | 预算上限 | 说明 |
|--------|----------|----------|------|
| Urgent (100) | 系统警告、紧急提醒、用户明确指令 | 30% | 优先满足,不可被挤占 |
| Active (80) | 主动表达候选、心事匣项 | 40% | 主动能力核心,次优先 |
| Reactive (60) | 相关记忆、对话历史、会话摘要 | 50% | 响应式内容,标准优先级 |
| Background (20) | 天气、时间、屏幕状态 | 10% | 环境信息,可压缩 |

#### 3.1.2 预算分配算法

```python
# src/cether/context_orchestrator.py
class ContextOrchestrator:
    def orchestrate(self, user_message, total_budget=2000):
        # 1. 收集各源候选
        urgent = self.sources["urgent"].get_candidates()
        active = self.sources["active"].get_candidates()
        reactive = self.sources["reactive"].retrieve(user_message)
        background = self.sources["background"].get_state()
        
        # 2. Urgent 优先满足(最多 30%)
        urgent_tokens = min(sum(len(c) for c in urgent), total_budget * 0.3)
        remaining = total_budget - urgent_tokens
        
        # 3. 动态预算分配
        context = {
            "urgent": self._select_top(urgent, urgent_tokens),
            "active": self._select_top(active, remaining * 0.4),
            "reactive": self._select_top(reactive, remaining * 0.5),
            "background": self._select_top(background, remaining * 0.1)
        }
        
        return context
```

**配置参数**(`config/context_orchestrator.toml`):
```toml
[orchestrator]
total_budget = 2000           # 总 token 预算
urgent_ratio = 0.3            # Urgent 源最大占比
active_ratio = 0.4            # Active 源权重
reactive_ratio = 0.5          # Reactive 源权重
background_ratio = 0.1        # Background 源权重
```

### 3.2 backchannel — 快速接话机制

**核心思想**: 用户输入时实时显示微表情反馈,无需等待完整回复(延迟 <500ms)。

#### 3.2.1 前端监听
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

#### 3.2.2 后端快速分析
```python
# src/cether/backchannel.py
class BackchannelEngine:
    def process_chunk(self, text_chunk):
        # 规则 + 关键词,<100ms
        sentiment = self._fast_sentiment(text_chunk)
        
        if sentiment > 0.5:
            return {"micro_expression": "smile", "duration": 0.8}
        elif sentiment < -0.5:
            return {"micro_expression": "concerned", "duration": 0.8}
        else:
            return {"micro_expression": "listening", "duration": 0.8}
```

**配置参数**(`config/backchannel.toml`):
```toml
[backchannel]
chunk_size = 15               # 触发字符数
sentiment_positive = 0.5      # 正面情绪阈值
sentiment_negative = -0.5     # 负面情绪阈值
expression_duration = 0.8     # 微表情持续时间(秒)
```

### 3.3 主动关怀调度器

**核心思想**: 周期性观察(每 5 分钟),多触发器,gate 检查,主动发起对话。

#### 3.3.1 五种触发器

| 触发器 | 检测条件 | 典型行为 | 冷却时间 |
|--------|----------|----------|----------|
| IdleTrigger | 30 分钟无互动 | "好久没见到你了" | 3600s |
| StressTrigger | 屏幕: bug/error/deadline | "看起来遇到困难了" | 7200s |
| CalendarTrigger | 日程提醒时间到 | "记得 15 分钟后有会议" | 无 |
| MindBoxTrigger | 心事匣 14 天回顾 | "之前提到的[心事]" | 86400s |
| WeatherTrigger | 极端天气 | "今天下雨了,记得带伞" | 43200s |

#### 3.3.2 gate 检查机制

| gate | 检查内容 | 失败处理 |
|------|----------|----------|
| window | 用户当前是否活跃 | 延后到下次检查 |
| sleep | 角色是否清醒 | 延后到下次检查 |
| mode | 当前模式是否允许主动 | 跳过此候选 |
| cooldown | 距上次主动是否超过冷却 | 延后到冷却结束 |
| daily_cap | 今日次数是否未达上限 | 延后到明天 |

#### 3.3.3 调度循环
```python
# src/cether/active_care.py
class ActiveCareScheduler:
    async def run(self):
        while True:
            await asyncio.sleep(300)  # 每 5 分钟
            
            for trigger in self.care_triggers:
                if trigger.should_fire(self.runtime.context):
                    candidate = trigger.generate_candidate()
                    
                    # gate 检查
                    gate_result = self._check_gates(candidate)
                    if not gate_result.passed:
                        self._log_decision("gate_failed", candidate, gate_result)
                        continue
                    
                    # 发送主动表达
                    await self.runtime.emit_active_expression(candidate)
                    self._log_decision("emitted", candidate, gate_result)
                    break  # 每次只触发一个
```

**配置参数**(`config/active_expression.toml`):
```toml
[scheduler]
check_interval = 300          # 调度间隔(秒)
global_cooldown = 1800        # 全局冷却(秒)
daily_cap = 3                 # 每日上限

[triggers.idle]
threshold = 1800              # 离开检测(秒)
cooldown = 3600               # 冷却时间(秒)

[triggers.stress]
keywords = ["bug", "error", "deadline", "崩溃", "报错"]
cooldown = 7200

[triggers.mind_box]
lookback_days = 14            # 回顾窗口(天)
min_importance = 0.65         # 最低重要度
cooldown = 86400
```

### 3.4 决策日志

**核心思想**: 记录所有主动行为的触发原因、评分依据、gate 检查结果,实现可解释 AI。

#### 3.4.1 日志结构
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
    "reason": "心事匣重要度高 + 时间窗口合适"
  }
}
```

**存储**: `{data_dir}/decision_log.jsonl`(append-only)

**UI 展示**: 状态面板添加"决策日志"标签,时间线视图,点击展开详情。

---

## 四、实现指南

### 4.1 配置文件结构

每个模块的配置文件统一放在 `config/` 目录:

```
config/
├── context_orchestrator.toml    # 上下文编排
├── backchannel.toml             # 快速接话
├── active_expression.toml       # 主动表达
├── emotion.toml                 # 情绪系统
├── memory.toml                  # 记忆系统
├── screen_sense.toml            # 屏幕感知
└── api_providers.md             # API 配置
```

### 4.2 代码模式

#### 4.2.1 配置加载
```python
from dataclasses import dataclass
from pathlib import Path
import tomllib

@dataclass
class OrchestratorConfig:
    """上下文编排配置"""
    total_budget: int = 2000
    urgent_ratio: float = 0.3
    active_ratio: float = 0.4
    reactive_ratio: float = 0.5
    background_ratio: float = 0.1

def load_orchestrator_config(path: Path) -> OrchestratorConfig:
    """从配置文件加载,缺失项使用默认值"""
    if not path.exists():
        return OrchestratorConfig()
    
    raw = tomllib.loads(path.read_text())["orchestrator"]
    return OrchestratorConfig(
        total_budget=raw.get("total_budget", 2000),
        urgent_ratio=raw.get("urgent_ratio", 0.3),
        active_ratio=raw.get("active_ratio", 0.4),
        reactive_ratio=raw.get("reactive_ratio", 0.5),
        background_ratio=raw.get("background_ratio", 0.1),
    )

# 使用时
config = load_orchestrator_config(Path("config/context_orchestrator.toml"))
context = orchestrator.orchestrate(message, total_budget=config.total_budget)
```

#### 4.2.2 热加载
```python
class ConfigWatcher:
    """监控配置文件变化,自动重新加载"""
    def __init__(self, path: Path, loader_func):
        self._path = path
        self._loader = loader_func
        self._mtime = path.stat().st_mtime if path.exists() else 0
        self._config = loader_func(path)
    
    def get_config(self):
        """返回最新配置,文件变化时自动重新加载"""
        if self._path.exists():
            mtime = self._path.stat().st_mtime
            if mtime > self._mtime:
                self._config = self._loader(self._path)
                self._mtime = mtime
        return self._config
```

### 4.3 完整示例

```python
# src/cether/context_orchestrator.py
from pathlib import Path
from typing import Dict, List

class ContextOrchestrator:
    def __init__(self, config_path: Path):
        self.config_watcher = ConfigWatcher(
            config_path,
            load_orchestrator_config
        )
        self.sources = {
            "urgent": UrgentSourceManager(),
            "active": ActiveExpressionManager(),
            "reactive": MemoryRetrievalManager(),
            "background": EnvironmentManager()
        }
    
    def orchestrate(self, user_message: str) -> Dict[str, List[str]]:
        config = self.config_watcher.get_config()
        
        # 1. 收集各源候选
        urgent_candidates = self.sources["urgent"].get_candidates()
        active_candidates = self.sources["active"].get_candidates()
        reactive_candidates = self.sources["reactive"].retrieve(user_message)
        background_candidates = self.sources["background"].get_state()
        
        # 2. Urgent 优先满足
        urgent_tokens = min(
            sum(len(c) for c in urgent_candidates),
            config.total_budget * config.urgent_ratio
        )
        remaining = config.total_budget - urgent_tokens
        
        # 3. 动态预算分配
        context = {
            "urgent": self._select_top(urgent_candidates, urgent_tokens),
            "active": self._select_top(active_candidates, remaining * config.active_ratio),
            "reactive": self._select_top(reactive_candidates, remaining * config.reactive_ratio),
            "background": self._select_top(background_candidates, remaining * config.background_ratio)
        }
        
        return context
    
    def _select_top(self, candidates: List[str], budget: float) -> List[str]:
        """按预算选择 top 候选"""
        selected = []
        total_tokens = 0
        for candidate in candidates:
            tokens = len(candidate)
            if total_tokens + tokens <= budget:
                selected.append(candidate)
                total_tokens += tokens
            else:
                break
        return selected
```

---

## 五、验收标准

所有新增功能必须满足:

### V2.1 标准(已实现)
1. ✅ 参数有合理预设值,代码可直接运行
2. ✅ 参数可从配置文件加载
3. ✅ 配置文件不存在时使用默认值
4. ✅ 参数含义在配置文件中有注释
5. ✅ 单元测试覆盖默认值和自定义值

### V3.0 新增标准
6. ✅ 配置变更后可热加载(不需要重启)
7. ✅ ContextOrchestrator 四级优先级正确裁决
8. ✅ backchannel 响应延迟 ≤500ms
9. ✅ 主动表达 gate 检查完整覆盖
10. ✅ 决策日志完整记录所有主动行为
11. ✅ 记忆召回准确率 ≥85%
12. ✅ 屏幕感知哈希准确率 ≥95%

---

## 六、现有代码对齐计划

### 6.1 V2.1 已实现模块(需对齐)

- [ ] 检索模块(BM25、向量、图扩散)的参数提取到 `config/memory.toml`
- [ ] 状态模块(惯性滤波α、四意愿映射权重)的参数提取到 `config/emotion.toml`
- [ ] 触发检测(情绪阈值、显著性阈值、重复窗口)的参数提取到 `config/active_expression.toml`
- [ ] 候选池(容量、TTL)的参数提取到 `config/active_expression.toml`
- [ ] 感知模块(哈希阈值、采样间隔)的参数提取到 `config/screen_sense.toml`

### 6.2 V3.0 新增模块(必须从一开始按原则实现)

- [ ] ContextOrchestrator 实现(3 天)
  - `src/cether/context_orchestrator.py`
  - `config/context_orchestrator.toml`
  - 单元测试 `tests/test_context_orchestrator.py`

- [ ] backchannel 快速接话(2 天)
  - `src/cether/backchannel.py`
  - `config/backchannel.toml`
  - 前端集成 `dist/index.html`
  - 延迟测试 `tests/test_backchannel.py`

- [ ] 主动关怀调度器(1 天)
  - `src/cether/active_care.py`
  - 5 个触发器 `src/cether/triggers/`
  - gate 检查机制
  - 调度循环与决策日志

- [ ] 决策透明化(1 天)
  - 决策日志 JSONL 写入
  - UI 展示 `dist/index.html`
  - 日志查询 API

- [ ] 记忆检索升级(0.5 天)
  - BM25 + Embedding + PPR + MMR 混合检索
  - `config/memory.toml` 参数配置
  - 准确率测试 `tests/test_retrieval.py`

- [ ] 屏幕感知(1 天)
  - `src/cether/screen_sense.py`
  - 哈希检测优化
  - `config/screen_sense.toml`

- [ ] 语音交互(1.5 天)
  - ASR: Whisper.cpp 集成
  - TTS: Edge TTS / VITS
  - `config/voice.toml`

- [ ] 天气现实锚点(1 天)
  - Open-Meteo API 集成
  - 天气影响情绪
  - `config/weather.toml`

### 6.3 优先级排序

**Week 1 — P0 核心架构**:
1. ContextOrchestrator (Day 1-3)
2. backchannel (Day 4-5)
3. 决策透明化 (Day 6)
4. 记忆检索升级 (Day 6)
5. 会话管理后端 (Day 7)

**Week 2 — P1 体验提升**:
1. 屏幕感知 (Day 8)
2. 语音交互 (Day 9-10)
3. 主动关怀调度 (Day 11)
4. 桌宠模式 (Day 11)
5. 天气现实锚点 (Day 12)

**Week 3 — P2 锦上添花**:
1. Live2D 立绘 (Day 13)
2. Ollama 本地模型 (Day 14-15)
3. 全量测试 (Day 16-17)
4. 文档更新 (Day 18)

---

## 七、五行平衡架构(V3.0 核心)

### 7.1 五行模块映射

基于传统五行哲学的认知架构设计:

| 五行 | 认知子系统 | 核心模块 | 李雅普诺夫特性 |
|------|-----------|---------|--------------|
| 木 Wood | 生长探索 | `wuxing_core.py` (好奇心驱力) | λ > 0 (扩张) |
| 火 Fire | 表达社交 | `bagua_emotion.py` (八卦情绪) | λ ≈ 0 (临界) |
| 土 Earth | 稳定安全 | 纯文件存储 + 本地优先 | λ < 0 (收敛) |
| 金 Metal | 掌控能力 | `taiji_decision.py` (太极决策) | λ ≈ 0 (临界) |
| 水 Water | 联结共情 | `yijing_memory.py` (易经记忆) | λ < 0 (收敛) |

### 7.2 阴阳平衡与临界态

**核心原理**: 系统保持在李雅普诺夫临界态(λ ≈ 0),既有创造性又不失稳定性。

**阴阳计算**:
```python
def compute_yin_yang_balance(drives: Dict[str, float]) -> Tuple[float, float]:
    """计算阴阳平衡度"""
    # 阳: 木(好奇) + 火(表达)
    yang = drives["wood"] + drives["fire"]
    
    # 阴: 土(安全) + 水(联结)
    yin = drives["earth"] + drives["water"]
    
    # 金(掌控)是中性
    neutral = drives["metal"]
    
    return yin + neutral * 0.5, yang + neutral * 0.5
```

**临界态维持**:
- λ_max > 0.1 → 阳过盛(混沌) → 增强阴性驱力(土、水)
- λ_max < -0.1 → 阴过盛(僵化) → 增强阳性驱力(木、火)
- -0.1 ≤ λ_max ≤ 0.1 → 已平衡(临界态) → 保持现状

### 7.3 五行相生相克

**相生(促进)**:
- 木生火: 好奇心驱动表达欲望
- 火生土: 情绪表达建立安全感
- 土生金: 稳定基础促进能力掌控
- 金生水: 自主能力深化人际联结
- 水生木: 深度联结激发新的好奇心

**相克(制约)**:
- 木克土: 过度探索破坏安全感
- 火克金: 强烈情绪干扰理性掌控
- 土克水: 过度保守限制人际联结
- 金克木: 执着掌控抑制好奇心
- 水克火: 深度共情淡化自我表达

**配置文件**:
```toml
# config/wuxing_balance.toml

[sheng_coefficients]  # 相生系数
wood_to_fire = 0.3
fire_to_earth = 0.25
earth_to_metal = 0.2
metal_to_water = 0.25
water_to_wood = 0.3

[ke_coefficients]  # 相克系数
wood_to_earth = -0.15
fire_to_metal = -0.2
earth_to_water = -0.15
metal_to_wood = -0.2
water_to_fire = -0.25
```

### 7.4 八卦情绪系统

将 PAD 三维情绪空间映射到八卦:

| 八卦 | 情绪原型 | PAD 区间 | 五行属性 |
|------|---------|---------|---------|
| 乾 ☰ | 自信掌控 | P>0.5, A>0.5, D>0.5 | 金 |
| 坤 ☷ | 平静接纳 | P<-0.5, A<-0.5, D<-0.5 | 土 |
| 震 ☳ | 兴奋激动 | P>0.3, A>0.5, D<0 | 木 |
| 巽 ☴ | 温柔共情 | P>0, A<0, D<0 | 水 |
| 坎 ☵ | 忧虑恐惧 | P<0, A<0, D<0 | 水 |
| 离 ☲ | 热情表达 | P>0.5, A>0.5, D<0 | 火 |
| 艮 ☶ | 沉稳克制 | P<0, A<-0.5, D>0 | 土 |
| 兑 ☱ | 愉悦社交 | P>0.5, A>0, D<0 | 火 |

### 7.5 易经六十四卦记忆编码

**Hexbit 算法对应易经六十四卦**:
- 6 个二值维度 = 6 个爻(阴爻/阳爻)
- 2^6 = 64 种编码 = 64 卦

**六爻映射**:
1. 初爻: valence_positive (情绪效价)
2. 二爻: high_salience (显著性)
3. 三爻: high_emotion (情绪强度)
4. 四爻: relation_event (关系事件)
5. 五爻: self_initiated (自我发起)
6. 上爻: flash_weight (闪光灯记忆)

**递减惩罚的易经解释**:
- 连续相同卦象 → "物极必反",需要变化
- 惩罚系数 0.85 → 每次重复衰减 15%
- 鼓励记忆多样性 = 保持临界态

---

## 参考资料

### 理论基础
- [易经](https://zh.wikipedia.org/wiki/易经) — 阴阳五行哲学
- [黄帝内经](https://zh.wikipedia.org/wiki/黄帝内经) — 天地人三才
- [Lyapunov Spectrum (Clark 2026)](https://arxiv.org/abs/2610.12426) — 临界态动力学
- [PSI (Joscha Bach 2009)](http://www.cognitive-ai.com/) — 驱力认知架构
- [The Synthetic Mind (Ferrer 2026)](https://github.com/joshferrer1/the-synthetic-library) — 赫尔驱力理论

### 开源项目
- [CetherYH V3.0 完整技术方案](CetherYH_V3.0_DESIGN.md)
- [五行认知哲学](docs/WUXING_PHILOSOPHY.md)
- [Sakura Desktop Pet](https://github.com/Rvosy/Sakura) — ContextOrchestrator 架构参考
- [Lararium](https://github.com/lararium-app/lararium) — 纯文件记忆设计
- [graph-memory](https://github.com/Doodle-Lin/graph-memory) — 混合检索栈

---

**版本历史**:
- V3.0 (2026-11-08): 添加五行平衡架构设计 + 智能调度层
- V2.1 (2026-11-06): 初始版本,参数管理原则

---

**许可证**: MIT License
