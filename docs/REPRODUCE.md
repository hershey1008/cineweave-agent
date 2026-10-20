# 完整应用运行指南

首次克隆按“环境配置 → 下载数据 → 构建镜像 → 数据导入 → 特征处理与推荐模型训练 → 语义索引 → 启动应用”执行。FunRec 数据 ZIP 不包含已训练模型。持有同一快照的完整本地包或推荐模型时，才可以跳过对应步骤。首次构建需要网络下载数据、依赖、容器和 BGE-M3。

## 1. 环境配置

安装 Git、Python 3.11、Docker Engine / Docker Desktop（Linux 容器）和 Compose v2。镜像安装 TensorFlow 后端与 CPU PyTorch 语义依赖、构建 Vue 前端。

```bash
git clone https://github.com/hershey1008/cineweave-agent.git
cd cineweave-agent
python scripts/configure_local.py
```

脚本只创建不存在的 `.env`，生成 DB 密码与 JWT secret，不输出密钥；创建空产物目录。已有 `.env` 时直接编辑。默认路径：

```dotenv
FUNREC_RAW_DATA_PATH=./artifacts/data
FUNREC_MODELS_PATH=./artifacts/processed/web_project/deployed_models
FUNREC_PROCESSED_DATA_PATH=./artifacts/processed
BACKEND_DOCKERFILE=Dockerfile
SEMANTIC_DOCKERFILE=Dockerfile
FRONTEND_DOCKERFILE=dockerfile
```

新环境使用标准 Dockerfile；`.local` 文件依赖作者机器的缓存镜像。需要可用端口 13000、18000、18010、15432、16379、19200，均绑定 127.0.0.1。为约 2 GB 的数据/海报、约 2.3 GB 的 BGE-M3、容器和构建缓存预留空间；安装本地包时还需要 zip 与暂存副本空间。

## 2. 下载数据或恢复已有产物

### 直接下载 FunRec 数据

