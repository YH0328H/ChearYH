# CetherYH 项目架构原则

## 一、参数管理原则（全局约束）

### 1. 参数预设化
所有涉及参数的地方（系数、阈值、权重、时间常数等）一律采用合理的预设值，**不因调参停滞进度**。预设值基于：
- 心理学理论（PSI、SDT、Panksepp等）
- 经验推荐值（如 BM25 的 k1=1.5, b=0.75）
- 简单合理假设（如衰减 τ=7天）

### 2. 逻辑与配置解耦
所有核心参数必须与业务逻辑解耦：
- ❌ **错误**：`if emotion > 0.7: ...`（硬编码阈值）
- ✅ **正确**：`if emotion > config.emotion_high_threshold: ...`（从配置读取）

参数来源优先级：
1. 角色卡配置文件（优先级最高）
2. 全局配置文件（默认值）
3. 代码内 fallback 常量（最后兜底）

### 3. 未来可动态调试
系统必须具备未来在 UI 界面进行动态配置与热更新的能力：
- 配置文件采用易读格式（TOML/JSON）
- 配置变更后无需重启（热加载）
- UI 界面可实时调整参数并观察效果
- 提供配置导出/导入功能

## 二、实现指南

### 配置文件结构示例
```toml
[state]
inertial_filter_alpha = 0.7  # 惯性滤波系数，越大变化越慢
emotion_high_threshold = 0.7  # 高情绪阈值
salience_high_threshold = 0.7  # 高显著性阈值

[memory]
ebbinghaus_tau_days = 7  # 艾宾浩斯衰减时间常数（天）
weibull_k = 0.8  # Weibull 衰减形状参数
surprise_window_size = 10  # 惊讶度计算的历史窗口大小

[retrieval]
bm25_k1 = 1.5  # BM25 词频饱和参数
bm25_b = 0.75  # BM25 长度归一化参数
rrf_k = 60  # RRF 融合参数
vector_top_k = 10  # 向量检索召回数量
graph_max_hops = 1  # 图扩散最大跳数

[checkpoint]
impulse_threshold = 0.5  # 检查点脉冲阈值
hesitation_probability = 0.3  # 犹豫概率
```

### 代码模式
```python
@dataclass
class StateConfig:
    """状态演化配置，所有参数可从 TOML 加载"""
    inertial_filter_alpha: float = 0.7
    emotion_high_threshold: float = 0.7
    salience_high_threshold: float = 0.7

def load_state_config(path: Path) -> StateConfig:
    """从配置文件加载，缺失项使用默认值"""
    if not path.exists():
        return StateConfig()  # 全部使用默认值
    raw = tomllib.loads(path.read_text())["state"]
    return StateConfig(
        inertial_filter_alpha=raw.get("inertial_filter_alpha", 0.7),
        emotion_high_threshold=raw.get("emotion_high_threshold", 0.7),
        salience_high_threshold=raw.get("salience_high_threshold", 0.7),
    )

# 使用时
config = load_state_config(Path("config/state.toml"))
new_value = inertial_filter(current, target, alpha=config.inertial_filter_alpha)
```

### 热加载模式
```python
class ConfigWatcher:
    """监控配置文件变化，自动重新加载"""
    def __init__(self, path: Path):
        self._path = path
        self._mtime = path.stat().st_mtime if path.exists() else 0
        self._config = load_state_config(path)

    def get_config(self) -> StateConfig:
        """返回最新配置，文件变化时自动重新加载"""
        if self._path.exists():
            mtime = self._path.stat().st_mtime
            if mtime > self._mtime:
                self._config = load_state_config(self._path)
                self._mtime = mtime
        return self._config
```

## 三、验收标准

所有新增功能必须满足：
1. ✅ 参数有合理预设值，代码可直接运行
2. ✅ 参数可从配置文件加载
3. ✅ 配置文件不存在时使用默认值
4. ✅ 配置变更后可热加载（不需要重启）
5. ✅ 参数含义在配置文件中有注释
6. ✅ 单元测试覆盖默认值和自定义值两种情况

## 四、现有代码的对齐计划

当前已实现的模块需要逐步对齐此原则：
- [ ] 检索模块（BM25、向量、图扩散）的参数提取到配置
- [ ] 状态模块（惯性滤波α、四意愿映射权重）的参数提取到配置
- [ ] 触发检测（情绪阈值、显著性阈值、重复窗口）的参数提取到配置
- [ ] 候选池（容量、TTL）的参数提取到配置
- [ ] 感知模块（哈希阈值、采样间隔）的参数提取到配置

新模块（第二批及以后）**必须从一开始就按此原则实现**。
