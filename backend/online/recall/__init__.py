"""

多通道召回模块

本模块提供多通道召回用于推荐流水线。
从多个来源检索多样化的候选。

主要组件:
- RecallService: 协调召回策略
- RecallStrategy: 召回策略基类
- YouTubeDNNRecallStrategy: 深度学习召回
- UserPreferenceRecallStrategy: 用户偏好召回
- ItemEmbeddingRecallStrategy: 物品相似度召回
"""

from .base import RecallStrategy


def get_recall_service():
    from .service import get_recall_service as factory
    return factory()


def __getattr__(name):
    if name == "RecallService":
        from .service import RecallService
        return RecallService
    raise AttributeError(name)

__all__ = [
    "get_recall_service",
    "RecallService",
    "RecallStrategy",
]
