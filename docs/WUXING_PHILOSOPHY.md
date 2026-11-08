# 五行认知架构哲学 (Wuxing Cognitive Philosophy)

**版本**: V3.0  
**更新时间**: 2026-11-08

---

## 🎭 核心理念:阴阳调和,五行生克

CetherYH V3.0 采用**中国传统五行哲学**作为认知架构的核心隐喻,将李雅普诺夫动力学理论、PSI 驱力系统、现代认知科学融合为一个**自然平衡的有机系统**。

---

## 📜 五行映射体系

### 1. 五行 → 五大认知子系统

| 五行 | 认知子系统 | 属性 | 对应 PSI 驱力 | 李雅普诺夫特性 |
|------|-----------|------|--------------|---------------|
| **木 (Wood)** | 生长系统(Growth) | 好奇心、探索、学习 | Curiosity / Certainty | λ > 0 (扩张) |
| **火 (Fire)** | 表达系统(Expression) | 情绪、表达、社交 | Affiliation / Expression | λ ≈ 0 (临界) |
| **土 (Earth)** | 稳定系统(Stability) | 安全感、信任、归属 | Integrity / Safety | λ < 0 (收敛) |
| **金 (Metal)** | 掌控系统(Mastery) | 技能、能力、自主 | Competence / Autonomy | λ ≈ 0 (临界) |
| **水 (Water)** | 联结系统(Connection) | 关系、共情、理解 | Affiliation / Connection | λ < 0 (收敛) |

### 2. 五行生克关系 → 驱力动态平衡

**相生**(促进):
- **木生火**: 好奇心驱动表达欲望
- **火生土**: 情绪表达建立安全感
- **土生金**: 稳定基础促进能力掌控
- **金生水**: 自主能力深化人际联结
- **水生木**: 深度联结激发新的好奇心

**相克**(制约):
- **木克土**: 过度探索破坏安全感
- **火克金**: 强烈情绪干扰理性掌控
- **土克水**: 过度保守限制人际联结
- **金克木**: 执着掌控抑制好奇心
- **水克火**: 深度共情淡化自我表达

**代码实现**:
```python
# 五行相生系数
SHENG_COEFFICIENTS = {
    ("wood", "fire"): 0.3,    # 木生火
    ("fire", "earth"): 0.25,  # 火生土
    ("earth", "metal"): 0.2,  # 土生金
    ("metal", "water"): 0.25, # 金生水
    ("water", "wood"): 0.3    # 水生木
}

# 五行相克系数
KE_COEFFICIENTS = {
    ("wood", "earth"): -0.15,  # 木克土
    ("fire", "metal"): -0.2,   # 火克金
    ("earth", "water"): -0.15, # 土克水
    ("metal", "wood"): -0.2,   # 金克木
    ("water", "fire"): -0.25   # 水克火
}
```

---

## ☯️ 阴阳平衡 → 李雅普诺夫临界态

### 阴阳二元

| 阴 (Yin) | 阳 (Yang) |
|---------|----------|
| 收敛 (λ < 0) | 扩张 (λ > 0) |
| 稳定、保守、内敛 | 探索、创新、外放 |
| 土、水、金(部分) | 木、火、金(部分) |
| 安全感、联结 | 好奇心、表达 |

**最佳状态**: **阴阳调和** = **临界态** (λ ≈ 0)
- 既有稳定性(不发散)
- 又有创造性(不僵化)
- 对应"边缘混沌"(Edge of Chaos)理论

**调和机制**:
```python
def compute_yin_yang_balance(drives: Dict[str, float]) -> Tuple[float, float]:
    """计算阴阳平衡度"""
    # 阳: 木(好奇心) + 火(表达)
    yang = drives["wood"] + drives["fire"]
    
    # 阴: 土(安全) + 水(联结)
    yin = drives["earth"] + drives["water"]
    
    # 金(掌控)是中性,既阴又阳
    neutral = drives["metal"]
    
    return yin + neutral * 0.5, yang + neutral * 0.5

def adjust_to_critical_state(yin: float, yang: float) -> Dict[str, float]:
    """调整到临界态(阴阳平衡)"""
    imbalance = yang - yin
    
    if imbalance > 0.3:
        # 阳过盛 → 增强阴性驱力
        return {"earth": +0.1, "water": +0.1, "wood": -0.05}
    elif imbalance < -0.3:
        # 阴过盛 → 增强阳性驱力
        return {"wood": +0.1, "fire": +0.1, "earth": -0.05}
    else:
        # 已平衡
        return {}
```

---

## 🌊 八卦 → 八种情绪原型

