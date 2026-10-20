# 接口、会话状态与存储契约

状态：V1 设计契约。当前本地实现情况见 [运行说明](../RUN_LOCAL.md) 和 [验收记录](../LOCAL_VALIDATION.md)。路由沿用现有 FunRec 的 `/api` 前缀。

## 1. 外部 API

| 方法与路径 | 职责 | 主要约束 |
| --- | --- | --- |
| `POST /api/chat/sessions` | 创建会话 | 用户由 JWT 确定 |
| `GET /api/chat/sessions/{id}` | 恢复消息、条件与最后结果 | 校验会话归属，消息支持分页 |
| `POST /api/chat/sessions/{id}/messages` | 提交一轮需求 | 幂等消息 ID、预期会话版本、文本长度限制 |
| `POST /api/chat/sessions/{id}/feedback` | 喜欢、不感兴趣、看过 | 校验请求、电影和用户的关联 |
| `POST /api/recommendation-events` | 实际展示、点击 | 事件去重、校验推荐归属 |
| `GET /api/agent/health` | 组件与索引就绪情况 | 不返回凭据或用户数据 |

默认 top_k=10，范围 1–20。用户文本建议上限 1000 字符，过长输入给出可操作错误；该限制部署前固定。客户端无需也不能指定其他用户的 user_id。

### 1.1 消息请求字段

| 字段 | 含义 |
| --- | --- |
| `message` | 本轮用户文本 |
| `client_message_id` | 客户端唯一 ID，防重复提交 |
| `expected_state_version` | 客户端已知状态版本 |
| `top_k` | 可选推荐数量，服务端校验范围 |

### 1.2 消息响应字段

| 字段 | 含义 |
| --- | --- |
| `status` | `ok` / `clarify` / `no_results` / `degraded` |
| `reply` | 用户可读说明 |
| `active_constraints` | 当前有效条件 |
| `items` | 按展示顺序的电影卡片 |
| `request_id` | 本轮追踪标识 |
| `state_version` | 更新后的会话版本 |
| `degraded_components` | 降级组件和简要原因 |
| `clarification` | 需要补充的信息，可空 |

`items` 包含 movie_id、title、poster_url、genres、year、runtime_minutes、reason 和可审计的 evidence。证据使用字段值或简介片段；未知值保留为空，不能伪造。

错误使用明确 HTTP 状态与业务错误码：未认证、无权访问、非法字段、版本冲突、组件不可用、整体超时。冲突不写入过期状态；超时不能留下半轮成功记录。

普通 JSON 请求响应；聊天客户端初始超时 25 秒，后端截止时间 20 秒。取消请求、超时和重试要与幂等消息规则一致。

## 2. Agent 意图与状态

| 状态字段 | 含义 |
| --- | --- |
| `semantic_query` | 当前主题、氛围与其他软偏好 |
| `include_genres` / `exclude_genres` | 类型要求，映射至受控类型词表 |
| `year_min` / `year_max` | 年份边界 |
| `runtime_max` | 最大片长 |
| `exclude_seen` | 是否排除全部已交互电影 |
| `excluded_movie_ids` | 本次明确排除的电影 |
| `reference_movie_ids` | 已解析的参考电影 |
| `last_recommendation_ids` | 上轮真实展示顺序 |
| `state_version` | 并发控制版本 |

意图输出包含动作、字段操作和必要的澄清项。每个字段操作必须区分 `keep`、`set`、`clear`；列表还应区分增加、移除、替换，避免“不要恐怖片”被后续修改其他字段时意外清除。

### 状态样例（行为规格）

| 本轮输入 | 操作 | 应保留内容 |
| --- | --- | --- |
| “两小时以内，不要恐怖片” | 设置片长和排除类型 | 其他已有条件 |
| “时长不限了” | 清除片长上限 | 排除恐怖片 |
| “第三部看过了” | 解析上轮第 3 个 ID，加入会话排除列表 | 其他全部有效条件 |
| “年代也不限了” | 清除年份范围 | 片长、类型等非年份条件 |
| “重新开始选片” | 清空当前选片条件 | 登录身份和长期个人资料 |

LLM 只提出结构化操作，后端执行词表、数值范围、冲突、身份和数据目录校验。库外参考片不能被误映射成某部库内电影；重名电影需要年份等信息消歧。

## 3. 内部推荐上下文

请求级对象包含 user_features、history、semantic_query、hard_constraints、session_exclusions、top_k、候选预算、排序配置、request_id。

原服务可共享只读模型资源；请求数据必须独立。召回服务补全画像时使用请求局部副本，不修改其他请求可见对象。全量已看集合用于过滤，短历史窗口仅用于模型输入。

### 3.1 统一候选

| 字段 | 职责 |
| --- | --- |
| `movie_id` | 唯一业务电影 ID |
| `recall_sources` | 所有召回来源，去重后仍保留 |
| `channel_ranks` / `channel_scores` | 各通道名次与原始分数 |
| `semantic_score` | 查询-内容相似度 |
| `preference_score` | DeepFM 等偏好信号，不宣称真实 CTR |
| `fusion_score` | 名次融合分数 |
| `final_score` / `final_rank` | 综合排序信号与展示位置 |
| `facts` / `evidence` | 事实字段和解释依据 |

原有 `recall_type` 字段继续兼容；新增多来源字段用于解释与分析。各分数不能混淆量纲；最终多样性调整后的名次独立保存。

### 3.2 语义服务

内部 `/search`：输入文本、合法电影 ID 集合、top_k 和预期索引版本；输出候选、语义分数映射及实际版本。小目录下一次返回合法目录分数，供混合候选评分复用。该实现选择应以响应大小和耗时测量验证。

内部 `/health`：输出模型是否加载、索引是否通过检查、数据/模型/模板版本。服务未预热或版本不符时不可报告 ready。

服务端限制请求长度与候选上限，业务后端设置超时。部署内部网络不向客户端暴露模型服务或全目录评分。

## 4. PostgreSQL 新增表

| 表 | 核心字段 |
| --- | --- |
| `chat_sessions` | session_id、user_id、state_json、state_version、created_at、updated_at |
| `chat_turns` | turn_id、session_id、client_message_id、request_id、user_text、reply、recommendation_ids、trace_summary、created_at |
| `recommendation_events` | event_id、user_id、session_id、request_id、movie_id、event_type、created_at |
| `recommendation_feedback` | feedback_id、user_id、session_id、request_id、movie_id、feedback_type、created_at |

约束：会话归属校验；消息在会话内按 client_message_id 唯一；事件 ID 幂等；推荐电影与 request_id 的对应关系可验证；关键时间统一保存并在界面转换。

完成一轮后，消息、推荐顺序和状态按版本检查原子提交。工具阶段不直接修改长期偏好或原评分。并发冲突返回明确状态，不用最后写入覆盖先前结果。

V1 引入只创建新增表的增量脚本；运行前备份和检查当前库。不得调用原导入流程的 reset 选项。后续需要复杂表变更时再引入正式迁移链。

## 5. 缓存与日志

Redis 缓存会话、查询编码/检索结果，键包含必要的用户、会话、模型和索引版本。会话缓存过期后从数据库重建；用户私有结果不能只用查询字符串作为缓存键。

日志记录工具名、耗时、参数概要、模型版本、候选数、过滤原因、排序配置、token 数、降级原因。不保存凭据。公开测试使用合成账号；真实聊天日志放在不入库的私有数据目录中。

推荐已返回、实际曝光、点击、喜欢、不感兴趣和看过分别记录。喜欢并不等于原有评分；未点击并不等于真实负反馈。
