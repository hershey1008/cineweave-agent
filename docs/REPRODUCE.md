# 在另一台电脑复现

项目是本机研究演示应用，不是免配置的 SaaS。仓库包含源码、测试和演示媒体；不包含数据集、用户日志、推荐模型产物或 BGE-M3 权重。

## 先看效果与检查代码

无需 API、GPU、数据库即可运行单元测试：

```bash
git clone https://github.com/hershey1008/cineweave-agent.git
cd cineweave-agent
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-test.txt
python -m pytest -q
```

前端可独立构建检查；要实际选片仍需后端服务：

```bash
cd frontend
npm ci
npm run build
```

需要 Python 3.11、Node.js 22.12+ 或兼容的受支持版本、Docker Compose。完整语义服务使用 CPU 即可运行；实际资源需求应以本机测量为准。

## 完整应用的外部产物

| 产物 | 准备方式 |
| --- | --- |
| FunRec 扩充 MovieLens 数据 | 从 [上游 Web 项目](https://github.com/datawhalechina/fun-rec/tree/master/web_project) 的数据准备入口自行获取并核对条款；需要 `movies.pkl`、元数据和图片等。本仓库不再分发该数据包 |
| YouTubeDNN / DeepFM 产物 | 使用自己已有的兼容产物，或运行随附离线训练链路重新生成。格式见下文；本次演示复用了已有预训练产物 |
| BGE-M3 | `python scripts/download_embedding_model.py`，固定 revision 并校验权重 |
| 语义索引 | 按 [运行文档](RUN_LOCAL.md) 构建并固定版本；不下载别人未核验的索引 |
| LLM API | 可选。留空是明确标记的规则模式；配置真实 API 后需要单独联调 |

数据集不是普通开源代码：MovieLens-1M 的官方 README 对再分发和商业使用分别有限制；简介、海报和扩充字段还需检查各自来源。[官方条款](https://files.grouplens.org/datasets/movielens/ml-1m-README.txt)

## 模型产物目录

`FUNREC_MODELS_PATH` 应指向部署产物目录，通常包括：

```text
deployed_models/
├── vocab_dict.pkl                 # 在线召回读取根目录词表
├── item_embeddings.npy           # 在线召回读取根目录物品向量
├── movie_ids.npy
├── recall/
│   ├── item_embeddings.npy
│   ├── movie_ids.npy
│   └── vocab_dict.pkl
├── ranking/                       # DeepFM 特征、模型配置、词表
└── model/
    ├── user_recall/active.json    # 指向用户塔版本目录
    ├── user_recall/v1/user_model/ # TensorFlow SavedModel
    ├── ranking/active.json        # 指向排序模型版本目录
    └── ranking/v1/ranking_model/  # TensorFlow SavedModel
```

实际兼容字段由 `backend/online/recall/resource_manager.py`、`backend/online/ranking/resource_manager.py` 定义；不要仅创建同名空文件冒充模型。

重新训练入口位于 `backend/offline/pipeline.py`，需要配置 `FUNREC_RAW_DATA_PATH`、`FUNREC_PROCESSED_DATA_PATH`、`REDIS_URL`，并安装完整后端依赖：

```bash
# 在 backend 目录，PYTHONPATH 应包含当前目录与 vendor
python -m offline.pipeline --steps all
```

该训练命令是继承链路的入口说明，本次发布没有在干净环境重新训练并取得新的算法成绩。重新训练后检查部署目录与模型加载状态，再进行应用验收。

## 配置与启动

1. 复制 `.env.example` 为 `.env`，设置独立 DB 密码、JWT secret 和本机路径。保留标准 Dockerfile 配置；`.local` Dockerfile 依赖作者机器缓存镜像，不能用于首次克隆。
2. 准备数据、推荐产物、BGE-M3 和语义索引。
3. 按 [RUN_LOCAL.md](RUN_LOCAL.md) 构建镜像、导入数据、建立 ES 索引、启动服务。
4. 使用 `python scripts/check_setup.py` 检查配置和外部文件；该命令只报告状态，不输出密钥。
5. 确认语义服务 ready、模型状态与实际响应后再演示。

Windows 中已初始化的目录可以使用 `scripts/start.ps1` / `scripts/stop.ps1`。Linux/macOS 使用 `docker compose up -d` / `docker compose stop`，端口统一为 13000 / 18000 / 18010。

标准前端、后端镜像已在本机单独构建，后端已连接演示基础设施完成关键推荐路径检查，见 [验收记录](LOCAL_VALIDATION.md)。完整构建与跨平台首次初始化仍需在自己的干净环境验收；仓库的自动测试不等于整个外部数据与模型链路已经一键复现。