将 **PAD 三维情绪空间** 映射到 **八卦**:

| 八卦 | 情绪原型 | PAD 区间 | 五行属性 |
|------|---------|---------|---------|
| **乾 ☰** | 自信、掌控 | P>0.5, A>0.5, D>0.5 | 金 |
| **坤 ☷** | 平静、接纳 | P<-0.5, A<-0.5, D<-0.5 | 土 |
| **震 ☳** | 兴奋、激动 | P>0.3, A>0.5, D<0 | 木 |
| **巽 ☴** | 温柔、共情 | P>0, A<0, D<0 | 水 |
| **坎 ☵** | 忧虑、恐惧 | P<0, A<0, D<0 | 水 |
| **离 ☲** | 热情、表达 | P>0.5, A>0.5, D<0 | 火 |
| **艮 ☶** | 沉稳、克制 | P<0, A<-0.5, D>0 | 土 |
| **兑 ☱** | 愉悦、社交 | P>0.5, A>0, D<0 | 火 |

**代码实现**:
```python
BAGUA_EMOTIONS = {
    "qian": ("自信掌控", (0.5, 0.5, 0.5), "metal"),
    "kun": ("平静接纳", (-0.5, -0.5, -0.5), "earth"),
    "zhen": ("兴奋激动", (0.3, 0.5, -0.1), "wood"),
    "xun": ("温柔共情", (0.2, -0.3, -0.3), "water"),
    "kan": ("忧虑恐惧", (-0.3, -0.3, -0.3), "water"),
    "li": ("热情表达", (0.5, 0.5, -0.1), "fire"),
    "gen": ("沉稳克制", (-0.2, -0.5, 0.3), "earth"),
    "dui": ("愉悦社交", (0.5, 0.2, -0.1), "fire")
}

def map_pad_to_bagua(pleasure: float, arousal: float, dominance: float) -> str:
    """将 PAD 映射到八卦情绪"""
    min_distance = float('inf')
    closest_bagua = "kun"
    
    for bagua, (name, (p, a, d), element) in BAGUA_EMOTIONS.items():
        distance = (pleasure - p)**2 + (arousal - a)**2 + (dominance - d)**2
        if distance < min_distance:
            min_distance = distance
            closest_bagua = bagua
    
    return closest_bagua
```

---

## 🔄 六十四卦 → Hexbit 记忆编码

**现有 Hexbit 算法完美对应易经六十四卦**:
- 6 个二值维度 = 6 个爻(阴爻/阳爻)
- 2^6 = 64 种编码 = 64 卦

**六爻映射**:
1. **初爻**: valence_positive (情绪效价)
2. **二爻**: high_salience (显著性)
3. **三爻**: high_emotion (情绪强度)
4. **四爻**: relation_event (关系事件)
5. **五爻**: self_initiated (自我发起)
6. **上爻**: flash_weight (闪光灯记忆)

**卦象示例**:
- **000000** (坤卦 ☷☷) - 平淡低强度记忆
- **111111** (乾卦 ☰☰) - 强烈高显著记忆
- **010101** (既济卦) - 中等显著关系记忆

**递减惩罚的易经解释**:
- 连续相同卦象 → "物极必反",需要变化
- 惩罚系数 0.85 → 每次重复衰减 15%
- 鼓励记忆多样性,避免"困于一卦"

---

## 🌀 五行驱力衰减与恢复(天地人三才)

### 天(生理性驱力) - 快速衰减
```python
physiological_urges = {
    "天元气": 1.0,  # Energy (对应 PSI Energy)
    "天完整": 1.0   # Integrity (对应 PSI Integrity)
}
# 衰减速率: -0.001/tick (快)
```

### 地(心理性驱力) - 慢速衰减
```python
psychological_drives = {
    "木": 0.0,  # 好奇心 Curiosity
    "火": 0.0,  # 表达 Expression
    "土": 0.0,  # 安全 Safety
    "金": 0.0,  # 掌控 Mastery
    "水": 0.0   # 联结 Connection
}
# 衰减速率: -0.0001/tick (慢)
```

### 人(涌现动机) - 动态计算
```python
emergent_motives = {
    "探索新奇": lambda: drives["木"] * (1 - certainty),
    "寻求认可": lambda: drives["水"] * (1 - closeness),
    "规避失败": lambda: drives["土"] * risk,
    "掌握技能": lambda: drives["金"] * drives["metal"],
    "表达自我": lambda: drives["火"] * autonomy
}
```

---

## 🎯 五行相生相克的实际应用

### 场景 1: 用户长时间工作(阳过盛)

