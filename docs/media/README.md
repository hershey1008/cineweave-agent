# 演示视频与截图

视频：**CineWeave 真实界面演示，约 2 分 10 秒，1920×1080 / 24 fps，H.264 + AAC**。

观看与下载：[GitHub Release](https://github.com/hershey1008/cineweave-agent/releases/tag/v0.1.0-demo)。MP4 作为 Release 附件发布，不放入 Git 历史。中文字幕、封面、画面和制作脚本随源码提供。

## 制作口径

- 使用实际本机应用截图，演示账号为公开 MovieLens 历史用户对应的本地演示身份。
- 视频中的五轮操作均通过真实 LLM 完成；BGE-M3、协同通道和 DeepFM 来自实际运行服务。
- 这是截图剪辑与讲解，**不是连续录屏**。请求等待时间已省略，不用剪辑时长代表系统延迟。
- 中文字幕与 Microsoft Huihui 本地合成旁白，无背景音乐、密钥、真实个人账号或内部日志。
- 电影海报和简介保留第三方权利；这里只展示应用界面，不授权二次使用影视素材。

## 场景

1. 应用首页与定位。
2. 提出太空探索、科幻、120 分钟以内、排除恐怖的需求。
3. 查看真实 LLM 与混合召回链路。
4. “轻松一点，其他要求不变”。
5. 将上一轮第三部 Gattaca 排除并替换。
6. 取消片长上限，保留其余条件。
7. 解释上一轮第一部。
8. 展开电影资料与事实字段。
9. 代码入口、复现与结果边界。

## 本机重新制作

脚本需要 Windows 的 Microsoft YaHei 字体、Huihui 语音引擎；应用本身的部署不依赖这些视频制作工具。

```powershell
python -m pip install -r requirements-video.txt
.\scripts\make_demo_narration.ps1
python scripts/make_demo_video.py
```

输入：`video-plan.json`、`screenshots/*.png`。中间音频和编码帧位于忽略的 `.runtime/`；输出 MP4、SRT、封面和 `video-manifest.json`。完整视频已进行解码检查，并抽取多个章节画面进行排版核验；语音为本机 TTS 合成。
