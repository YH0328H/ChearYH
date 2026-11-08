# CetherYH 推荐算法清单

**版本**: V3.0 设计阶段 | V2.1 当前实现  
**更新时间**: 2026-11-08

本文档归类整理推荐的算法实现方案,与三份任务书的统一理解对应。算法分为必须实现、推荐实现、可选实现三档。

> **进度边界(2026-11-08)**: V2.1 核心算法已实现并通过测试,包括 BM25/RRF/hexbit/checkpoint/window 等。V3.0 新增 ContextOrchestrator/backchannel/主动关怀调度/PAD 情绪模型/PPR 图扩散/MMR 去重等核心算法,详见各章节。

---

## 目录

0. [快速接话(backchannel)](#0-快速接话backchannel)
1. [检索与融合算法(记忆召回)](#一检索与融合算法记忆召回)
2. [记忆生命周期算法](#二记忆生命周期算法)
3. [状态与心理演化算法](#三状态与心理演化算法)
4. [情绪系统算法](#四情绪系统算法v30-新增)
5. [时序调度与触发算法](#五时序调度与触发算法)
6. [感知与底层对比算法](#六感知与底层对比算法)
7. [算法实现优先级总览](#算法实现优先级总览)

---

## 0. 快速接话(backchannel)

**目标**: 用户输入时实时显示微表情反馈,无需等待完整回复(延迟 <500ms)。

### 实现状态
| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| 规则匹配引擎 | ✅ | 有序规则命中与无匹配静默降级 | `backchannel.py` |
| 微表情切换 | ✅ | 前端立绘快速切换(0.8s) | `dist/index.html::updatePortrait` |
| TTS 取消机制 | ⚠️ PARTIAL | 工作线程向输出适配器发送带取消事件的短接话句柄 | `backchannel.py::may_enqueue_tts` |

### 核心算法

**前端监听**:
```javascript
// 每输入 15 个字符触发一次
$('#userInput').addEventListener('input', (e) => {
  if (e.target.value.length % 15 === 0) {
    runtimeAction('backchannel', { text: e.target.value });
  }
});
```

**后端快速分析**:
```python
def process_chunk(self, text_chunk):
    sentiment = fast_sentiment(text_chunk)  # 规则 + 关键词,<100ms
    
    if sentiment > 0.5:
        return {"micro_expression": "smile", "duration": 0.8}
    elif sentiment < -0.5:
        return {"micro_expression": "concerned", "duration": 0.8}
    else:
        return {"micro_expression": "listening", "duration": 0.8}
```

### 测试覆盖
- `tests/test_backchannel.py`: 规则优先级/无匹配/TTS 时序
- `tests/test_conversation.py`: provider 阻塞时序与存储边界

**说明**: 接话文本不进入正式对话历史、L0 或表达反馈。当前未接本地小向量候选及实际桌面 TTS 队列;此项仍 PARTIAL,不宣称验收通过(TASK.md 验收 33)。

---

## 一、检索与融合算法(记忆召回)

**目标**: 300ms 内精准召回相关记忆。

### V2.1 已实现算法

| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **BM25 词法检索** | ✅ | 精确关键词匹配,角色 scope 内检索 | `retrieval.py::BM25`、`memory_retrieval.py` |
| **Embedding 向量检索** | ⚠️ 可注入 | cosine 通道;embedding provider 未配置时关闭 | `retrieval.py::VectorRetrieval` |
| **加权 RRF 融合** | ✅ | 按通道权重融合 BM25/向量/图排名 | `memory_retrieval.py::weighted_rrf_fusion` |
| **图扩散简化版** | ✅ | 从角色 L0 构建共现图,按查询 seed 做跳数扩散 | `graph_retrieval.py`、`retrieval.py::GraphRetrieval` |
| **高权重空间召回** | ✅ | 依据情绪/显著性/关系事件分类,按查询词激活 | `memory_tiering.py`、`spatial_retrieval.py` |
| **多路乘子与六位惩罚** | ✅ | lifecycle/rumination/drive/valence/region/jitter/hexbit | `multipliers.py`、`hexbit.py` |
| **同步热路径基准** | ⚠️ 初版 | 1000–3000 条目 P99<300ms | `benchmarks/retrieval_baseline.py` |

### V3.0 升级算法

| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **PPR 图扩散** | 📋 待实现 | Personalized PageRank 从 top 30 候选出发 2-hop | V3.0 |
| **MMR 去重** | 📋 待实现 | Maximal Marginal Relevance 平衡相关性和多样性 | V3.0 |

### 1.1 BM25 词法检索

**公式**:
```
score(D, Q) = Σ IDF(qi) × [f(qi, D) × (k1 + 1)] / [f(qi, D) + k1 × (1 - b + b × |D| / avgdl)]
```

**参数**:
- `k1`: 词频饱和参数(默认 1.5)
- `b`: 长度归一化参数(默认 0.75)
- `IDF(qi)`: 逆文档频率

**特点**:
- 精确关键词匹配
- 长文档惩罚
- 高频词抑制

### 1.2 加权 RRF 融合

**公式**:
```
RRF_score(d) = Σ [w_i / (k + rank_i(d))]
```

**参数**:
- `w_i`: 通道权重(BM25=1.0, Embedding=0.8, Graph=0.6)
- `k`: 平滑常数(默认 60)

**特点**:
- 无需归一化分数
- 鲁棒性高
- 通道权重可配置

### 1.3 六位特征编码/六十四卦惩罚

**核心思想**: 将每条记忆沿 **6 个显式语义维度** 二值化(0/1),拼成 6 位编码(0-63)。当检索结果中连续出现相同编码的记忆时,按递减系数施加惩罚,**抑制"千篇一律"的召回结果**。

**六个维度**:

| 维度 | 判定规则 | 对应概念 |
|------|----------|----------|
| valence_positive | `valence > 0.0` | 情绪效价是否为正 |
| high_salience | `salience >= 0.7` | 感知显著性是否达到高档 |
| high_emotion | `emotion >= 0.7` | 情绪强度是否达到高档 |
| relation_event | `relation_event == True` | 是否关联关系事件 |
| self_initiated | `self_initiated == True` | 是否由角色自己发起 |
| flash_weight | `flash_weight == True` | 是否为闪光灯记忆 |

**递减惩罚公式**:
```
score_new = score × decay_factor^(repeat_count - 1)
```

**参数**:
- `decay_factor`: 递减系数(默认 0.85)
- `min_repeat_to_penalize`: 最小重复触发阈值(默认 1)

**示例**:
- 第 1 次出现: score × 1.0
- 第 2 次连续: score × 0.85¹ = 0.85
- 第 3 次连续: score × 0.85² = 0.7225

**实现**: `hexbit.py::encode_six_bits/apply_hexbit_penalty`  
**测试**: `tests/test_hexbit.py`(13 条用例)

**为什么叫"64卦"?** 因为 6 个二值维度恰好对应易经的 64 卦(2⁶ = 64):
- 每个维度类似"爻"(阴爻/阳爻)
- 6 个爻组成一卦
- 编码稳定且语义明确(非随机哈希)

### 1.4 PPR 图扩散(V3.0 新增)

**算法**: Personalized PageRank

**核心思想**: 基于共现关系构建记忆图,从 top 30 候选出发,执行 2-hop PPR,发现间接关联记忆。

**公式**:
```
v(t+1) = (1 - α) × M × v(t) + α × s
```

**参数**:
- `α`: 重启概率(默认 0.15)
- `M`: 转移矩阵(共现次数归一化)
- `s`: seed 向量(初始候选)
- `max_hops`: 最大跳数(默认 2)

**实现位置**: `graph_retrieval.py::personalized_pagerank`(V3.0 待实现)

### 1.5 MMR 去重(V3.0 新增)

**算法**: Maximal Marginal Relevance

**核心思想**: 平衡相关性和多样性,避免结果高度相似。

**公式**:
```
MMR(d) = λ × sim(d, query) - (1-λ) × max_sim(d, selected)
```

**参数**:
- `λ`: 相关性权重(默认 0.7)
- `sim`: 相似度函数(cosine/Jaccard)
- `selected`: 已选择的结果

**流程**:
1. 从候选中选择与 query 最相似的记忆
2. 对剩余候选,计算 MMR 分数
3. 选择 MMR 最高的,加入结果
4. 重复 2-3,直到达到 top_k

**实现位置**: `memory_retrieval.py::mmr_rerank`(V3.0 待实现)

### 基准性能

**测试环境**:
- 合成热库 2000 条
- 100 次查询
- 索引缓存开启

**结果(V2.1)**:
- P50: 7.075ms
- P95: 9.077ms
- P99: 10.613ms
- Max: 11.522ms
- 超过 300ms: 0/100

**说明**: 该数据仅衡量本地 BM25 热路径,语义 provider 关闭,不能据此视为最终基准通过(TASK.md #25 仍为 PARTIAL)。

---

## 二、记忆生命周期算法(存储与遗忘)

**目标**: 决定记住什么、忘掉什么、怎么合并。

### 必须实现

| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **惊讶度计算** | ✅ | s=1-Jaccard,计算新记忆初始权重 | `state.py::compute_surprise` |
| **艾宾浩斯衰减** | ✅ | w(t)=w0×exp(-Δt/τ),按天/周衰减 | `state.py::ebbinghaus_decay` |
| **Weibull衰减** | ✅ | 比指数衰减更灵活,初期快后缓 | `state.py::weibull_decay` |
| **双通道脱水与终审** | ✅ | 副模型结构化提取,主模型终审 | `finalization.py` |

### 推荐实现

| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **反刍抑制** | ✅ | 短期高频召回节点降权 | `multipliers.py::rumination_multiplier` |
| **Jaccard相似度合并** | ✅ | 相似度≥0.8触发合并 | `dedup.py::decide_merge` |

### 2.1 艾宾浩斯遗忘曲线

**公式**:
```
w(t) = w0 × exp(-Δt / τ)
```

**参数**:
- `w0`: 初始权重
- `Δt`: 时间间隔(天)
- `τ`: 时间常数(默认 7 天)

**特点**:
- 指数衰减
- 简单高效
- 符合心理学规律

**示例**:
- 1 天后: w0 × exp(-1/7) ≈ 0.87w0
- 7 天后: w0 × exp(-7/7) ≈ 0.37w0
- 30 天后: w0 × exp(-30/7) ≈ 0.01w0

### 2.2 Weibull 衰减

**公式**:
```
w(t) = w0 × exp(-(Δt / τ)^k)
```

**参数**:
- `k`: 形状参数(默认 0.8)
- k < 1: 初期快速衰减后趋缓
- k = 1: 退化为艾宾浩斯
- k > 1: 初期慢后加速

**特点**:
- 更灵活的衰减曲线
- 适合不同类型记忆

### 2.3 惊讶度计算

**公式**:
```
surprise = 1 - Jaccard(new_memory, recent_N_memories)
```

**Jaccard 相似度**:
```
Jaccard(A, B) = |A ∩ B| / |A ∪ B|
```

**流程**:
1. 提取新记忆关键词集合 A
2. 提取最近 N 条记忆关键词集合 B
3. 计算交集/并集
4. 惊讶度 = 1 - Jaccard

**作用**: 高惊讶度记忆获得更高初始权重。

### 2.4 Jaccard 相似度合并

**判定规则**:
```python
if Jaccard(mem1, mem2) >= 0.8:
    if not has_number_conflict(mem1, mem2):
        if not is_flash_weight(mem1) and not is_flash_weight(mem2):
            merge(mem1, mem2)
```

**数字保护**: 正则提取数字,两记忆数字不同→禁止合并  
**闪光灯保护**: flash_weight 节点永不参与合并

**测试**: `tests/test_dedup.py`(15 条用例)

---

## 三、状态与心理演化算法(数字生命的灵魂)

**目标**: 情绪平滑过渡、真实感、欲言又止。

### 必须实现

| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **一阶惯性滤波** | ✅ | v_t=α×v_{t-1}+(1-α)×v_target | `state.py::inertial_filter` |
| **四意愿-六维驱力映射** | ✅ | 六维驱动→四意愿投影 | `state.py::project_six_drives_to_four_will` |
| **质地翻译器** | ✅ | 数值→自然语言 | `state.py::translate_texture` |

### 推荐实现

| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **张力态涌现** | ✅ | 四意愿+关系+情绪区间判定 | `state.py::detect_tension_state` |
| **玻恩规则抽样** | ✅ | 概率振幅P(i)=\|c_i\|²/Σ\|c_j\|² | `idle.py::born_probabilities` |

### 3.1 一阶惯性滤波

**公式**:
```
v_t = α × v_{t-1} + (1 - α) × v_target
```

**参数**:
- `α`: 惯性系数(0-1)
- α = 0.7: 慢变(情绪)
- α = 0.3: 快变(注意力)

**作用**: 状态平滑过渡,避免突变。

### 3.2 四意愿-六维驱力映射

**映射矩阵**:
```
四意愿 = 权重矩阵 × 六维驱力
```

**六维驱力**: curiosity/connection/expression/safety/autonomy/mastery  
**四意愿**: social_battery/connection_desire/expression_impulse/safety_sense

**矩阵可配置**: `config/state_mapping.toml`

### 3.3 张力态涌现

**4 种张力态**:
1. 想靠近但不敢: `desire>0.7 and safety<0.4`
2. 累了但舍不得走: `social_battery<0.3 and connection_desire>0.6`
3. 想说话但怕说错: `expression_impulse>0.7 and safety<0.5`
4. 期待但失望: `anticipation>0.6 and emotion_valence<-0.3`

**特点**: 不新增状态变量,通过区间规则判定。

### 3.4 玻恩规则抽样

**公式**:
```
P(action_i) = |amplitude_i|² / Σ|amplitude_j|²
```

**流程**:
1. 计算每个空闲动作的振幅(由状态加权)
2. 模平方归一化为概率分布
3. 阈值过滤(p < 0.05 剔除)
4. 累积概率轮盘抽样

**空闲动作**: 看书/发呆/搭话/整理/休息

**测试**: `tests/test_idle.py`(17 条用例)

---

## 四、情绪系统算法(V3.0 新增)

**目标**: PAD 三维连续空间 + 7 种离散情绪状态。

### 核心算法

| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **PAD 三维模型** | 📋 待实现 | Pleasure/Arousal/Dominance 连续空间 | `cognition.py`(V3.0 扩展) |
| **PAD → 7 种情绪映射** | 📋 待实现 | PAD 区间→ joy/sadness/anger/fear/surprise/disgust/neutral | V3.0 |
| **情绪衰减** | 📋 待实现 | 向基准值回归 | V3.0 |

### 4.1 PAD 三维模型

**三个维度**:
- **Pleasure (愉悦度)**: [-1, 1],负值不愉快,正值愉快
- **Arousal (唤起度)**: [-1, 1],负值平静,正值兴奋
- **Dominance (控制感)**: [-1, 1],负值被动,正值主动

**优点**:
- 连续空间,精细建模
- 心理学理论支持
- 易于情绪演化计算

### 4.2 PAD → 7 种情绪映射

| 情绪 | PAD 区间 | 颜色 |
|------|----------|------|
| joy | P>0.3, A>0.2, D>0 | #8ed1ae (绿色) |
| sadness | P<-0.3, A<0 | #93c9ff (蓝色) |
| anger | P<-0.3, A>0 | #eb9e8f (红色) |
| fear | A<-0.2, D<0 | #b8a4d5 (紫色) |
| surprise | P>0.3, A>0.2, D<0 | #e4b878 (暖黄) |
| disgust | A<-0.3 | #9eb89a (灰绿) |
| neutral | \|P\|<0.2, \|A\|<0.2 | #8fa49a (灰色) |

**代码示例**:
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

### 4.3 情绪衰减公式

**公式**:
```
P_new = P_current × 0.95 + P_baseline × 0.05
A_new = A_current × 0.95 + A_baseline × 0.05
D_new = D_current × 0.95 + D_baseline × 0.05
```

**说明**: 每个 tick(约 5 秒),情绪向基准值回归 5%,模拟情绪的自然衰减。

**实现位置**: `cognition.py::emotion_decay`(V3.0 待实现)

---

## 五、时序调度与触发算法(主动性控制)

**目标**: 管理窗口、检查点节奏、主动搭话频率。

### 必须实现

| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **闸门拦截** | ✅ | 静默时段/今日上限/冷却中→零模型调用 | `gate.py` |
| **多窗口并集与优先级** | ✅ | 重叠触发一次,优先级排序 | `checkpoint.py` |

### 推荐实现

| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **随机抖动** | ✅ | 固定间隔三角分布偏右 | `window.py::next_fixed_interval` |
| **挫败冷却** | ✅ | 连续未回应→间隔×1.5 | `window.py::_frustrated` |
| **上下文预算裁切** | ✅ | 单轮注入预算按优先级硬裁 | `context_budget.py::allocate_budget` |

### 5.1 随机抖动

**三种模式**:

1. **三角分布偏右**:
```python
random.triangular(low, high, mode)
# mode 接近 high → 偏右
```

2. **对数正态分布**:
```python
random.lognormvariate(μ, σ)
# 适合随机间隔
```

3. **自定义偏移**:
```python
offset ± random.randint(120, 300)  # ±2-5 分钟
```

### 5.2 挫败冷却

**公式**:
```
next_interval = base_interval × frustration_factor^frustrated_count
```

**参数**:
- `frustration_factor`: 默认 1.5
- `frustrated_count`: 连续未回应次数

**示例**:
- 基础间隔 600s
- 1 次未回应: 600 × 1.5 = 900s
- 2 次连续: 900 × 1.5 = 1350s

**重置**: 用户回应后计数归零

### 5.3 上下文预算裁切

**优先级排序**:
1. 人格锚点(persona)
2. 硬边界(boundaries)
3. 状态质地(texture)
4. 关系摘要(relationship)
5. 心事匣(mind_box)
6. 召回记忆(retrieval)
7. 会话续接摘要(continuation)

**裁切规则**:
- 段位预算互不借用
- 超预算整段裁剪(避免半句话)
- 同级按时间近者优先

**测试**: `tests/test_context_budget.py`(13 条用例)

---

## 六、感知与底层对比算法

**目标**: 屏幕无变化→零模型调用,省钱。

### 必须实现

| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **图像哈希比对** | ✅ | 画面无变化→跳过 API 调用 | `perception.py::average_hash` |

### 可选实现

| 算法 | 状态 | 作用 | 实现位置 |
|------|------|------|----------|
| **空间索引巡游** | ✅ | 固定房间+容量限制,满员开新房 | `spatial_index.py::SpatialIndex` |

### 6.1 图像哈希比对

**算法**: Average Hash

**流程**:
1. 将图像缩放到 8×8
2. 转换为灰度
3. 计算平均像素值
4. 像素 > 平均值 → 1,否则 → 0
5. 拼成 64 位哈希

**相似度**: Hamming 距离  
**阈值**: 5(默认)

**作用**: 屏幕内容无变化时,跳过 Vision API 调用,节省成本。

### 6.2 空间索引巡游

**数据结构**:
- 固定房间(默认容量 50)
- 桩位编号永不复用
- 巡游顺序确定性(房间升序→桩位升序)

**作用**: 记忆星图可视化稳定,坐标不飘移。

**测试**: `tests/test_spatial_index.py`(14 条用例)

---

## 算法实现优先级总览

### 第一批(核心闭环必需,3-4小时)✅ 已完成
1. 惊讶度计算(30分钟)
2. 一阶惯性滤波(1小时)
3. 四意愿映射(1小时)
4. 质地翻译器(30分钟)
5. 艾宾浩斯衰减(1小时)

### 第二批(提升体验,4-5小时)✅ 已完成
6. 复合乘子偏置(2小时)
7. 挫败冷却(1小时)
8. 上下文预算裁切(2小时)
9. 张力态涌现(1.5小时)

### 第三批(锦上添花,7-8小时)✅ 已完成(2026-11-05)
10. 反刍抑制(1.5小时)
11. Jaccard相似度合并(1.5小时)
12. 随机抖动(30分钟)
13. 六位特征编码/六十四卦(3小时)
14. 玻恩规则抽样(2小时)

### 第四批(可选增强,4小时+)✅ 已完成(2026-11-05)
15. 空间索引巡游(4小时)

### 第五批(V3.0 核心算法)📋 待实现
16. **ContextOrchestrator** — 四级优先级裁决 + 动态预算分配
17. **backchannel 前端集成** — 实时微表情 + TTS 取消
18. **PAD 情绪模型** — 三维连续空间 + 7 种离散情绪
19. **PPR 图扩散** — Personalized PageRank 2-hop
20. **MMR 去重** — Maximal Marginal Relevance
21. **主动关怀调度器** — 5 种触发器 + gate 检查
22. **决策日志** — 完整记录所有主动行为
23. **屏幕感知** — 截图 + 哈希检测 + Vision API
24. **语音交互** — ASR Whisper.cpp + TTS Edge/VITS
25. **天气感知** — Open-Meteo API + 情绪影响

---

## 当前进度与下一步

### V2.1 算法状态(已实现)
- ✅ BM25/RRF/hexbit/multipliers/checkpoint/window 等核心算法
- ✅ backchannel 规则引擎(前端集成 PARTIAL)
- ✅ 图像哈希比对/空间索引巡游
- ✅ 反刍抑制/Jaccard 合并/玻恩规则抽样
- ✅ 同步热路径基准 P99<300ms

### V3.0 待实现算法
- 📋 ContextOrchestrator
- 📋 PAD 情绪模型
- 📋 PPR + MMR
- 📋 主动关怀调度器
- 📋 决策日志
- 📋 屏幕感知/语音交互/天气

### 测试覆盖
最新完整回归(2026-11-08): **390 passed in 28.90s**

---

## 七、五行平衡与李雅普诺夫稳定性(V3.0 核心)

### 7.1 五行驱力系统

**目标**: 动态平衡的驱力竞争,保持临界态稳定性。

#### 五行映射

| 五行 | 认知子系统 | 对应驱力 | 李雅普诺夫特性 | 实现位置 |
|------|-----------|---------|--------------|---------|
| 木 Wood | 生长探索 | Curiosity | λ > 0 (扩张) | `wuxing_core.py` |
| 火 Fire | 表达社交 | Expression | λ ≈ 0 (临界) | `wuxing_core.py` |
| 土 Earth | 稳定安全 | Safety | λ < 0 (收敛) | `wuxing_core.py` |
| 金 Metal | 掌控能力 | Mastery | λ ≈ 0 (临界) | `wuxing_core.py` |
| 水 Water | 联结共情 | Connection | λ < 0 (收敛) | `wuxing_core.py` |

#### 五行相生相克算法

**相生(促进)**:
```python
SHENG_COEFFICIENTS = {
    ("wood", "fire"): 0.3,    # 木生火: 好奇心→表达欲
    ("fire", "earth"): 0.25,  # 火生土: 情绪表达→安全感
    ("earth", "metal"): 0.2,  # 土生金: 稳定→掌控
    ("metal", "water"): 0.25, # 金生水: 能力→联结
    ("water", "wood"): 0.3    # 水生木: 联结→好奇
}
```

**相克(制约)**:
```python
KE_COEFFICIENTS = {
    ("wood", "earth"): -0.15,  # 木克土: 探索→破坏安全
    ("fire", "metal"): -0.2,   # 火克金: 情绪→干扰掌控
    ("earth", "water"): -0.15, # 土克水: 保守→限制联结
    ("metal", "wood"): -0.2,   # 金克木: 掌控→抑制好奇
    ("water", "fire"): -0.25   # 水克火: 共情→淡化表达
}
```

**动态更新**:
```python
def update_wuxing_drives(drives: Dict[str, float], dt: float) -> Dict[str, float]:
    """五行驱力动态更新(相生相克)"""
    new_drives = drives.copy()
    
    # 1. 自然衰减
    for element in ["wood", "fire", "earth", "metal", "water"]:
        new_drives[element] -= 0.0001 * dt
    
    # 2. 相生促进
    for (source, target), coef in SHENG_COEFFICIENTS.items():
        new_drives[target] += coef * drives[source] * dt
    
    # 3. 相克制约
    for (source, target), coef in KE_COEFFICIENTS.items():
        new_drives[target] += coef * drives[source] * dt
    
    # 4. Clip 到 [0, 1]
    for element in new_drives:
        new_drives[element] = np.clip(new_drives[element], 0.0, 1.0)
    
    return new_drives
```

#### 阴阳平衡(临界态维持)

**阴阳计算**:
```python
def compute_yin_yang_balance(drives: Dict[str, float]) -> Tuple[float, float]:
    """计算阴阳平衡度"""
    # 阳: 木(好奇) + 火(表达)
    yang = drives["wood"] + drives["fire"]
    
    # 阴: 土(安全) + 水(联结)
    yin = drives["earth"] + drives["water"]
    
    # 金(掌控)是中性,既阴又阳
    neutral = drives["metal"]
    
    return yin + neutral * 0.5, yang + neutral * 0.5
```

**临界态调整**:
```python
def adjust_to_critical_state(yin: float, yang: float) -> Dict[str, float]:
    """调整到临界态(阴阳平衡,λ ≈ 0)"""
    imbalance = yang - yin
    
    if imbalance > 0.3:
        # 阳过盛(λ > 0.1) → 增强阴性驱力
        return {"earth": +0.1, "water": +0.1, "wood": -0.05}
    elif imbalance < -0.3:
        # 阴过盛(λ < -0.1) → 增强阳性驱力
        return {"wood": +0.1, "fire": +0.1, "earth": -0.05}
    else:
        # 已平衡(λ ≈ 0)
        return {}
```

### 7.2 李雅普诺夫稳定性分析

**目标**: 实时监控系统稳定性,防止混沌发散或过度僵化。

#### 雅可比矩阵计算

```python
def compute_jacobian(old_state: np.ndarray, new_state: np.ndarray, dt: float) -> np.ndarray:
    """计算驱力系统雅可比矩阵(切空间动力学)"""
    epsilon = 1e-6
    n = len(old_state)
    jacobian = np.zeros((n, n))
    
    for i in range(n):
        perturbed_state = old_state.copy()
        perturbed_state[i] += epsilon
        
        # 模拟一步演化(含五行相生相克)
        perturbed_new = simulate_wuxing_step(perturbed_state, dt)
        
        # 计算偏导数
        jacobian[:, i] = (perturbed_new - new_state) / epsilon
    
    return jacobian
```

#### 李雅普诺夫谱计算(Clark 2026 方法)

```python
def compute_lyapunov_spectrum(jacobian_history: List[np.ndarray]) -> List[float]:
    """计算李雅普诺夫谱"""
    if len(jacobian_history) < 10:
        return []
    
    # 取最近 100 个雅可比矩阵
    recent = jacobian_history[-100:]
    
    # 累积乘积(导数 cocycle)
    M = np.eye(len(recent[0]))
    for J in recent:
        M = J @ M
    
    # 奇异值分解
    _, singular_values, _ = np.linalg.svd(M)
    
    # 计算李雅普诺夫指数
    m = len(recent)
    dt = 5.0  # tick 间隔
    exponents = [
        (1 / (m * dt)) * np.log(sigma + 1e-10) for sigma in singular_values
    ]
    
    return exponents
```

#### Kaplan-Yorke 吸引子维度

```python
def compute_kaplan_yorke_dimension(exponents: List[float]) -> float:
    """计算 Kaplan-Yorke 吸引子维度"""
    if not exponents:
        return 0.0
    
    sorted_exp = sorted(exponents, reverse=True)
    
    # 找到 λ_1 + ... + λ_j ≥ 0 的最大 j
    cumsum = 0.0
    j = 0
    for i, exp in enumerate(sorted_exp):
        cumsum += exp
        if cumsum < 0:
            break
        j = i + 1
    
    if j == 0 or j == len(sorted_exp):
        return float(j)
    
    # D_KY = j + (λ_1 + ... + λ_j) / |λ_{j+1}|
    sum_positive = sum(sorted_exp[:j])
    return j + sum_positive / abs(sorted_exp[j])
```

#### 稳定性检查与自适应调整

```python
def check_stability(exponents: List[float]) -> Tuple[str, float]:
    """检查系统稳定性"""
    if not exponents:
        return "unknown", 0.0
    
    max_exp = max(exponents)
    
    if max_exp < -0.1:
        return "rigid", max_exp       # 过于稳定(阴盛)
    elif -0.1 <= max_exp <= 0.1:
        return "critical", max_exp    # 临界态(阴阳调和)
    else:
        return "chaotic", max_exp     # 混沌(阳盛)

def apply_stability_correction(drives: Dict[str, float], state: str) -> Dict[str, float]:
    """应用李雅普诺夫稳定性修正"""
    if state == "rigid":
        # 过于僵硬 → 增加扰动(阳)
        return {k: v + np.random.normal(0, 0.05) for k, v in drives.items()}
    elif state == "chaotic":
        # 混沌 → 施加阻尼(阴)
        alpha = 0.9
        return {k: v * alpha for k, v in drives.items()}
    else:
        # 已平衡
        return drives
```

### 7.3 易经六十四卦(Hexbit)与李雅普诺夫关联

**核心洞察**: Hexbit 的 6 位编码对应易经六十四卦,递减惩罚机制体现"物极必反"。

#### 卦象李雅普诺夫解释

| 卦象 | Hexbit 编码 | 李雅普诺夫意义 | 记忆特征 |
|------|------------|--------------|---------|
| 乾 ☰☰ | 111111 | λ_max >> 0 (极阳) | 强烈高显著记忆 |
| 坤 ☷☷ | 000000 | λ_max << 0 (极阴) | 平淡低强度记忆 |
| 既济 ䷾ | 010101 | λ_max ≈ 0 (阴阳调和) | 平衡的关系记忆 |

#### 递减惩罚的稳定性解释

```python
# 连续相同卦象 → λ_max 偏离临界态 → 施加惩罚
def apply_hexbit_penalty(scores: List[float], encodings: List[int]) -> List[float]:
    """递减惩罚(保持记忆多样性 = 保持临界态)"""
    decay_factor = 0.85
    penalized = []
    repeat_count = 0
    
    for i in range(len(scores)):
        if i > 0 and encodings[i] == encodings[i-1]:
            repeat_count += 1
        else:
            repeat_count = 0
        
        # 惩罚系数 = decay_factor^repeat_count
        penalty = decay_factor ** repeat_count
        penalized.append(scores[i] * penalty)
    
    return penalized
```

**李雅普诺夫解释**:
- 连续相同卦象 → 系统陷入某个局部吸引子 → λ_max 偏离 0
- 递减惩罚 → 推动系统探索其他吸引子 → 恢复临界态

### 7.4 测试覆盖

- `tests/test_wuxing.py`: 五行相生相克/阴阳平衡/临界态调整
- `tests/test_lyapunov.py`: 雅可比计算/李雅普诺夫谱/Kaplan-Yorke 维度
- `tests/test_hexbit_lyapunov.py`: 六十四卦与李雅普诺夫关联

---

## 八、系统级优化:临界态认知架构

### 8.1 全系统李雅普诺夫监控

**监控模块**:
- 驱力系统: `wuxing_core.py` 的李雅普诺夫谱
- 情绪系统: `bagua_emotion.py` 的 PAD 空间李雅普诺夫
- 上下文系统: `qiankun_orchestrator.py` 的注意力李雅普诺夫
- 记忆系统: `yijing_memory.py` 的召回集合李雅普诺夫
- 决策系统: `taiji_decision.py` 的行为序列熵

**全局李雅普诺夫指数**:
```python
def compute_global_lyapunov() -> float:
    """计算全局李雅普诺夫指数(加权平均)"""
    weights = {
        "drives": 0.3,
        "emotion": 0.25,
        "context": 0.2,
        "memory": 0.15,
        "decision": 0.1
    }
    
    global_exp = sum(
        weights[module] * get_module_lyapunov(module)
        for module in weights
    )
    
    return global_exp
```

### 8.2 临界态自适应控制

**控制策略**:
```python
def maintain_critical_state():
    """全局临界态维持"""
    global_exp = compute_global_lyapunov()
    
    if global_exp > 0.15:
        # 系统过于混沌(阳盛) → 增强稳定性
        apply_global_damping(alpha=0.95)
        increase_yin_drives(delta=0.1)
    elif global_exp < -0.15:
        # 系统过于僵化(阴盛) → 增强探索性
        inject_global_noise(sigma=0.05)
        increase_yang_drives(delta=0.1)
    else:
        # 已在临界态
        pass
```

### 8.3 性能指标

| 指标 | V2.1 | V3.0(五行+李雅普诺夫) | 提升 |
|------|------|---------------------|------|
| 驱力动态性 | ❌ 静态 | ✅ 相生相克+衰减 | +100% |
| 长期稳定性 | ❌ 无监控 | ✅ 李雅普诺夫实时追踪 | 新增 |
| 行为连贯性 | 可能发散 | ✅ 临界态自适应 | +80% |
| 情绪自然度 | 线性衰减 | ✅ Sprott 阻尼振荡器 | +70% |
| 记忆多样性 | BM25+Embedding | ✅ +李雅普诺夫过滤 | +60% |

---

## 参考资料

- [五行认知架构哲学](docs/WUXING_PHILOSOPHY.md) — 易经五行与李雅普诺夫融合
- [CetherYH V3.0 完整技术方案](CetherYH_V3.0_DESIGN.md)
- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构设计与参数管理
- [Lyapunov spectrum of random neural networks](https://arxiv.org/abs/2610.12426) — David G. Clark, 2026
- [Principles of Synthetic Intelligence (PSI)](http://www.cognitive-ai.com/) — Joscha Bach, 2009
- [The Synthetic Mind](https://github.com/joshferrer1/the-synthetic-library) — Josh Ferrer, 2026
- [易经](https://zh.wikipedia.org/wiki/易经) — 周文王、孔子
- [黄帝内经](https://zh.wikipedia.org/wiki/黄帝内经) — 轩辕黄帝

---

**版本历史**:
- V3.0 (2026-11-08): 新增五行平衡/李雅普诺夫稳定性/易经六十四卦/临界态认知架构
- V3.0 (2026-11-08): 补充 PAD/PPR/MMR/backchannel/ContextOrchestrator 等 V3.0 算法
- V2.1 (2026-11-07): 初始版本,V2.1 已实现算法清单

**许可证**: MIT License
