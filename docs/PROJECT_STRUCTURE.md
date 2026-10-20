# 实际项目结构与文档索引

本页描述当前实现目录。运行所需数据、索引、权重、`.env` 和运行日志在本机保存；不属于 Git 源码。

## 后端

```text
backend/
├── app/
│   ├── main.py                         FastAPI 入口、启动与路由
│   ├── config.py                       配置与环境变量
│   ├── database.py                     SQLAlchemy 连接与会话
│   ├── models.py                       用户、电影、会话、事件与反馈表
│   ├── schemas.py                      业务请求/响应模型
│   ├── core/{auth,security}.py          JWT、鉴权与密码
│   ├── api/
│   │   ├── deps.py                     API 依赖
│   │   └── v1/
│   │       ├── api.py                  路由聚合
│   │       └── endpoints/              auth、chat、agent_health、movies、
│   │                                  recommendations、ratings、search、
│   │                                  users、genres、people、stats、health
│   ├── agent/
│   │   ├── orchestrator.py             会话动作编排与提交
│   │   ├── schemas.py                  意图、约束、状态、动作契约
│   │   ├── llm_client.py               LLM / 规则解析与错误分类
│   │   ├── prompts.py                  意图提示词
│   │   ├── session_service.py          会话持久化、幂等与 CAS
│   │   ├── tools.py                    指代解析与受控推荐工具
│   │   ├── explanation_service.py      电影事实模板与证据
│   │   └── timeouts.py                 跨层超时预算
│   └── services/elasticsearch_service.py
├── online/
│   ├── context.py                     请求级上下文
│   ├── context_pipeline.py            会话推荐流水线
│   ├── pipeline.py                    常规推荐流水线
│   ├── filtering.py                   条件、已看与候选过滤
│   ├── recall/                        semantic、youtubednn、item_based、
│   │                                  trending、fusion、service、resource_manager
│   ├── ranking/                       deepfm、contextual、service、resource_manager
│   ├── reranking/                     contextual、dispersion、service
│   └── cold_start/                    检测、热门、类型偏好与 UCB
├── offline/
│   ├── config.py                      数据/产物路径及训练配置
│   ├── pipeline.py                    离线任务入口
│   ├── feature/                       preprocess_retrieval、preprocess_ranking
│   ├── training/                      train_retrieval、train_ranking
│   └── storage/                       local_deploy、redis_ingest
├── scripts/                           seed_cineweave、seed_redis_profiles、
│                                      index_movies_elasticsearch、故障与集成验证
├── vendor/funrec/
│   ├── config/                        推荐模型参数
│   ├── features/                      特征列与处理器
│   ├── models/                        YouTubeDNN、DeepFM 等模型定义与层
│   ├── training/                      训练器与损失
│   └── evaluation/                    评估器与指标
├── tests/                             后端与产物工具测试
├── requirements.txt
├── Dockerfile
└── Dockerfile.local
```

会话存储逻辑在 `app/agent/session_service.py`，不是设计草案中的独立 repositories 目录。接口当前走 `/api` 前缀。当前解释为事实模板，没有额外部署自由生成的解释模型。

## 语义服务与前端

```text
semantic_service/
├── app/
│   ├── main.py                        健康、检索与服务入口
│   ├── encoder.py                     固定 BGE-M3 编码器
│   ├── index.py                       索引完整性与精确向量检索
│   └── schemas.py                     检索协议
├── offline/
│   ├── prepare_documents.py           内容清洗、别名与字段提取
│   └── build_index.py                 编码、质量清单、版本发布与回滚
├── tests/
├── requirements.txt
└── Dockerfile / Dockerfile.local

frontend/
├── src/
│   ├── main.js / App.vue              Vue 入口
│   ├── router/index.js                聊天、浏览、详情、个人页路由
│   ├── views/                         ChatRecommend、Home、MovieDetail、
│   │                                  Auth、Profile、AddMovie
│   ├── components/                    Header、MovieCard、MovieRow、
│   │                                  SearchOverlay、StarRating
│   ├── services/{api,chatApi}.js       API、令牌与聊天请求
│   ├── stores/auth.js                 登录状态
│   └── assets/                        样式与静态素材
├── public/
├── package.json / package-lock.json
├── vite.config.js                     13000 开发端口与 18000 代理
├── nginx.conf                         容器静态资源与 /api 代理
└── dockerfile / Dockerfile.local
```

## 工具、评估与运行产物

