# 来源、数据与状态边界

## 项目来源

CineWeave（影织）扩展 [Datawhale FunRec](https://github.com/datawhalechina/fun-rec) 的电影推荐 Web 项目。本仓库承载新增应用代码、设计、测试与演示材料，与已有 `movie_recsystem` 区分。

2026-10-19 检查原本地 FunRec 的召回、在线流水线、DeepFM 输入、数据库字段、API、前端 API、依赖和 Compose，形成设计基线。2026-10-20 完成本地 V1 实现和真实 LLM 小规模联调；复用与新增见 [CONTRIBUTIONS.md](CONTRIBUTIONS.md)。

初始提交仅包含设计文档。发布整理保留了上游 README 声明的 CC BY-NC-SA 4.0 许可、完整许可文本与修改说明，见根目录 `LICENSE`、`THIRD_PARTY_NOTICES.md`。原始数据、模型权重和凭据不包含在发布源码中；第三方资产保留其自身条件。

## 原始数据与扩充数据

原始 MovieLens-1M 包含电影基本信息、显式评分与用户信息，不能视为原生曝光/点击日志。完整剧情简介、片长、演职员信息并非原始 1M 的标准电影字段。

当前本地 FunRec 使用扩充后的 `movies.pkl` 和 `movie_metadata.pkl`。2026-10-19 实际读取检查结果：

| 项目 | 结果 |
| --- | ---: |
| 电影总数 | 3883 |
| 非空简介 | 3882 |
| IMDb ID 非空 | 3883 |
| 类型非空 | 3883 |
| 原始片名非空 | 3881 |
| 年份非空 | 3881 |
| 有效正数片长 | 3689 |
| 简介含 HTML 实体 | 944 |
| 重复 movie_id | 0 |

元数据包含主创、主要演职员、人物基础信息、电影别名和 IMDb 评分表。计数是对该本地快照的字段审计；非空不等于事实正确，简介具体采集来源本次未追溯，也没有逐条核验。所有数据仍需在索引构建时重新检查。

## 参考资料

- [MovieLens 1M 官方数据页](https://grouplens.org/datasets/movielens/1m/)
- [TensorFlow Datasets 的 MovieLens 字段说明](https://www.tensorflow.org/datasets/catalog/movie_lens)
- [BGE-M3 官方模型卡](https://huggingface.co/BAAI/bge-m3)：多语言、1024 维，V1 初始嵌入选型。
- [FunRec Web 项目](https://github.com/datawhalechina/fun-rec/tree/master/web_project)：原多阶段电影推荐链路。
- [TMDB 外部 ID 查询](https://developer.themoviedb.org/reference/find-by-id)：后续可用于缺失资料补充，不是 V1 必须新增的数据依赖。

后续下载或发布数据时检查对应数据源使用条件。此仓库不会通过提交数据包绕过数据源条件。

2026-10-20 整理了本地原有扩充快照、海报、已有推荐模型和活动语义索引的本地备份包，未重新训练。用户确认尚未取得再分发授权，因此不上传公开仓库或 Release；文件格式和恢复流程见 [DATA_AND_MODELS.md](DATA_AND_MODELS.md)。此包不含当前应用的聊天记录、账号数据库或 API 配置。

## 结果表述

本地实现按用户约定支持无 API 的规则演示模式，配合真实语义模型和原推荐模型。实际执行结果见本地验收记录；不把规则测试表述为真实 LLM 效果，不把输入草案表述为已完成人工相关性标注，也不把预训练模型复用表述为重新训练。

进一步检查发现：源数据中 3532 条的 `titleType` 为 `movie`；其余 351 条包含游戏、剧集、短片等不同类型。V1 对其保守隔离，不使用这些外部字段执行电影内容推荐。原始数据保留；该过滤仍不是完整的实体匹配人工审计。
