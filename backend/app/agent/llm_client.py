import asyncio
import json
import os
import re
import time

import httpx

from .prompts import INTENT_SYSTEM
from .schemas import IntentPatch, SessionState
from .timeouts import llm_timeout_seconds

GENRE_WORDS = {"科幻": "Sci-Fi", "喜剧": "Comedy", "恐怖": "Horror", "悬疑": "Mystery",
               "惊悚": "Thriller", "动画": "Animation", "爱情": "Romance", "动作": "Action",
               "冒险": "Adventure", "奇幻": "Fantasy", "犯罪": "Crime", "战争": "War",
               "纪录": "Documentary", "儿童": "Children's", "剧情": "Drama", "西部": "Western"}
THEMES = {"虚拟现实": "virtual reality, simulated world, reality and identity",
          "烧脑": "mind-bending, complex narrative, mystery and unexpected twists",
          "轻松": "lighthearted, uplifting, humorous and playful",
          "治愈": "heartwarming, friendship, hope and kindness",
          "太空": "space exploration, astronauts, interstellar adventure",
          "机器人": "robots, artificial intelligence, human and machine",
          "人工智能": "artificial intelligence, sentient machines",
          "梦境": "dreams, subconscious, reality and illusion",
          "家庭": "family relationships, parents and children",
          "友谊": "friendship, loyalty and companionship",
          "成长": "coming of age, personal growth",
          "魔法": "magic, fantasy, enchanted adventure",
          "时间旅行": "time travel, changing the past, temporal paradox",
          "压抑": "dark, bleak, oppressive atmosphere",
          "温暖": "warmhearted, uplifting, kindness"}
NUMERALS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def numeral(value):
    return int(value) if value.isdigit() else NUMERALS.get(value, 0)