[下载 funrec-movielens-1m.zip（约 1.93 GB）](https://funrec-datasets.s3.eu-west-3.amazonaws.com/funrec-movielens-1m.zip)。解压后将 `movies.pkl`、`users.pkl`、`ratings.pkl`、`movie_metadata.pkl` 和 `image/` 整理到 `artifacts/data/`，或将 `.env` 的 `FUNREC_RAW_DATA_PATH` 指向直接包含这些文件的解压目录。

下载与解压命令、字段含义和各步处理说明已写在 [本仓库的数据准备流程](DATA_AND_MODELS.md#下载与处理数据)，无需进入 FunRec 项目。该包已经是处理后的扩充数据，不需要再次转换原始 `*.dat`。接着按第 3–7 节依次构建、导入、训练、编码和启动。已有模型或完整包时再跳过相应步骤。

### 方式 A：安装可信本地包

制作方式见 [数据与模型](DATA_AND_MODELS.md)。在新的源码目录执行：

```bash
python scripts/install_local_assets.py /path/to/cineweave-local-assets.zip --verify-only
python scripts/install_local_assets.py /path/to/cineweave-local-assets.zip
python scripts/pin_index.py
```

安装器检查路径、文件清单、大小和 SHA-256，拒绝覆盖非空目标。校验只证明完整性，不证明未知 pickle 安全；仅使用可信快照。包内不含 `.env`、API 密钥或业务运行日志。

```text
artifacts/
├── data/{movies,users,ratings,movie_metadata}.pkl
├── data/image/
├── processed/web_project/deployed_models/
└── semantic_index/{active.json,<version>/}
```

### 方式 B：直接挂载已有 FunRec 目录

不必重复复制海报，在 `.env` 填写自己的路径：

```dotenv
FUNREC_RAW_DATA_PATH=C:/path/to/fun-rec-master/funrec-movielens-1m
FUNREC_MODELS_PATH=C:/path/to/fun-rec-master/processed_data/web_project/deployed_models
```

两个目录必须来自同一快照。语义索引仍需放在本仓库 `artifacts/semantic_index/` 并执行 `python scripts/pin_index.py`。没有现成索引时按第 6 节构建。

原始 MovieLens `*.dat` 不等于所需扩充数据：原始 1M 没有完整简介、片长、海报、演职员和 IMDb 关联，不能仅改文件名代替 pickle。

## 3. 构建镜像和基础设施

```bash
docker compose build backend semantic frontend
docker compose up -d --wait postgres redis elasticsearch
```

前端 Dockerfile 自动执行 `npm ci`、`npm run build`；TensorFlow 与 PyTorch 在两个独立镜像中安装。

## 4. 数据导入

```bash
docker compose run --rm --no-deps backend python -m scripts.seed_cineweave
docker compose run --rm --no-deps backend python -m scripts.seed_redis_profiles
docker compose run --rm --no-deps backend python -m scripts.index_movies_elasticsearch
```

依次初始化 PostgreSQL 的电影/用户/评分/元数据及演示账号、Redis 历史画像、Elasticsearch 搜索索引。种子导入按表跳过已有记录，不会比较并升级数据版本。换快照时使用新的开发实例和数据卷，不能将新数据与旧词表混合；不要清空当前演示实例。

## 5. 特征处理、推荐模型训练与部署

**首次下载必须执行这一节；已有同一快照的完整模型产物时可以跳过。** 使用默认 `.env` 路径，在仓库根目录执行：

```bash
docker compose run --rm --no-deps --env FUNREC_RAW_DATA_PATH=/data --env FUNREC_PROCESSED_DATA_PATH=/training --volume "${PWD}/artifacts/processed:/training" backend python -m offline.pipeline --steps retrieval_preprocess,ranking_preprocess,retrieval_training,ranking_training,deploy
```

容器依次执行召回特征处理、排序特征处理、YouTubeDNN 训练、DeepFM 训练、模型部署。训练目录通过可写挂载落盘到 `artifacts/processed/web_project/`；其中 `deployed_models/` 正是默认 `FUNREC_MODELS_PATH`。

请勿省略两个 `--env` 和可写 `--volume`：Compose 中在线服务的 `/models` 是只读挂载，训练需要使用单独的 `/training` 输出路径。Windows PowerShell 与 Bash 均可使用上面 `${PWD}` 写法。

各步输入、输出、参数、续跑方式和产物检查详见 [首次下载后的训练流程](DATA_AND_MODELS.md#4-首次下载后的特征处理与模型训练)。本次仅补文档，没有重新执行全量训练，不将历史演示模型或规则测试成绩当作本次训练结果。

## 6. 语义编码与索引

推荐模型已经在上一节训练/部署，或由已有产物恢复。这里单独准备 BGE-M3 内容编码器与电影语义索引，不重新训练 BGE-M3。

准备语义编码器：

```bash
python -m pip install requests
python scripts/download_embedding_model.py
```

固定 BGE-M3 revision：`5617a9f61b028005a4858fdac845db406aefb181`，输出 `artifacts/model_cache/bge-m3/`；下载器校验权重 SHA-256。也可以拷贝自己已验证的同版本缓存，包含 `cineweave-model.json` 与所有配置、分词器文件。

本地包已包含索引时跳过下段。仅当没有索引或内容变更时才进行内容编码；这不是重新训练推荐模型。

```bash
python -m venv .semantic-venv
# Windows: .\.semantic-venv\Scripts\Activate.ps1
# Linux/macOS: source .semantic-venv/bin/activate
python -m pip install torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r semantic_service/requirements.txt
```

Windows PowerShell：

```powershell
$env:USE_TF='0'
$env:EMBEDDING_MODEL_PATH=(Resolve-Path 'artifacts/model_cache/bge-m3').Path
python -m semantic_service.offline.build_index --data-dir '你的扩充数据目录' --revision 5617a9f61b028005a4858fdac845db406aefb181
python scripts/pin_index.py
```

Linux/macOS：

```bash
USE_TF=0 EMBEDDING_MODEL_PATH="$PWD/artifacts/model_cache/bge-m3" python -m semantic_service.offline.build_index --data-dir '/path/to/funrec-movielens-1m' --revision 5617a9f61b028005a4858fdac845db406aefb181
python scripts/pin_index.py
```

内容清洗后隔离非 `movie` 关联，生成向量、质量报告与文件哈希，验证完整版本后切换活动指针。电影与查询均使用相同编码器，1024 维向量、512 tokens 上限。

## 7. 前后端启动

```bash
docker compose up -d --wait semantic
docker compose up -d backend frontend
docker compose ps
python scripts/check_setup.py
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:13000 |
| API 文档 | http://localhost:18000/docs |
| Agent 健康 | http://localhost:18000/api/agent/health |
| 语义健康 | http://localhost:18010/health |

演示账号 `demo@cineweave.local`、`history@cineweave.local`；默认密码 `CineweaveDemo!2026`，首次创建由 `.env` 的 `DEMO_PASSWORD` 控制。模型首次加载较慢，等待语义健康 `ready: true`；演示步骤见 [RUN_LOCAL.md](RUN_LOCAL.md)。

## 8. LLM 配置

`.env` 中填写：

```dotenv
LLM_BASE_URL=https://your-provider.example/v1
LLM_MODEL=your-model-name
LLM_API_KEY=your-local-secret
LLM_TIMEOUT_SECONDS=45
```

需支持 `/chat/completions` 与 JSON 输出契约。保存后 `docker compose up -d --force-recreate --no-deps backend`。

默认 LLM 总预算 45 秒，聊天外层有效预算至少 60 秒，前端/Nginx 为 65 秒。超时不静默转为规则成功，失败轮次不保存修改。页面配置状态不能代替一次实际请求验收。密钥不进入前端、Git 或本地数据包。

## 9. 验收、开发与停止

```bash
python -m pip install -r requirements-test.txt
python -m pytest -q
python evaluation/runners/smoke_live.py
python evaluation/runners/evaluate_conversations.py
```

前两行无需模型或数据库；后两行需要已运行应用，主要验证规则模式 fixture。真实 API 配好后单独执行 `python evaluation/runners/verify_llm_conversation.py`。报告写入 `evaluation/reports/generated/`。已有实测见 [LOCAL_VALIDATION.md](LOCAL_VALIDATION.md)；本次整理未重新训练或重新执行整套容器验收。

前端开发需 Node.js 22.12+：在 `frontend/` 执行 `npm ci`、`npm run dev -- --host 127.0.0.1`。Vite 默认 13000，代理到后端 18000；先停止 Docker 前端或另指定开发端口，避免冲突。

```bash
docker compose stop
docker compose up -d
docker compose logs --tail 100 backend semantic
```

`stop` 保留数据卷。不要用删除数据卷的命令代替日常停止。

## 常见问题

| 现象 | 检查 |
| --- | --- |
| 安装包拒绝覆盖 | 目标已有数据/模型/索引，使用新克隆目录或直接挂载 |
| 数据或词表不存在 | `.env` 路径、解包结果；Windows 路径用 `/` |
| 语义不 ready | 权重 revision、索引哈希及 `SEMANTIC_INDEX_VERSION` 是否一致 |
| 历史账号模型降级 | SavedModel、词表与数据是否齐全且属于同一快照 |
| 意图超时/鉴权失败 | API URL、模型、密钥、网络；重建 backend 加载新环境 |
| 搜索无结果 | 数据导入后是否执行 ES 索引脚本 |
| 构建找不到 `web_project-*` | 新机器改用标准 Dockerfile，移除 `.local` 设置 |