| 位置 | 职责 |
| --- | --- |
| `scripts/configure_local.py` | 创建本机配置、独立密钥与空目录，不覆盖已有 `.env` |
| `scripts/package_local_assets.py` | 打包本机真实数据、海报、已有推荐模型与活动索引 |
| `scripts/install_local_assets.py` | 逐文件校验与安全恢复，拒绝覆盖非空目标 |
| `scripts/check_setup.py` | 只读检查环境与产物，不输出密钥 |
| `scripts/download_embedding_model.py` | 下载并核验固定编码器 |
| `scripts/pin_index.py` | 固定本机后端的语义索引版本 |
| `scripts/start.ps1` / `stop.ps1` | 已初始化的 Windows 实例启停 |
| `scripts/sync_to_desktop.ps1` | 本机开发目录同步，保留目标已有 `.env` |
| `scripts/create_evaluation_fixtures.py` | 生成检索查询草案与功能 fixture |
| `scripts/make_demo_narration.ps1` / `make_demo_video.py` | 本地旁白及视频制作 |
| `evaluation/datasets/` | 对话 fixture、检索查询草案、标签样例 |
| `evaluation/runners/` | smoke_live、evaluate_conversations、verify_llm_conversation、performance_live、collect_retrieval_runs、score_retrieval |
| `evaluation/reports/generated/` | 本次机器生成的报告；Git 忽略 |
| `artifacts/data/` | 本机恢复的真实扩充数据及海报 |
| `artifacts/processed/web_project/deployed_models/` | 本机已训练的推荐模型、词表、向量 |
| `artifacts/semantic_index/` | 活动指针与版本化语义索引 |
| `artifacts/model_cache/bge-m3/` | 固定 BGE-M3 权重、配置和校验元数据 |
| `artifacts/distribution/` | 本地数据包、清单与 zip 哈希；不公开上传 |
| `.github/workflows/unit-tests.yml` | Python 单元测试、前端 npm 构建 |
| `docker-compose.yaml` | postgres、redis、elasticsearch、semantic、backend、frontend |
| `requirements-test.txt` / `requirements-video.txt` | 轻量测试与视频制作独立依赖 |
| `pytest.ini` | 测试目录、Python 路径、asyncio 模式 |
| `.env.example` / `.gitignore` / `.gitattributes` | 配置模板、忽略规则与文本行尾 |
| `LICENSE` / `licenses/` / `THIRD_PARTY_NOTICES.md` | 项目与第三方许可 |

## 全部文档

| 文档 | 用途 |
| --- | --- |
| [README](../README.md) | 项目入口、完整应用快速开始、主要目录 |
| [REPRODUCE](REPRODUCE.md) | 环境、加载、模型、导入、前后端启动、测试与排错 |
| [DATA_AND_MODELS](DATA_AND_MODELS.md) | 真实本地快照、打包与恢复、文件格式、分发状态 |
| [PROJECT_STRUCTURE](PROJECT_STRUCTURE.md) | 当前实际目录与本文档索引 |
| [RUN_LOCAL](RUN_LOCAL.md) | 已初始化实例启停、演示账号和对话顺序 |
| [LOCAL_VALIDATION](LOCAL_VALIDATION.md) | 已有实测、模式、限制与性能口径 |
| [verification-summary.json](evidence/verification-summary.json) | 公开汇总的机器可读验收摘要 |
| [local-asset-verification.json](evidence/local-asset-verification.json) | 本地真实数据包恢复、文件校验与测试摘要，不包含数据记录 |
| [provenance](provenance.md) | FunRec、MovieLens 与扩充字段来源/审计 |
| [CONTRIBUTIONS](CONTRIBUTIONS.md) | 源码归属与修改说明；保留上游署名 |
| [architecture](agent-v1/architecture.md) | V1 设计架构与处理链路 |
| [contracts](agent-v1/contracts.md) | 意图、会话、动作、接口契约 |
| [project-structure](agent-v1/project-structure.md) | V1 设计目录/模块映射，实际文件以本文为准 |
| [implementation-plan](agent-v1/implementation-plan.md) | V1 阶段计划与实现边界 |
| [acceptance](agent-v1/acceptance.md) | V1 验收设计与指标口径 |
| [评估数据说明](../evaluation/datasets/README.md) | fixture 与待人工审核查询的区别 |
| [视频说明](media/README.md) | 截图剪辑、旁白、字幕与视频重建 |
| [video-plan.json](media/video-plan.json) / [video-manifest.json](media/video-manifest.json) | 分镜、旁白、时长和编码信息 |
| [第三方说明](../THIRD_PARTY_NOTICES.md) | 上游代码、数据、模型与素材条款 |