def parse_rules(text: str, state: SessionState) -> IntentPatch:
    """Explicit local demo parser. Never labelled as an LLM."""
    patch = IntentPatch()
    if re.search(r"(?:其他人|别人).*(?:会话|聊天|记录|密码)", text):
        return IntentPatch(action="clarify", question="我只能访问你自己的选片会话。请描述你的电影需求。")
    if re.search(r"重新开始|清空(?:所有|全部|本次)?条件|重置条件", text):
        patch.action = "reset"
        return patch
    if re.search(r"绝对.*(?:血腥|暴力|儿童)|保证.*(?:没有|无)|零血腥", text):
        return IntentPatch(action="clarify", question="当前资料无法保证逐镜头内容。可以改为排除恐怖、惊悚类型，或提供可核验的其他条件吗？")
    if re.search(r"不要太长|别太长|时长短一点", text) and not re.search(r"分钟|小时", text):
        return IntentPatch(action="clarify", question="你希望电影最多多少分钟？例如 90 分钟或 120 分钟。")
    if re.search(r"(?:至少|最少|不少于|不短于|恰好|正好)[^，。]{0,8}(?:分钟|小时)|(?:分钟|小时)以上", text):
        return IntentPatch(action="clarify", question="当前支持片长上限筛选。请说明最多多少分钟，或取消时长条件。")
    lower = re.findall(r"(\d{4})年?(?:以后|之后|以来)", text)
    upper = re.findall(r"(\d{4})年?(?:以前|之前)", text)
    if lower and upper and max(map(int, lower)) > min(map(int, upper)):
        return IntentPatch(action="clarify", question="年份条件有冲突，请确认起始和结束年份。")
    for position in re.findall(r"第([一二两三四五六七八九十\d]+)(?:部|个|张)", text):
        n = numeral(position)
        if n:
            patch.exclude_positions.append(n)
    if patch.exclude_positions:
        patch.action = "explain" if re.search(r"为什么|解释|理由", text) else "replace"
    patch.reference_titles = re.findall(r"《([^》]+)》", text)
    include, exclude = list(state.include_genres), list(state.exclude_genres)
    genre_change = False
    if "类型不限" in text:
        patch.clear_fields += ["include_genres", "exclude_genres"]
    for word, genre in GENRE_WORDS.items():
        if word not in text:
            continue
        genre_change = True
        if re.search(r"(?:取消排除|可以看|不再排除)[^，。；,;]{0,5}" + word, text):
            exclude = [g for g in exclude if g != genre]
        elif re.search(r"(?:不要|不看|排除|别推荐|不喜欢)[^，。；,;]{0,8}" + word, text):
            exclude = list(dict.fromkeys(exclude + [genre]))
            include = [g for g in include if g != genre]
        else:
            include = list(dict.fromkeys(include + [genre]))
            exclude = [g for g in exclude if g != genre]
    if "改成" in text or "换成" in text:
        positive = [g for w, g in GENRE_WORDS.items() if w in text and g in include]
        if positive:
            include = positive
    if genre_change:
        patch.set_fields.update(include_genres=include, exclude_genres=exclude)
    if re.search(r"时长不限|时间不限|取消.*时长|不限制.*时长", text):
        patch.clear_fields.append("runtime_max")
    else:
        minutes = re.search(r"(\d{1,3})\s*分钟", text)
        hours = re.search(r"([一二两三四五六七八九十\d.]+)(?:个)?小时", text)
        if "一个半小时" in text or "一小时半" in text:
            patch.set_fields["runtime_max"] = 90
        elif minutes:
            patch.set_fields["runtime_max"] = int(minutes.group(1))
        elif hours:
            value = hours.group(1)
            patch.set_fields["runtime_max"] = int((float(value) if re.fullmatch(r"[\d.]+", value) else numeral(value)) * 60)
    if re.search(r"年代不限|年份不限|取消.*年份|取消.*年代", text):
        patch.clear_fields += ["year_min", "year_max"]
    else:
        year_range = re.search(r"(\d{4})\s*年?\s*(?:到|至|[-~—])\s*(\d{4})", text)
        decade = re.search(r"(\d{2}|\d{4})年代", text)
        year = re.search(r"(\d{4})年?(以前|之前|以后|之后|以来)?", text)
        if year_range:
            patch.set_fields.update(year_min=int(year_range.group(1)), year_max=int(year_range.group(2)))
        elif decade:
            start = int(decade.group(1))
            start = start + (1900 if start >= 20 else 2000) if start < 100 else start
            patch.set_fields.update(year_min=start, year_max=start + 9)
        elif year:
            value, relation = int(year.group(1)), year.group(2)
            if relation in {"以前", "之前"}:
                patch.set_fields["year_max"] = value
            elif relation:
                patch.set_fields["year_min"] = value
            else:
                patch.set_fields.update(year_min=value, year_max=value)
    if re.search(r"看过.*(?:也可以|可以)|不用排除看过|包含看过", text):
        patch.set_fields["exclude_seen"] = False
    elif re.search(r"不要.*看过|排除.*看过|没看过", text):
        patch.set_fields["exclude_seen"] = True
    themes = [english for word, english in THEMES.items() if word in text]
    if themes:
        base = state.semantic_query
        if "不压抑" in text or "不要太压抑" in text:
            themes = [t for t in themes if t != THEMES["压抑"]] + ["uplifting, hopeful"]
        patch.set_fields["semantic_query"] = "; ".join(dict.fromkeys(([base] if base else []) + themes))[-1800:]
    elif not state.semantic_query and patch.action == "recommend":
        positive_genres = " ".join(include)
        patch.set_fields["semantic_query"] = positive_genres or text
    if state.semantic_query and not (patch.set_fields or patch.clear_fields or patch.exclude_positions or patch.reference_titles):
        if re.search(r"换一组|再来一组|另外几部", text) and state.last_recommendation_ids:
            patch.action = "replace"
            patch.exclude_positions = list(range(1, len(state.last_recommendation_ids) + 1))
        else:
            return IntentPatch(action="clarify", question="本地演示还不能可靠理解这次修改。请明确类型、年份、最大片长，或使用“轻松一点”“第三部换掉”等表达。")
    return patch


