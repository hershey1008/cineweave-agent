# 本地运行与演示

本应用用于本机回环地址演示。页面：`http://localhost:13000`；API 文档：`http://localhost:18000/docs`；语义服务健康：`http://localhost:18010/health`。

## 已准备的桌面项目

进入桌面 `cineweave-agent`，执行：

```powershell
.\scripts\start.ps1
```

脚本保留数据卷；停止应用执行：

```powershell
.\scripts\stop.ps1
```

不要用清空数据卷的操作代替日常停止。首次启动大型语义模型可能需要等待，页面将显示准备状态。

### 演示账号

| 场景 | 邮箱 | 本地演示密码 |
| --- | --- | --- |
| 新用户 | `demo@cineweave.local` | `CineweaveDemo!2026` |
| 历史偏好 | `history@cineweave.local` | `CineweaveDemo!2026` |

首页直接选择提示词即可登录新用户演示账号；左下角切换历史用户。演示凭据仅用于本机开发环境；容器端口绑定 127.0.0.1。

### 推荐演示顺序

1. “想看关于虚拟现实的科幻片，两小时以内，不要恐怖片”。
2. “轻松一点”：确认时长和排除类型保留。
3. “时长不限了”：仅清除片长上限。
4. “第三部看过了，换一部”：排除上轮第 3 部电影。
5. 点击电影查看资料依据，点击喜欢/看过记录本次反馈。
6. 切换历史账号，查看运行详情中的协同通道和 DeepFM 信号。

## 当前解析模式与真实 LLM 接入

按本次开发约定，未配置 API 时使用明确标记的**本地规则演示**，支持设计中的主要中文条件和多轮修改。它不是通用大语言模型，不能将其测试成绩表述为真实 LLM 结果。

语义检索独立使用真实 BGE-M3 向量；推荐解释使用电影事实模板和简介证据。API 未配置不等于用随机电影模拟语义召回。

后续在本机 `.env` 配置：

```dotenv
LLM_BASE_URL=https://your-provider.example/v1
LLM_MODEL=your-model-name
LLM_API_KEY=your-local-secret
LLM_TIMEOUT_SECONDS=45
```

接入服务需支持 `/chat/completions` 与 JSON 输出契约。后端使用受限结构化意图解析，参数校验后执行工具。配置后重新创建后端容器以加载环境：

```powershell
docker compose up -d --force-recreate backend
```

当前 LLM 意图请求和最多一次 JSON 修复共享 45 秒总预算，连接上限 5 秒；外层聊天截止至少为 LLM 预算加 15 秒（默认有效值 60 秒，即使旧 `.env` 中 `CHAT_TIMEOUT=20`）；前端与 Nginx 等待上限均为 65 秒。`LLM_TIMEOUT_SECONDS` 可在本机 `.env` 中调整；若提高到 45 秒以上，也需相应调整前端和代理预算。网络超时不自动重试、不自动切回规则模式；失败轮次不保存会话修改。页面会区分超时、鉴权、限流、响应协议错误。

密钥不写入前端、不输出到日志、不提交 Git。真实服务接入后需另外执行端到端测试；现有本地规则测试不能替代它。

## 从源代码重新准备环境

前提：Docker Desktop、可访问的模型下载源、本地 FunRec 扩充数据和已有推荐模型产物。模型和数据不在 Git 中。

1. 复制 `.env.example` 为 `.env`，填写本机数据、模型目录和独立数据库密码、JWT secret。
2. `BACKEND_DOCKERFILE`、`SEMANTIC_DOCKERFILE`、`FRONTEND_DOCKERFILE` 设为标准 Dockerfile，使用可移植构建；`.local` 文件用于复用本机已存在的 `web_project-*` 镜像。
3. 构建镜像并启动基础设施。

```powershell
docker compose build backend semantic
docker compose up -d postgres redis elasticsearch
docker compose run --rm backend python -m scripts.seed_cineweave
docker compose run --rm backend python -m scripts.seed_redis_profiles
docker compose run --rm backend python -m scripts.index_movies_elasticsearch
```

数据导入是按表可恢复的初始种子导入，不重置已有业务表。若原始数据变更，请使用新的开发数据库执行完整数据升级，而不是将旧表的一部分混入新快照。

4. 下载固定语义模型。在一个有 `requests` 的 Python 环境运行：

```powershell
python scripts/download_embedding_model.py
```

脚本从官方仓库下载固定 revision，分段续传并校验权重 SHA-256，产物位于 `artifacts/model_cache/bge-m3`。

5. 离线构建索引。可以在安装语义依赖的本地 Python 3.11 环境执行：

```powershell
$env:USE_TF='0'
$env:EMBEDDING_MODEL_PATH=(Join-Path (Get-Location) 'artifacts/model_cache/bge-m3')
python -m semantic_service.offline.build_index --data-dir '你的扩充数据目录' --revision 5617a9f61b028005a4858fdac845db406aefb181
python scripts/pin_index.py
```

查询编码和电影编码均固定同一模型与模板，当前最大输入长度 512。索引会隔离 `titleType` 非 `movie` 的关联，并生成质量与隔离清单。发布前验证完整候选版本，再切换活动指针。

6. 构建前端，启动全部服务。标准前端 Dockerfile 自行执行 npm 构建；本机加速 Dockerfile 先使用 `frontend` 下的 `npm ci` 与 `npm run build` 生成 dist。

```powershell
docker compose build frontend
docker compose up -d
docker compose ps
```

## 测试入口

轻量单元测试无需 TensorFlow、模型或数据库：

```powershell
python -m pip install -r requirements-test.txt
python -m pytest -q
```

应用运行后，在有 httpx/numpy 的环境执行：

```powershell
python evaluation/runners/smoke_live.py
python evaluation/runners/evaluate_conversations.py
python evaluation/runners/performance_live.py --count 200 --concurrency 5
docker compose run --rm --no-deps backend python -m scripts.verify_failure_modes
```

生成报告位于 `evaluation/reports/generated/`，不默认提交用户运行日志。查询草案与人工标注状态见 [evaluation/datasets/README.md](../evaluation/datasets/README.md)。

## 数据与运行边界

- 原数据 3883 条，外部类型为 `movie` 的保守语义目录为 3532 条；其他关联隔离并保留原数据。
- 类型隔离不是完整的电影实体匹配审计，剩余关联仍可能有错误。当前不宣称简介和 IMDb 字段已逐条人工核验。
- 电影目录主要来自早期 MovieLens，无法回答目录之外的新片要求。
- 原有推荐模型产物用于工程集成；未在此任务中重新训练，也不宣称新的离线提升。
- 120 条检索查询是待人工审核的草案，尚无人工相关性成绩。
- 真实 LLM 配置与测试按用户后续安排进行。
