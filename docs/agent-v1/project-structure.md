# 目录与相对 FunRec 的改动清单

> 当前实际目录与全部文档请查看 [PROJECT_STRUCTURE.md](../PROJECT_STRUCTURE.md)。下文保留 V1 设计与模块改动说明。

下面保留 V1 设计目录。当前已迁入应用实现；部分数据访问逻辑合并在 Agent 和 API 模块中，独立会话流水线位于 `online/context_pipeline.py`。实际目录和运行情况见根 README 及本地验收记录。

## 1. 计划目录

```text
cineweave-agent/
├── backend/
│   ├── app/
│   │   ├── agent/
│   │   │   ├── orchestrator.py          # Agent 状态机与预算
│   │   │   ├── schemas.py               # 意图、动作、字段操作与状态
│   │   │   ├── llm_client.py            # LLM 适配、超时、结构化输出
│   │   │   ├── prompts.py               # 提示词与版本
│   │   │   ├── tools.py                 # 受控业务工具
│   │   │   ├── session_service.py       # 状态合并、并发与持久化
│   │   │   └── explanation_service.py   # 证据、解释与回退
│   │   ├── repositories/
│   │   │   ├── chat_repository.py
│   │   │   └── event_repository.py
│   │   ├── api/v1/endpoints/
│   │   │   ├── chat.py
│   │   │   ├── recommendation_events.py
│   │   │   ├── agent_health.py
│   │   │   └── recommendations.py
│   │   ├── models.py
│   │   ├── config.py
│   │   └── api/v1/api.py
│   ├── online/
│   │   ├── context.py
│   │   ├── pipeline.py
│   │   ├── filtering.py
│   │   ├── recall/
│   │   │   ├── semantic.py
│   │   │   ├── fusion.py
│   │   │   └── service.py
│   │   ├── ranking/
│   │   │   ├── contextual.py
│   │   │   └── service.py
│   │   └── reranking/service.py
│   ├── scripts/migrate_agent_schema.py
│   ├── tests/{unit,integration,regression}/
│   └── pyproject.toml
├── semantic_service/
│   ├── app/
│   │   ├── main.py
│   │   ├── encoder.py
│   │   ├── index.py
│   │   └── schemas.py
│   ├── offline/
│   │   ├── prepare_documents.py
│   │   ├── build_index.py
│   │   └── audit.py
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/src/
│   ├── views/ChatRecommend.vue
│   ├── components/chat/
│   ├── stores/chat.js
│   ├── services/chatApi.js
│   ├── router/index.js
│   └── components/Header.vue
├── evaluation/
│   ├── datasets/
│   ├── configs/
│   ├── runners/
│   └── reports/
├── docs/agent-v1/
├── docker-compose.yaml
└── .env.example
```

外部数据产物：`processed_data/web_project/semantic_index/<version>/`。模型、数据、用户日志不进入仓库。

## 2. 新增模块

| 模块 | 输入 | 输出 / 职责 |
| --- | --- | --- |
| `app/agent/orchestrator.py` | 登录用户、本轮消息、会话快照 | 动作执行、工具编排、预算、结果 |
| `app/agent/schemas.py` | 模型/接口数据 | 严格状态与工具参数契约 |
| `app/agent/session_service.py` | 旧状态、操作、期望版本 | 新状态、持久化与并发校验 |
| `app/agent/explanation_service.py` | 最终电影和证据 | 有依据的解释或模板 |
| `app/repositories/` | 会话、事件、反馈 | 数据访问和原子写入 |
| `online/context.py` | 画像、意图、约束和预算 | 请求级上下文 |
| `online/filtering.py` | 电影事实、硬条件 | 合法 ID、过滤原因 |
| `online/recall/semantic.py` | 语义查询和合法集合 | 语义候选与分数 |
| `online/recall/fusion.py` | 多通道候选 | 去重、多来源记录、RRF 和配额 |
| `online/ranking/contextual.py` | 偏好、语义、融合名次 | 综合排序 |
| `semantic_service/app/` | 检索请求与索引版本 | 编码、精确检索与就绪状态 |
| `semantic_service/offline/` | 扩充电影数据 | 清洗文本、向量、manifest 和质量报告 |
| `frontend` 对话模块 | API 结果和用户交互 | 对话、条件标签、卡片、反馈 |
| `evaluation` | 固定配置、测试集、运行结果 | 对照指标、失败案例和验收报告 |

## 3. 需要修改的上游模块

下列路径相对于原 FunRec 的 `web_project/`；未来复制/迁移到本仓库时必须保留上游版权与许可。

| 原路径 | 修改内容 |
| --- | --- |
| `backend/online/pipeline.py` | 请求上下文、会话分支、混合召回、统一硬过滤、完整候选评分、事实复核 |
| `backend/online/recall/service.py` | 按请求选择通道、局部特征副本、可选新融合方式、全部来源记录 |
| `backend/online/ranking/service.py` | 在最终截断前为完整保留候选提供评分；接会话排序 |
| `backend/online/reranking/service.py` | 请求级策略选择；不临时修改共享配置 |
| `backend/app/api/v1/endpoints/recommendations.py` | 登录态绑定身份，补充片长等事实；兼容原响应字段 |
| `backend/app/models.py` | 仅新增会话、消息、事件、反馈模型 |
| `backend/app/config.py` | 模型适配、服务地址、版本、超时、预算配置 |
| `backend/app/api/v1/api.py` | 注册聊天、事件和健康路由 |
| `backend/pyproject.toml` | 业务后端所需新增依赖；模型依赖归语义服务 |
| `frontend/src/router/index.js` | 聊天页路由 |
| `frontend/src/components/Header.vue` | 聊天入口 |
| `docker-compose.yaml` | 第六个语义服务，网络、健康检查与只读索引挂载 |
| `.env.example` | 非敏感配置样例；凭据使用占位值 |

## 4. 复用模块与兼容要求

| 原能力 | 处理方式 |
| --- | --- |
| YouTubeDNN、I2I、类型召回 | 保留策略实现，作为混合候选来源 |
| 冷启动候选生成 | 复用；新增语义分支后不提前结束会话流水线 |
| DeepFM 模型 | 复用评分，第一版不新增其对话输入特征 |
| 文本搜索、详情、人物资料 | 用于实体解析和事实查询 |
| 类型/年代打散 | 请求级复用并评估相关性损失 |
| 认证、评分、首页、详情页 | 回归验证；聊天反馈与评分分开 |
| 原离线训练流程 | 功能复用；需要严格算法比较时修正时间切分及统计泄漏 |

## 5. 前端行为

聊天页展示历史消息、当前条件标签、电影卡片、反馈按钮、清空本次条件入口。必须显示加载、澄清、无结果、降级、超时和重试状态。新增 `chatApi` 单独设置超时，不修改全部普通 API 的预算。

曝光在卡片实际展示后记录；返回列表不直接当作曝光。“第三部”使用保存的真实展示顺序。重复提交、快速连续发送和会话切换都进入集成测试。

## 6. 首次导入上游代码的操作边界

初始文档提交未复制上游应用、数据、模型或凭据。2026-10-20 的本地实现迁入必要应用源码并建立 `THIRD_PARTY_NOTICES.md`；数据和模型通过本地路径/忽略的 artifacts 提供。没有自动把应用源码、数据或模型推送到 GitHub。后续分发继承源码前仍需完成许可检查，不复制原项目 `.git`、`.env`、数据库卷和用户日志。