class LLMServiceError(Exception):
    """Safe public error; never forward provider bodies or credentials."""
    def __init__(self, detail, *, status_code=503, kind="unavailable"):
        super().__init__(detail)
        self.status_code = status_code
        self.kind = kind


class LLMClient:
    @property
    def mode(self):
        return "llm" if os.getenv("LLM_API_KEY") and os.getenv("LLM_MODEL") else "rules"

    async def parse(self, text: str, state: SessionState):
        if self.mode == "rules":
            return parse_rules(text, state), {"mode": "rules", "calls": 0, "tokens": 0}
        base = os.getenv("LLM_BASE_URL", "").rstrip("/")
        if not base.startswith(("https://", "http://localhost:", "http://127.0.0.1:")):
            raise ValueError("请配置可信的 LLM_BASE_URL")
        messages = [{"role": "system", "content": INTENT_SYSTEM},
                    {"role": "user", "content": json.dumps({"state": state.model_dump(), "message": text}, ensure_ascii=False)}]
        budget = llm_timeout_seconds()
        tokens = 0
        started = time.perf_counter()
        try:
            # The first call and optional JSON repair share one total deadline.
            # Timeout/network failures are not automatically retried or relabelled as rules.
            async with asyncio.timeout(budget):
                async with httpx.AsyncClient(timeout=httpx.Timeout(budget, connect=min(5, budget)), trust_env=False) as client:
                    for attempt in range(2):
                        response = await client.post(base + "/chat/completions",
                            headers={"Authorization": "Bearer " + os.environ["LLM_API_KEY"]},
                            json={"model": os.environ["LLM_MODEL"], "messages": messages,
                                  "temperature": 0, "response_format": {"type": "json_object"}})
                        response.raise_for_status()
                        try:
                            data = response.json()
                            content = data["choices"][0]["message"]["content"]
                            if not isinstance(content, str):
                                raise TypeError("Expected string content")
                        except (ValueError, KeyError, IndexError, TypeError):
                            raise LLMServiceError("LLM 接口响应格式不兼容，请检查服务商接口与模型配置。", status_code=502, kind="protocol") from None
                        usage = data.get("usage") or {}
                        used = usage.get("total_tokens", 0) if isinstance(usage, dict) else 0
                        tokens += used if isinstance(used, int) else 0
                        try:
                            patch = IntentPatch.model_validate_json(content)
                            return patch, {"mode": "llm", "calls": attempt + 1, "tokens": tokens,
                                "model": os.environ["LLM_MODEL"], "timeout_seconds": budget,
                                "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)}
                        except (ValueError, TypeError):
                            messages += [{"role": "assistant", "content": content},
                                {"role": "user", "content": "输出不符合约定，请只返回符合字段定义的 JSON。"}]
        except (TimeoutError, httpx.TimeoutException):
            raise LLMServiceError(f"LLM 响应超时（本轮等待预算 {budget:g} 秒），本轮未保存，请稍后重试。", status_code=504, kind="timeout") from None
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in {401, 403}:
                detail, kind = "LLM 鉴权失败，请检查 API 密钥与模型访问权限。", "authentication"
            elif status == 429:
                detail, kind = "LLM 服务商限流或额度不足，请稍后重试或检查服务商账户。", "rate_limit"
            elif status in {400, 404, 422}:
                detail, kind = "LLM 服务商拒绝了请求，请检查接口地址、模型 ID 与 JSON 输出支持。", "configuration"
            else:
                detail, kind = "LLM 服务商暂不可用，请稍后重试。", "provider"
            raise LLMServiceError(detail, kind=kind) from None
        except httpx.RequestError:
            raise LLMServiceError("无法连接 LLM 服务，请检查接口地址和网络后重试。", kind="connection") from None
        raise LLMServiceError("LLM 连续返回无效意图结构，本轮未保存，请重试。", status_code=502, kind="invalid_output")
