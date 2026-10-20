# 数据与模型

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

**数据包仅在本地保存，尚未上传到公开 GitHub 或 Release。** MovieLens 官方条款要求单独取得再分发许可；当前尚未取得。扩充简介、海报、IMDb 关联的来源与分发条件还需核对。将数据处理为 pickle 不代表可以按本仓库代码许可重新授权。

- [MovieLens-1M 官方入口](https://grouplens.org/datasets/movielens/1m/)
- [官方数据使用条款](https://files.grouplens.org/datasets/movielens/ml-1m-README.txt)
- [FunRec Web 项目与数据准备说明](https://github.com/datawhalechina/fun-rec/tree/master/web_project)
- [本地扩充字段审计](provenance.md)

使用者应自行准备获准使用的同结构快照。当前 README 不承诺仅克隆源码即可取得完整演示数据，也没有不可用的数据包下载链接。

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
