# CetherYH 云端 API 配置表

请逐项填写 `待填` 的单元格。API Key 不要写在这个文件里，只写环境变量名，Key 本身放到你本机的环境变量中。

## 1. 对话通道（单活模型，全局只能有一个）

| 项目 | 填写内容 | 示例 |
|---|---|---|
| 渠道名 | 中转：启明星| OpenAI / Anthropic / DeepSeek / 其他 |
| 接口地址（Base URL） |https://api.aisj.ai | https://api.openai.com/v1 |
| 模型 ID |deepseek-v4-flash  | gpt-4o / claude-sonnet-5-5 / deepseek-chat |
| API Key 环境变量名 | CETHER_CHAT_API_KEY（Key 已从文件移除，请设到本机环境变量） | CETHER_CHAT_API_KEY |
| 是否支持流式输出 | 是 | 是 / 否 |

## 2. 后台通道（按职能独立配置，未填的槽位使用本地降级）

| 槽位 | 渠道与接口地址 | 模型 ID | API Key 环境变量名 | 是否启用 |
|---|---|---|---|---|
| 提取（结构化脱水） | 公益站：https://ly.77625.xyz | deepseek-v4-flash | CETHER_EXTRACT_API_KEY（Key 未写入文件，请设到本机环境变量） | 是 |
| 叙事（L1 生成） | 公益站：https://ly.77625.xyz | deepseek-v4-flash | CETHER_EXTRACT_API_KEY（与提取槽位共用，Key 未写入文件） | 是 |
| 反思 / 梦境 | 公益站：https://ly.77625.xyz | deepseek-v4-flash | CETHER_EXTRACT_API_KEY（与提取槽位共用，Key 未写入文件） | 是 |
| 人设解析 | 公益站：https://ly.77625.xyz | deepseek-v4-flash | CETHER_EXTRACT_API_KEY（与提取槽位共用，Key 未写入文件） | 是 |
| Embedding（向量） | 硅基流动：https://api.siliconflow.cn/v1 | BAAI/bge-m3（1024 维） | CETHER_EMBED_API_KEY（Key 未写入文件） | 是 |
| Rerank（重排） | 硅基流动：https://api.siliconflow.cn/v1 | BAAI/bge-reranker-v2-m3 | CETHER_EMBED_API_KEY（与 Embedding 共用，Key 未写入文件） | 是 |
| TTS（语音） | Breeze Blue：https://api.breeze.blue/v1 | breeze-tts-2-multilingual | CETHER_TTS_API_KEY（Key 未写入文件） | 是 |
| 生图 | 中转：启明星：https://api.aisj.ai | gpt-image-2.5-sunburst（按次计费，约 0.08 元/次） | CETHER_IMAGE_API_KEY（Key 未写入文件） | 否（默认关闭，触发节点才调用） |

## 3. 降级顺序（可保持默认）

| 项目 | 默认值 | 是否修改 |
|---|---|---|
| 后台槽位失效时 | 记忆提取暂停，检索降级为关键词 | 否（保持默认） |
| 终审兜底策略 | 留候选池，过期后丢弃 | 否（保持默认） |

## 4. 说明

- Embedding 维度必须与热库一致。填写后启动时会校验，不一致则拒绝加载。
- 保存前会做连通性探测：向量需返回多维数组，重排需返回相似度分数，提取需返回合规 JSON。
