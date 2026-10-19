# 来源、数据与状态边界

## 项目来源

CineWeave（影织）计划扩展 [Datawhale FunRec](https://github.com/datawhalechina/fun-rec) 的电影推荐 Web 项目。当前仓库是新的文档和后续代码承载仓库，与已有 `movie_recsystem` 区分。

2026-10-19 已检查原本地 FunRec 的召回、在线流水线、DeepFM 输入、数据库字段、API、前端 API、依赖和 Compose。上述源码检查用于制定方案，不表示本仓库已包含或实现这些模块。

本次初始化不复制上游应用源码，不上传原始数据、模型、凭据或用户信息。后续引入代码前，核对所用上游版本的许可并保留必要版权与许可文件。当前未为尚未实现的整体应用指定开源许可证。

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

## 结果表述

当前只有技术方案。尚无 CineWeave 的训练、服务启动、测试集运行、检索指标、线上反馈或性能结果。验收文档中的数字为目标，未来必须用可复现报告支撑。
