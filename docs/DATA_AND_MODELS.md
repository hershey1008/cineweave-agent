# 数据与模型

## 下载与处理数据

直接下载上游提供的 [funrec-movielens-1m.zip](https://funrec-datasets.s3.eu-west-3.amazonaws.com/funrec-movielens-1m.zip)，无需先进入或克隆 FunRec 项目。2026-10-20 检查直链返回 HTTP 200，压缩包为 1,933,960,749 字节（约 1.93 GB）。

### 1. 下载并解压

Windows PowerShell，在 CineWeave 根目录执行：

```powershell
New-Item -ItemType Directory -Force 'artifacts/downloads' | Out-Null
curl.exe --fail --location --retry 3 --continue-at - --output 'artifacts/downloads/funrec-movielens-1m.zip' 'https://funrec-datasets.s3.eu-west-3.amazonaws.com/funrec-movielens-1m.zip'
Expand-Archive -LiteralPath 'artifacts/downloads/funrec-movielens-1m.zip' -DestinationPath 'artifacts/downloads/funrec-extracted'
```

Linux/macOS：

```bash
mkdir -p artifacts/downloads
curl --fail --location --retry 3 --continue-at - --output artifacts/downloads/funrec-movielens-1m.zip 'https://funrec-datasets.s3.eu-west-3.amazonaws.com/funrec-movielens-1m.zip'
unzip artifacts/downloads/funrec-movielens-1m.zip -d artifacts/downloads/funrec-extracted
```

解压使用新的目标目录，不覆盖已有数据。下载文件沿用上游托管地址，本仓库不再上传一份数据副本。

### 2. 检查文件并配置路径

找到解压结果中**直接包含以下文件**的目录，将其内容放到 `artifacts/data/`，或者直接将 `.env` 的 `FUNREC_RAW_DATA_PATH` 设置为该目录。不要指向 zip 文件或多套一层的父目录。

```text
artifacts/data/
├── movies.pkl            电影基本信息、简介及外部字段
├── users.pkl             用户属性
├── ratings.pkl           用户—电影显式评分与时间戳
├── movie_metadata.pkl    别名、主创、演职员、人物、外部评分
└── image/                海报
```

```dotenv
FUNREC_RAW_DATA_PATH=./artifacts/data
FUNREC_MODELS_PATH=./artifacts/processed/web_project/deployed_models
FUNREC_PROCESSED_DATA_PATH=./artifacts/processed
```

该 ZIP 是 FunRec 扩充并处理过的数据，不需要在本项目重新从 MovieLens `*.dat` 转为 pickle。不要以原始 MovieLens 下载包替换它：原始 1M 缺少简介、片长与扩充元数据。

### 3. 在当前仓库完成数据处理

先按 [环境与镜像配置](REPRODUCE.md#4-构建镜像和基础设施) 构建服务、启动基础设施，然后在 CineWeave 根目录执行：

```bash
docker compose run --rm --no-deps backend python -m scripts.seed_cineweave
docker compose run --rm --no-deps backend python -m scripts.seed_redis_profiles
docker compose run --rm --no-deps backend python -m scripts.index_movies_elasticsearch
```

| 顺序 | 处理内容 | 结果 |
| --- | --- | --- |
| PostgreSQL 导入 | 读取四个 pickle，规范空值/数值，导入电影、用户、评分与元数据，计算电影评分统计 | 业务表和演示账号 |
| Redis 画像 | 按评分时间整理近期历史，统计类型偏好 | 用户画像与在线历史特征 |
| Elasticsearch 索引 | 从 PostgreSQL 读取电影标题、类型、年份、简介等字段 | 可搜索的电影索引 |
| 语义内容清洗 | 解码 HTML 实体、规整空白、合并中英文别名、整理类型/年份/片长，隔离非 `movie` 关联 | 电影内容文档和质量清单 |
| BGE-M3 编码 | 使用固定编码器生成归一化向量，校验文件哈希与完整性后发布版本 | `artifacts/semantic_index/<version>/` |

最后两步由 `python -m semantic_service.offline.build_index` 一起完成；安装依赖、环境变量和完整命令见 [当前仓库的语义索引步骤](REPRODUCE.md#3-模型准备)。有已验证的现成索引时直接恢复，无需重复编码。

### 4. 接入已有模型并启动

数据 ZIP 与推荐模型部署产物是两类材料。将已有 `deployed_models` 放到上述配置目录，或让 `FUNREC_MODELS_PATH` 指向其现有位置；格式见 [模型与索引目录](#模型与索引目录)。本次不重新训练，也不将数据导入或向量编码写成模型训练。

数据、模型和索引齐备后，按 [前后端启动](REPRODUCE.md#6-前后端启动) 运行即可。已有完整本地包则可以跳过下载/导入材料整理，使用下文的恢复流程。

## 当前本地快照

本次使用作者本机 **FunRec 已处理的真实 MovieLens-1M 数据及现有模型**，不重新训练，不生成虚构电影，不采集当前应用的聊天记录或账号数据。

| 内容 | 本地核对结果 |
| --- | ---: |
| `movies.pkl` | 3883 部电影 |
| `users.pkl` | 6040 个 MovieLens 用户 |
| `ratings.pkl` | 1,000,209 条显式评分 |
| `movie_metadata.pkl` | 别名、主创、人物、演职员与外部评分表 |
| `image/` | 3883 个海报文件 |
| 推荐模型 | 21 个部署文件，包含 YouTubeDNN / DeepFM 与词表 |
| 活动语义索引 | 3532 部电影，1024 维 |

3532 与 3883 的差异来自对 351 条外部实体类型非 `movie` 记录的隔离，原始数据仍保留。类型过滤不等于完整实体映射审核。原始 MovieLens 的评分是显式评分，不能当作真实曝光/点击日志。

## 公开分发状态

**本项目制作的完整“数据 + 推荐模型 + 语义索引”包仅在本地保存，尚未上传到公开 GitHub 或 Release。** 上游数据通过本页的 FunRec 直链获取。MovieLens 官方条款要求单独取得再分发许可；当前尚未取得。扩充简介、海报、IMDb 关联的来源与分发条件还需核对。将数据处理为 pickle 不代表可以按本仓库代码许可重新授权。

- [MovieLens-1M 官方入口](https://grouplens.org/datasets/movielens/1m/)
- [官方数据使用条款](https://files.grouplens.org/datasets/movielens/ml-1m-README.txt)
- [FunRec 扩充数据直接下载](https://funrec-datasets.s3.eu-west-3.amazonaws.com/funrec-movielens-1m.zip)
- [本地扩充字段审计](provenance.md)

使用者可从上面的上游直链取得扩充数据，并按本页步骤准备。我们自己的“数据 + 推荐模型 + 活动语义索引”完整包仍只在本地保存，没有公开下载地址；上游数据 ZIP 不能替代这一整包。

## 制作本地数据包

在 CineWeave 仓库根目录执行；将路径换为自己的 FunRec 根目录：

```powershell
python scripts/package_local_assets.py --funrec-root 'C:\path\to\fun-rec-master'
```

输入路径：

```text
fun-rec-master/
├── funrec-movielens-1m/
│   ├── movies.pkl
│   ├── users.pkl
│   ├── ratings.pkl
│   ├── movie_metadata.pkl
│   └── image/
└── processed_data/web_project/deployed_models/
```

默认同时读取当前仓库的 `artifacts/semantic_index/active.json` 及活动版本。可用 `--index-root` 指定已验证的其他索引根目录，`--output` 指定输出 zip，`--without-posters` 生成不含海报的小包。已有输出不会覆盖。

输出位于 Git 忽略的本地目录：

```text
artifacts/distribution/
├── cineweave-local-assets.zip
├── cineweave-local-assets.zip.sha256
└── cineweave-local-assets.manifest.json
```

完整包约 **1.99 GB（1.86 GiB）**，包含 3914 个文件及内置清单；不含 BGE-M3 权重。每个文件记录大小和 SHA-256；zip 另有整体哈希。海报已压缩，zip 使用无损存储，保留原始文件字节。包内目录为 `data/`、`models/`、`semantic_index/`；不复制 `.env`、API 密钥或数据库业务日志。

## 校验与恢复

先核对 zip 的旁路 SHA-256（Windows 示例）：

```powershell
Get-FileHash 'artifacts/distribution/cineweave-local-assets.zip' -Algorithm SHA256
Get-Content 'artifacts/distribution/cineweave-local-assets.zip.sha256'
```

新克隆的源码目录中：

```bash
python scripts/configure_local.py
python scripts/install_local_assets.py /path/to/cineweave-local-assets.zip --verify-only
python scripts/install_local_assets.py /path/to/cineweave-local-assets.zip
python scripts/pin_index.py
```

恢复到 `artifacts/data/`、`artifacts/processed/web_project/deployed_models/`、`artifacts/semantic_index/`。安装器逐项检查大小、哈希与路径，拒绝路径穿越、异常目录、重复文件与非空目标，不执行 pickle 加载。**校验和只证明完整性；之后应用会读取 pickle，因此仅使用可信数据包。**

## 模型与索引目录

```text
artifacts/
├── processed/web_project/deployed_models/
│   ├── vocab_dict.pkl
│   ├── item_embeddings.npy
│   ├── movie_ids.npy
│   ├── recall/
│   │   ├── vocab_dict.pkl
│   │   ├── item_embeddings.npy
│   │   └── movie_ids.npy
│   ├── ranking/
│   │   ├── vocab_dict.pkl
│   │   ├── feature_dict.pkl
│   │   └── model_config.pkl
│   └── model/
│       ├── user_recall/
│       │   ├── active.json
│       │   └── v1/user_model/{saved_model.pb,variables/,...}
│       └── ranking/
│           ├── active.json
│           └── v1/ranking_model/{saved_model.pb,variables/,...}
├── semantic_index/
│   ├── active.json
│   └── <version>/
│       ├── manifest.json
│       ├── documents.jsonl
│       ├── movie_ids.npy
│       ├── embeddings.npy
│       └── quality_report.json
└── model_cache/bge-m3/
    ├── cineweave-model.json
    ├── pytorch_model.bin
    └── ...配置、分词器及 SentenceTransformer 文件
```

BGE-M3 通过 `python scripts/download_embedding_model.py` 从官方固定版本获取，或拷入自己已验证的同版本缓存。编码器权重、索引 manifest revision、文件哈希及后端 `SEMANTIC_INDEX_VERSION` 必须相符。

## 训练代码保留在哪里

`backend/offline/feature/`、`backend/offline/training/`、`backend/offline/storage/` 保留特征、YouTubeDNN / DeepFM 训练和部署代码。当前交付采用现有模型产物，不执行这些训练入口；本次没有新的训练结果或效果提升结论。需要研究训练链路时应使用独立输出目录，并审查样本划分、评分标签与负采样口径。