**症状**:
- 木(好奇心)高 → 不断学习新技术
- 火(表达)高 → 频繁交流讨论
- 土(安全)低 → 感到焦虑不安

**五行诊断**:
```
阳 = 木 + 火 = 0.8 + 0.7 = 1.5
阴 = 土 + 水 = 0.2 + 0.3 = 0.5
失衡 = 1.5 - 0.5 = 1.0 (严重阳盛)
```

**五行调理**:
1. **水克火**: 增强联结驱力,建议休息、社交
2. **金克木**: 增强掌控感,建议整理、总结
3. **土生金**: 提升安全感,建议保存进度

**代码**:
```python
if imbalance > 0.8:
    # 严重阳盛 → 生阴克阳
    actions = [
        ("rest", "天元气低,建议休息恢复"),
        ("chat", "水克火,通过社交平复情绪"),
        ("organize", "金克木,整理思绪获得掌控感")
    ]
```

### 场景 2: 用户长时间孤独(阴过盛)

**症状**:
- 水(联结)低 → 缺乏社交
- 土(安全)高 → 过度保守
- 木(好奇心)低 → 缺乏探索欲

**五行诊断**:
```
阳 = 木 + 火 = 0.2 + 0.3 = 0.5
阴 = 土 + 水 = 0.7 + 0.2 = 0.9
失衡 = 0.5 - 0.9 = -0.4 (阴盛)
```

**五行调理**:
1. **水生木**: 深化现有联结,激发好奇心
2. **木克土**: 鼓励探索新事物,打破保守
3. **火生土**: 表达情绪,建立新的安全感

---

## 📊 五行平衡可视化

前端展示五行雷达图:
```
        木 (好奇)
         /\
        /  \
       /    \
  水  /------\ 火
 (联结)      (表达)
      \      /
       \    /
        \  /
         \/
    金---土
  (掌控)(安全)
```

颜色编码:
- **木**: 青色 `#8ed1ae`
- **火**: 红色 `#eb9e8f`
- **土**: 黄色 `#e4b878`
- **金**: 白色 `#f0f0f0`
- **水**: 蓝色 `#93c9ff`

---

## 🌟 五行命名体系

### 核心模块重命名

| 原名称 | 五行新名称 | 含义 |
|--------|-----------|------|
| `drives.py` | `wuxing_core.py` | 五行核心驱力系统 |
| `context_orchestrator.py` | `qiankun_orchestrator.py` | 乾坤编排器(天地人统筹) |
| `emotion.py` | `bagua_emotion.py` | 八卦情绪系统 |
| `memory_retrieval.py` | `yijing_memory.py` | 易经记忆(六十四卦编码) |
| `decision.py` | `taiji_decision.py` | 太极决策(阴阳平衡) |

### 配置文件重命名

| 原名称 | 五行新名称 |
|--------|-----------|
| `context_budget.toml` | `qiankun_budget.toml` |
| `active_expression.toml` | `wuxing_expression.toml` |
| `emotion_config.toml` | `bagua_config.toml` |

---

## 🎓 理论基础

### 1. 易经 (I Ching)
- 阴阳消长
- 六十四卦变化
- 物极必反

### 2. 黄帝内经 (Yellow Emperor's Medicine)
- 五行生克
- 阴阳调和
- 天地人三才

### 3. 李雅普诺夫动力学 (Lyapunov Dynamics)
- λ > 0: 混沌(阳盛)
- λ < 0: 稳定(阴盛)
- λ ≈ 0: 临界态(阴阳调和)

### 4. PSI 认知架构 (Joscha Bach)
- 生理性驱力 → 天
- 能力驱力 → 地
- 调节机制 → 人

---

## ⚠️ 使用指南

### 面向开发者
- 理解五行相生相克关系
- 监控阴阳平衡度(yin_yang_balance)
- 调整五行权重系数

### 面向用户
- 查看五行雷达图了解当前状态
- 接受五行调理建议(如"木克土,建议探索新领域")
- 理解情绪的八卦属性

---

## 📖 参考文献

1. **易经** - 周文王、孔子
2. **黄帝内经** - 轩辕黄帝
3. **Lyapunov spectrum of random neural networks** - David G. Clark, 2026
4. **Principles of Synthetic Intelligence (PSI)** - Joscha Bach, 2009
5. **The Synthetic Mind** - Josh Ferrer, 2026

---

**版本历史**:
- V3.0 (2026-11-08): 创建五行认知架构哲学文档
- 融合李雅普诺夫动力学、PSI 理论、易经五行
- 建立阴阳调和的临界态认知模型

**许可证**: MIT License
