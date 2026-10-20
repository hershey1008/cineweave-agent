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

先按 [环境与镜像配置](REPRODUCE.md#3-构建镜像和基础设施) 构建服务、启动基础设施，然后在 CineWeave 根目录执行：

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

最后两步由 `python -m semantic_service.offline.build_index` 一起完成；安装依赖、环境变量和完整命令见 [当前仓库的语义索引步骤](REPRODUCE.md#6-语义编码与索引)。有已验证的现成索引时直接恢复，无需重复编码。

### 4. 首次下载后的特征处理与模型训练

首次下载的 ZIP 只有扩充数据，没有已训练的 YouTubeDNN / DeepFM。完成镜像构建和数据导入后，在 CineWeave **仓库根目录**执行：

```bash
docker compose run --rm --no-deps --env FUNREC_RAW_DATA_PATH=/data --env FUNREC_PROCESSED_DATA_PATH=/training --volume "${PWD}/artifacts/processed:/training" backend python -m offline.pipeline --steps retrieval_preprocess,ranking_preprocess,retrieval_training,ranking_training,deploy
```

这条命令适用于 PowerShell 和 Bash。`${PWD}` 表示当前仓库根目录；将本机 `artifacts/processed/` 以可写方式挂载到容器 `/training`。`/data` 使用 Compose 已配置的真实数据挂载。显式覆盖容器内两个路径，避免将宿主机路径传给容器，或向在线服务的只读 `/models` 挂载写入。

首次构建使用以下 `.env` 路径，使训练输出和在线服务读取同一目录：

```dotenv
FUNREC_RAW_DATA_PATH=./artifacts/data
FUNREC_PROCESSED_DATA_PATH=./artifacts/processed
FUNREC_MODELS_PATH=./artifacts/processed/web_project/deployed_models
```

| 实际步骤名 | 工作 | 主要产物（相对 `artifacts/processed/web_project/`） |
| --- | --- | --- |
| `retrieval_preprocess` | 编码用户/电影特征，按时间构建行为序列与下一物品样本 | `train_eval_sample_final.pkl`、`feature_dict.pkl`、`vocab_dict.pkl` |
| `ranking_preprocess` | 构建评分衍生标签与离线模拟负样本，输出逐点排序样本 | `ranking_train_eval_sample.pkl`、`ranking_feature_dict.pkl`、`ranking_vocab_dict.pkl` |
| `retrieval_training` | 训练 YouTubeDNN，保存用户塔/物品塔并生成归一化物品向量 | `saved_models/user_model/`、`saved_models/item_model/`、`item_embeddings.npy`、`movie_ids.npy` |
| `ranking_training` | 独立训练 DeepFM，输出排序模型与配置 | `saved_models/ranking_model/`、`ranking_model_config.pkl` |
| `deploy` | 复制模型、词表、向量与配置，写入活动版本指针 | `deployed_models/` |

`--steps` 使用表中的实际步骤名，按依赖顺序执行。要续跑时可改为某个步骤或其后的步骤列表，前提是前序产物已经齐全。Redis 已由数据导入步骤的 `seed_redis_profiles` 初始化，因此这里不重复执行离线 `ingest`。

默认参数在 `backend/offline/config.py`：3 epochs、batch size 128、embedding 16 维、召回负采样 20、学习率 0.001。网络结构分别在 `train_retrieval.py`（YouTubeDNN `[64, 32]`）和 `train_ranking.py`（DeepFM `[128, 64, 32]`）中配置。MovieLens 是显式评分数据；排序脚本生成的二分类标签及负样本用于离线实验，不能解释为真实曝光点击率。

训练会在终端输出损失与现有评估器的指标，运行时间取决于本机 CPU、Docker 内存与样本量；本次文档整理没有重新执行训练，也没有产生新的质量指标。上述步骤会写入配置的输出目录，已有可用模型时走“复用已有模型”路径，不必重复执行。

部署后至少检查：

```text
artifacts/processed/web_project/deployed_models/
├── vocab_dict.pkl
├── item_embeddings.npy
├── movie_ids.npy
├── ranking/{vocab_dict.pkl,feature_dict.pkl,model_config.pkl}
└── model/
    ├── user_recall/active.json
    ├── user_recall/v1/user_model/saved_model.pb
    ├── ranking/active.json
    └── ranking/v1/ranking_model/saved_model.pb
```

SavedModel 的 `variables/` 目录也必须完整。文件落盘检查不等于推理成功；启动应用后用历史账号发起推荐，检查模型加载日志、YouTubeDNN 通道和 DeepFM 信号。缺少模型时出现的降级结果不能作为训练成功验收。

已有同一数据快照的 `deployed_models/` 时，将 `FUNREC_MODELS_PATH` 指向它即可跳过训练；这只适用于已经持有模型产物的使用者，不是首次下载数据的默认路径。

### 5. 准备语义索引并启动

YouTubeDNN / DeepFM 训练完成后，继续下载 BGE-M3、编码电影内容并固定索引版本，最后启动应用。BGE-M3 使用固定预训练权重，不在本项目重新训练；它的 1024 维语义向量与 YouTubeDNN 的 16 维物品向量是独立产物。具体命令见 [语义编码与索引](REPRODUCE.md#6-语义编码与索引) 和 [前后端启动](REPRODUCE.md#7-前后端启动)。

## 当前本地快照

下表是作者本机 **真实 FunRec / MovieLens-1M 数据及已有模型**的快照。首次下载者需要按上文完成训练；持有同一快照模型者可以跳过。这里不使用虚构电影，也不打包当前应用的聊天记录或账号数据。

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

## 训练代码位置

`backend/offline/feature/`、`backend/offline/training/`、`backend/offline/storage/` 分别负责特征、YouTubeDNN / DeepFM 训练和部署；`backend/offline/pipeline.py` 串联实际步骤。首次构建按上文执行，已有模型可以跳过。本次只补齐文档，不重新训练当前本机模型；研究效果时还需审查样本划分、评分标签与负采样口径。
