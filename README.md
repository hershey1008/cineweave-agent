# CineWeave · 影织

**多轮电影选片：LLM 意图解析 × BGE-M3 语义召回 × 个性化推荐**

[![Tests](https://github.com/hershey1008/cineweave-agent/actions/workflows/unit-tests.yml/badge.svg)](https://github.com/hershey1008/cineweave-agent/actions/workflows/unit-tests.yml)
[![License](https://img.shields.io/badge/license-CC_BY--NC--SA_4.0-lightgrey)](LICENSE)
[界面截图](docs/media/README.md) · [LangGraph 改造与对照](docs/agent-v1/langgraph-refactor.md)

用自然语言选片，继续修改条件、替换已看电影、查看推荐依据。支持多路召回、DeepFM 排序、会话条件更新、反馈和运行追踪。

![对话选片界面](docs/media/screenshots/langgraph/02-chat-welcome.jpg)

```text
Vue → FastAPI → LangGraph 单轮编排 → LLM 结构化意图 → 会话与硬过滤
    → BGE-M3 / YouTubeDNN / I2I / 类型偏好 → 融合排序 → 事实解释
存储：PostgreSQL · Redis · Elasticsearch
```

## 快速开始：完整应用

需要 **Git、Python 3.11、Docker Engine / Docker Desktop 与 Compose v2**。镜像内安装后端依赖、构建前端；宿主机无需安装 TensorFlow 或 Node.js。

使用**真实 MovieLens-1M 的 FunRec 扩充数据**。首次下载按下列步骤训练 YouTubeDNN / DeepFM；已有同一快照的模型才可跳过训练。原始 1M 不含剧情简介、片长和海报。

### 1. 获取代码、配置环境

```bash
git clone https://github.com/hershey1008/cineweave-agent.git
cd cineweave-agent
python scripts/configure_local.py
```

生成 `.env` 和独立密码，不覆盖已有配置。真实 LLM 需要填写 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`；留空进入明确标记的规则模式。

### 2. 下载并准备数据

直接下载 [FunRec 扩充 MovieLens-1M 数据（ZIP，约 1.93 GB）](https://funrec-datasets.s3.eu-west-3.amazonaws.com/funrec-movielens-1m.zip)。解压后，将四个 pickle 文件和海报目录放到：

```text
artifacts/data/
├── movies.pkl
├── users.pkl
├── ratings.pkl
├── movie_metadata.pkl
└── image/
```

这是已处理的数据，直接用于本仓库的导入和内容清洗，无需先转换原始 `*.dat`。`.env` 默认 `FUNREC_RAW_DATA_PATH=./artifacts/data`；若保留解压目录，则将该值改为包含 `movies.pkl` 的目录。

下载数据不会自动生成推荐模型。默认训练输出为 `artifacts/processed/web_project/deployed_models/`，与 `.env` 的 `FUNREC_MODELS_PATH` 对应；已有模型和完整包恢复方法见 [数据与模型](docs/DATA_AND_MODELS.md)。

### 3. 构建镜像

```bash
docker compose build backend semantic frontend
```

首次使用标准 Dockerfile，镜像内安装训练依赖；宿主机无需安装 TensorFlow。

### 4. 导入数据

```bash
docker compose up -d --wait postgres redis elasticsearch
docker compose run --rm --no-deps backend python -m scripts.seed_cineweave
docker compose run --rm --no-deps backend python -m scripts.seed_redis_profiles
docker compose run --rm --no-deps backend python -m scripts.index_movies_elasticsearch
```

### 5. 训练推荐模型、准备语义索引

首次下载在仓库根目录执行（PowerShell / Bash）：

```bash
docker compose run --rm --no-deps --env FUNREC_RAW_DATA_PATH=/data --env FUNREC_PROCESSED_DATA_PATH=/training --volume "${PWD}/artifacts/processed:/training" backend python -m offline.pipeline --steps retrieval_preprocess,ranking_preprocess,retrieval_training,ranking_training,deploy
```

这会依次处理特征、训练 YouTubeDNN / DeepFM 并部署到默认模型目录。各步产物和参数见 [训练说明](docs/DATA_AND_MODELS.md#4-首次下载后的特征处理与模型训练)。已有完整模型可跳过。

```bash
python -m pip install requests
python scripts/download_embedding_model.py
```

随后按 [语义编码与索引](docs/REPRODUCE.md#6-语义编码与索引) 生成电影向量并运行 `python scripts/pin_index.py`；已有完整索引可直接恢复。BGE-M3 使用固定预训练权重。

### 6. 启动前后端

```bash
docker compose up -d --wait semantic
docker compose up -d backend frontend
docker compose ps
```

前端 **http://localhost:13000**；API 文档 **http://localhost:18000/docs**。账号 `demo@cineweave.local`、`history@cineweave.local`，默认密码均为 `CineweaveDemo!2026`。

试试：“想看关于太空探索的科幻片，120分钟以内，不要恐怖片” → “轻松一点，其他要求不变” → “第三部看过了，换一部”。

停止并保留数据：`docker compose stop`。配置 API 后：`docker compose up -d --force-recreate --no-deps backend`。开发启动、验收与排错见 [完整运行指南](docs/REPRODUCE.md)。

## 目录与文档

```text
cineweave-agent/
├── backend/
│   ├── app/              API、鉴权、Agent、会话与数据库
│   ├── online/           过滤、召回、排序、多样性与冷启动
│   ├── offline/          特征、训练、模型部署与 Redis 导入
│   ├── scripts/          数据初始化、ES 索引与集成验收
│   ├── tests/            后端单元测试
│   └── vendor/funrec/    模型定义、特征、训练与评估组件
├── semantic_service/
│   ├── app/              BGE-M3 编码、索引加载与检索 API
│   ├── offline/          内容清洗、质量审计与索引构建
│   └── tests/            语义索引测试
├── frontend/             Vue / Vite 页面、状态、接口与 Nginx
├── evaluation/           对话用例、检索查询与评估脚本
├── scripts/              配置、数据打包/恢复、模型下载与启停
├── docs/                 运行、架构、契约、验收、来源与演示
├── licenses/             完整许可文本
├── .github/workflows/    Python 测试与前端构建 CI
├── .env.example          本机配置模板
└── docker-compose.yaml   六项运行服务
```

| 文档 | 内容 |
| --- | --- |
| [完整运行指南](docs/REPRODUCE.md) | 环境、数据导入、模型准备、前后端启动、验收与排错 |
| [数据与模型](docs/DATA_AND_MODELS.md) | 本地快照、打包/恢复、模型格式和分发状态 |
| [实际项目结构与全部文档](docs/PROJECT_STRUCTURE.md) | 模块、关键文件、运行产物及完整文档索引 |
| [架构](docs/agent-v1/architecture.md) / [接口契约](docs/agent-v1/contracts.md) | 推荐链路、状态与 API |
| [LangGraph 改造与对照](docs/agent-v1/langgraph-refactor.md) | 单轮图、原流程切换、固定输入对照与结果边界 |
| [界面截图](docs/media/README.md) | 统一风格后的电影库、对话选片与运行详情 |
| [本地演示](docs/RUN_LOCAL.md) / [验收记录](docs/LOCAL_VALIDATION.md) | 演示步骤与已有实测口径 |
| [数据来源](docs/provenance.md) / [第三方说明](THIRD_PARTY_NOTICES.md) | 数据字段、来源和许可 |

单元测试：`python -m pip install -r requirements-test.txt`，然后 `python -m pytest -q`。检索质量仍待人工标注评估，不报告未经验证的效果提升。

基于 [Datawhale FunRec](https://github.com/datawhalechina/fun-rec)，保留 [CC BY-NC-SA 4.0](LICENSE) 署名与许可。数据、海报和模型遵循各自条款；密钥、本地数据包和权重不进入 Git。
