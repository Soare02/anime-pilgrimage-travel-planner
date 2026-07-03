import os
import re
import json
import html
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import parse_qs, unquote, urlparse
from dotenv import load_dotenv
import requests
from langchain.tools import tool
from tavily import TavilyClient
from openai import OpenAI
from tavily_config import (
    get_tavily_search_kwargs,
    parse_int_env,
    domain_matches,
    ANIME_SCENE_SITE_QUERIES,
    ANIME_SCENE_VALUE_DOMAINS,
    ANIME_SCENE_TRAVEL_KEYWORDS,
)
load_dotenv()

# MiMo 视觉分析返回值哨兵常量（供 agent.py 跨模块复用，避免硬编码字符串）
MIMO_ERROR_PREFIX = "[MiMo视觉分析异常]"
MIMO_SECTION_HEADER = "[MiMo视觉分析]"
# 配置性失败专用后缀：agent 据此判断是"未配置 key"而非"调用失败"
MIMO_NO_KEY_SUFFIX = "未配置MIMO_API_KEY环境变量"

# MiMo vision client (lazy init)
_mimo_client = None
# 一旦确认缺少 key，置位此 flag，避免每个地标重复尝试初始化并 raise
_mimo_unavailable = False

def _get_mimo_client():
    global _mimo_client
    if _mimo_client is None:
        api_key = os.getenv("MIMO_API_KEY")
        base_url = os.getenv("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
        if not api_key:
            raise ValueError(MIMO_NO_KEY_SUFFIX)
        # max_retries=0：失败已由调用方优雅处理，重试无收益且放大延迟（30s→90s）
        _mimo_client = OpenAI(api_key=api_key, base_url=base_url, timeout=30.0, max_retries=0)
    return _mimo_client

@tool
def get_weather(city: str) -> str:
    """
    通过调用 wttr.in API 查询真实的天气信息。
    """
    # API端点，我们请求JSON格式的数据
    url = f"https://wttr.in/{city}?format=j1"
    
    try:
        # 发起网络请求
        response = requests.get(url)
        # 检查响应状态码是否为200 (成功)
        response.raise_for_status() 
        # 解析返回的JSON数据
        data = response.json()
        
        # 提取当前天气状况
        current_condition = data['current_condition'][0]
        weather_desc = current_condition['weatherDesc'][0]['value']
        temp_c = current_condition['temp_C']
        
        # 格式化成自然语言返回
        return f"{city}当前天气:{weather_desc}，气温{temp_c}摄氏度"
        
    except requests.exceptions.RequestException as e:
        # 处理网络错误
        return f"错误:查询天气时遇到网络问题 - {e}"
    except (KeyError, IndexError) as e:
        # 处理数据解析错误
        return f"错误:解析天气数据失败，可能是城市名称无效 - {e}"

@tool
def get_time()-> str:
    """获取当前时间"""
    return f"当前时间为：5:20:00"

@tool
def get_yg()->str:
    """用户询问妖狗是谁时获取信息"""
    return f"妖狗是一个王者荣耀选手，最喜欢玩韩信"

@tool
def get_attraction(city: str, weather: str) -> str:
    """
    根据城市和天气，使用Tavily Search API搜索并返回优化后的景点推荐。
    """
    # 1. 从环境变量中读取API密钥
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "错误:未配置TAVILY_API_KEY环境变量。"

    # 2. 初始化Tavily客户端
    tavily = TavilyClient(api_key=api_key)
    
    # 3. 构造一个精确的查询
    query = f"'{city}' 在'{weather}'天气下最值得去的旅游景点推荐及理由"
    
    try:
        # 4. 调用API，include_answer=True会返回一个综合性的回答
        response = tavily.search(
            query=query,
            **get_tavily_search_kwargs(search_depth="basic", include_answer=True)
        )
        
        # 5. Tavily返回的结果已经非常干净，可以直接使用
        # response['answer'] 是一个基于所有搜索结果的总结性回答
        if response.get("answer"):
            return response["answer"]
        
        # 如果没有综合性回答，则格式化原始结果
        formatted_results = []
        for result in response.get("results", []):
            formatted_results.append(f"- {result['title']}: {result['content']}")
        
        if not formatted_results:
             return "抱歉，没有找到相关的旅游景点推荐。"

        return "根据搜索，为您找到以下信息:\n" + "\n".join(formatted_results)

    except Exception as e:
        return f"错误:执行Tavily搜索时出现问题 - {e}"


ANIME_SCENE_NOISE_PATTERNS = (
    ".diff", ".patch", ".csv", ".xlsx", ".json", ".xml", ".txt",
    "/commit/", "/raw/", "/blob/", "huggingface.co/datasets", "github.com/commits",
)


def _clean_search_text(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _include_raw_content_enabled(env_name: str, default: str = "1") -> bool:
    return os.getenv(env_name, default).strip().lower() not in {"0", "false", "no", "off"}


def _result_content_with_raw(result: dict, raw_limit: int = 1400) -> str:
    content = _clean_search_text(result.get("content", ""))
    raw_content = _clean_search_text(result.get("raw_content", ""))
    if raw_content and raw_content != content:
        if len(raw_content) > raw_limit:
            raw_content = raw_content[:raw_limit].rstrip() + "..."
        return f"{content}\n正文摘录: {raw_content}" if content else raw_content
    return content


def _dedupe_items(items):
    seen = set()
    deduped = []
    for item in items:
        key = re.sub(r"\s+", " ", item).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item.strip())
    return deduped


def _anime_scene_terms(anime_title, location_name, anime_title_ja, location_name_ja):
    terms = []
    for value in (anime_title, location_name, anime_title_ja, location_name_ja):
        if value and value not in terms:
            terms.append(value)
    return terms


def _build_anime_scene_queries(
    anime_title: str,
    episode: str,
    location_name: str,
    timestamp: str = "",
    anime_title_ja: str = "",
    location_name_ja: str = "",
):
    title = anime_title.strip()
    location = location_name.strip()
    ep = (episode or "").strip()
    ts = (timestamp or "").strip()
    jp_title = (anime_title_ja or "").strip()
    jp_location = (location_name_ja or "").strip()
    # 仅当提供了真实的日文作品名或日文地点名时，才构造日文 query；
    # 否则把中文名塞进日文模板会生成低命中率伪日文 query，浪费 Tavily 预算。
    has_jp_name = bool(jp_title) or bool(jp_location)
    jp_title_for_query = jp_title or title
    jp_location_for_query = jp_location or location

    cn_parts = [f"《{title}》", location, "圣地巡礼"]
    if ep:
        cn_parts.append(ep)
    if ts:
        cn_parts.append(ts)
    cn_parts.append("打卡 场景 攻略")

    queries = [
        ("中文精确", " ".join(cn_parts)),
        ("中文宽松", f"{title} {location} 圣地巡礼 攻略 交通 拍照机位"),
        ("地点优先", f"{location} {title} 巡礼 舞台 取景地 打卡"),
        ("英文", f"{title} {location} anime pilgrimage scene location guide"),
    ]
    if has_jp_name:
        queries.append(("日文通用", f"『{jp_title_for_query}』 {jp_location_for_query} 聖地巡礼 舞台探訪 場面 アクセス"))

    if ep or ts:
        queries.append(("场景片段", f"{title} {location} {ep} {ts} 场景 截图 圣地巡礼"))

    site_base = f"{title} {location} 圣地巡礼 攻略"
    jp_site_base = f"{jp_title_for_query} {jp_location_for_query} 聖地巡礼 舞台探訪"
    for label, site_filter in ANIME_SCENE_SITE_QUERIES:
        if "ameblo.jp" in site_filter or "livedoor.jp" in site_filter:
            # 日文博客站点只有提供了日文名才有意义；否则跳过，避免伪日文 query。
            if has_jp_name:
                queries.append((label, f"{site_filter} {jp_site_base}"))
        else:
            queries.append((label, f"{site_filter} {site_base}"))

    max_queries = parse_int_env("ANIME_SCENE_MAX_QUERIES", 10)
    packed_queries = _dedupe_items([f"{label}\t{query}" for label, query in queries])
    return [tuple(item.split("\t", 1)) for item in packed_queries[:max_queries]]


def _is_noise_search_result(url: str, title: str, content: str) -> bool:
    text = f"{url} {title} {content}".lower()
    if any(pattern in text for pattern in ANIME_SCENE_NOISE_PATTERNS):
        return True
    return "diff --git" in text or "+++ b/" in text


def _score_anime_scene_result(result: dict, core_terms, query: str = "") -> int:
    title = _clean_search_text(result.get("title", ""))
    content = _result_content_with_raw(result)
    url = result.get("url", "") or ""
    text = f"{title} {content} {url}".lower()
    domain = urlparse(url).netloc.lower()

    score = 0
    for term in core_terms:
        term_lower = term.lower()
        if term_lower and term_lower in text:
            score += 3

    if any(keyword.lower() in text for keyword in ANIME_SCENE_TRAVEL_KEYWORDS):
        score += 3
    if any(domain_matches(domain, value_domain) for value_domain in ANIME_SCENE_VALUE_DOMAINS):
        score += 2
    # 只有非 site: 定向 query 的普通结果，才按内容长度给小幅加分；
    # site: 定向 query 的结果本身已通过域名加分体现价值，避免重复奖励。
    if "site:" not in (query or "").lower() and len(content) > 80:
        score += 1
    return score


def _unwrap_duckduckgo_url(url: str) -> str:
    """解包 DDG 跳转链接。若无法解出真实目标 URL（缺 uddg 参数），返回空串由调用方跳过，
    避免把 duckduckgo.com/l/?... 这类跳转链接当成真实结果 URL 污染输出。"""
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    is_ddg_redirect = (
        parsed.path.startswith("/l/")
        and (not parsed.netloc or "duckduckgo.com" in parsed.netloc)
    )
    if is_ddg_redirect:
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        return unquote(target) if target else ""
    return url


def _duckduckgo_html_search(query: str, max_results: int = 5):
    """返回 (results, error)。error 非 None 时表示请求/解析失败，由调用方记入 query_errors。"""
    try:
        response = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Mozilla/5.0 (compatible; anime-travel/1.0)"},
            timeout=8,
        )
        response.raise_for_status()
    except Exception as e:
        return [], f"DDG请求失败: {e}"

    page = response.text
    # 直接匹配 result__a 链接，兼容 href/class 属性顺序和单双引号差异。
    results = []
    link_pattern = re.compile(
        r"<a\b"
        r"(?=[^>]*\bclass\s*=\s*(['\"])[^'\"]*\bresult__a\b[^'\"]*\1)"
        r"(?=[^>]*\bhref\s*=\s*(['\"])(?P<href>.*?)\2)"
        r"[^>]*>(?P<title>.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    snippet_pattern = re.compile(
        r"<(?P<tag>a|div|span)\b"
        r"(?=[^>]*\bclass\s*=\s*(['\"])[^'\"]*\bresult__snippet\b[^'\"]*\2)"
        r"[^>]*>(?P<snippet>.*?)</(?P=tag)>",
        re.IGNORECASE | re.DOTALL,
    )
    matches = list(link_pattern.finditer(page))
    for idx, match in enumerate(matches):
        url = _unwrap_duckduckgo_url(html.unescape(match.group("href")))
        if not url:
            continue
        next_start = matches[idx + 1].start() if idx + 1 < len(matches) else len(page)
        snippet_match = snippet_pattern.search(page, match.end(), next_start)
        title = _clean_search_text(match.group("title"))
        content = _clean_search_text(snippet_match.group("snippet") if snippet_match else "")
        if title and url:
            results.append({"title": title, "url": url, "content": content})
        if len(results) >= max_results:
            break
    return results, None


def _format_anime_scene_results(results, query_errors):
    if not results:
        details = ""
        if query_errors:
            details = "\n检索异常:\n" + "\n".join(f"- {label}: {error}" for label, error in query_errors[:5])
        return "", details

    lines = []
    for index, item in enumerate(results, start=1):
        content = _clean_search_text(item.get("content", ""))
        if len(content) > 420:
            content = content[:420].rstrip() + "..."
        title = _clean_search_text(item.get("title", ""))
        label = item.get("_label", "来源")
        score = item.get("_score", 0)
        if item.get("_synthetic_answer"):
            # 综合回答没有独立可访问 URL，输出为"Tavily 综合回答"，避免暴露伪 URL
            lines.append(f"{index}. 【{label}｜相关性{score}】{title}\n   来源: Tavily 综合回答\n   摘要: {content}")
        else:
            url = item.get("url", "")
            lines.append(f"{index}. 【{label}｜相关性{score}】{title}\n   URL: {url}\n   摘要: {content}")

    if query_errors:
        lines.append("\n检索异常（已自动跳过）:")
        lines.extend(f"- {label}: {error}" for label, error in query_errors[:5])
    return "\n".join(lines), ""


@tool
def get_anime_scene(
    anime_title: str,
    episode: str,
    location_name: str,
    timestamp: str = "",
    anime_title_ja: str = "",
    location_name_ja: str = "",
) -> str:
    """
    查询动漫中某个特定场景的剧情细节、时间氛围和情节内容。
    模型可根据返回的场景信息（如黄昏、夜晚、雨天等氛围）调整巡礼路线的时间安排。

    Args:
        anime_title: 作品名称，如"吹响吧！上低音号"
        episode: 集数，如"EP1"、"第3集"
        location_name: 地点名称，如"宇治桥"、"大吉山展望台"
        timestamp: 时间戳，如"0:25"、"11:45"
        anime_title_ja: 作品日文原名
        location_name_ja: 地点日文原名
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "错误:未配置TAVILY_API_KEY环境变量。"

    tavily = TavilyClient(api_key=api_key)

    try:
        queries = _build_anime_scene_queries(
            anime_title=anime_title,
            episode=episode,
            location_name=location_name,
            timestamp=timestamp,
            anime_title_ja=anime_title_ja,
            location_name_ja=location_name_ja,
        )
        responses = []
        query_errors = []
        with ThreadPoolExecutor(max_workers=min(len(queries), 4)) as executor:
            future_to_label = {
                executor.submit(
                    tavily.search,
                    query=query,
                    **get_tavily_search_kwargs(
                        search_depth="advanced",
                        include_answer=True,
                        max_results=6,
                        include_raw_content=_include_raw_content_enabled("ANIME_SCENE_INCLUDE_RAW_CONTENT", "1"),
                    )
                ): (label, query)
                for label, query in queries
            }
            for future in as_completed(future_to_label):
                label, query = future_to_label[future]
                try:
                    responses.append((label, query, future.result()))
                except Exception as e:
                    query_errors.append((label, str(e)))

        scored_results = []
        seen_urls = set()
        core_terms = _anime_scene_terms(anime_title, location_name, anime_title_ja, location_name_ja)
        for label, query, response in responses:
            answer = response.get("answer")
            if answer:
                synthetic = {
                    "title": f"{label}综合回答",
                    "url": f"tavily://answer/{label}",
                    "content": answer,
                    "_label": label,
                    "_synthetic_answer": True,
                }
                # 综合回答是 Tavily 最精炼的摘要，给保底分避免被普通结果 >=3 阈值误杀。
                synthetic["_score"] = max(_score_anime_scene_result(synthetic, core_terms, query), 5)
                scored_results.append(synthetic)
            for result in response.get("results", []):
                url = result.get("url", "")
                if not url:
                    continue
                if url in seen_urls:
                    continue
                title = result.get("title", "")
                content = _result_content_with_raw(result)
                if _is_noise_search_result(url, title, content):
                    continue
                seen_urls.add(url)
                item = dict(result)
                item["content"] = content
                item["_label"] = label
                item["_query"] = query
                item["_score"] = _score_anime_scene_result(item, core_terms, query)
                scored_results.append(item)

        useful_results = [item for item in scored_results if item.get("_score", 0) >= 3]
        if len(useful_results) < 3 and os.getenv("ANIME_SCENE_ENABLE_DDG_FALLBACK", "1") != "0":
            fallback_queries = queries[:3]
            with ThreadPoolExecutor(max_workers=min(len(fallback_queries), 3)) as executor:
                future_to_label = {
                    executor.submit(_duckduckgo_html_search, query, 4): (label, query)
                    for label, query in fallback_queries
                }
                for future in as_completed(future_to_label):
                    label, query = future_to_label[future]
                    try:
                        ddg_results, ddg_error = future.result()
                    except Exception as e:
                        ddg_results, ddg_error = [], f"DDG异常: {e}"
                    if ddg_error:
                        query_errors.append((f"DDG/{label}", ddg_error))
                        continue
                    for result in ddg_results:
                        url = result.get("url", "")
                        if not url:
                            continue
                        if url in seen_urls:
                            continue
                        if _is_noise_search_result(url, result.get("title", ""), result.get("content", "")):
                            continue
                        seen_urls.add(url)
                        result["_label"] = f"DDG备用/{label}"
                        result["_query"] = query
                        result["_score"] = _score_anime_scene_result(result, core_terms, query)
                        if result["_score"] >= 3:
                            useful_results.append(result)

        useful_results.sort(key=lambda item: item.get("_score", 0), reverse=True)
        formatted, extra = _format_anime_scene_results(useful_results[:12], query_errors)

        if not formatted:
            searched = "\n".join(f"- {label}: {query}" for label, query in queries)
            return (
                f"未找到《{anime_title}》{episode}中{location_name}的相关场景信息。\n"
                f"已尝试以下查询:\n{searched}{extra}"
            )

        searched = "；".join(f"{label}" for label, _ in queries)
        return f"为您找到以下场景信息（查询策略: {searched}）:\n{formatted}"

    except Exception as e:
        return f"错误:搜索场景信息时出现问题 - {e}"


TOOLS = [get_weather, get_attraction, get_anime_scene]


def analyze_anime_scene_image(image_url: str, location_name: str, anime_title: str, extra_context: str = "") -> str:
    """
    使用 MiMo v2.5 视觉模型分析动漫截图，提取场景光照、时段、角度、构图等细节。
    返回结构化的视觉分析文本，可直接注入地标的 final_info。

    Args:
        image_url: Anitabi 返回的动漫截图 URL
        location_name: 地标名称（如"宇治桥"）
        anime_title: 动漫作品名称（如"吹响吧！上低音号"）
        extra_context: 额外的文字上下文（RAG/Tavily 检索结果摘要）
    """
    global _mimo_unavailable
    # 若此前已确认缺少 key，直接快速返回，避免重复 raise（每地标都触发）
    if _mimo_unavailable:
        return f"{MIMO_ERROR_PREFIX} {MIMO_NO_KEY_SUFFIX}"

    try:
        client = _get_mimo_client()
    except ValueError as e:
        _mimo_unavailable = True
        return f"{MIMO_ERROR_PREFIX} {str(e)}"

    model = os.getenv("MIMO_MODEL", "mimo-v2.5")

    ctx_block = f"\n已知文字背景：{extra_context[:300]}" if extra_context else ""

    prompt = f"""请仔细分析这张动漫截图，这是《{anime_title}》中"{location_name}"的场景。{ctx_block}

请从以下维度输出你的分析（中文），必须严格用 ```json 包裹：

1. lighting: 光线特征（逆光/顺光/侧光/金色暖光/冷色蓝调/阴天漫射光…）
2. time_of_day: 画面时段（清晨/上午/正午/午后/黄昏/夜晚）
3. season: 季节特征（春樱/夏绿/秋红叶/冬雪/室内无季节）
4. camera_angle: 拍摄角度（仰角/俯角/平视）和大致朝向（面朝东/西/南/北…）
5. key_elements: 画面核心元素（建筑风格、植被、标志物、角色站位…）
6. composition: 构图分析（画面各元素的相对位置）
7. photo_guide: 还原此镜头的拍摄建议（站位、焦段、角度、注意事项）

请务必只返回 JSON 块。"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}}
                    ]
                }
            ],
            temperature=0.3,
            max_tokens=1500
        )
        raw = response.choices[0].message.content

        # 尝试解析 JSON 并格式化为可读文本，便于下游 DeepSeek 消费
        match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(1).strip())
                labels = {
                    "lighting": "光线特征", "time_of_day": "画面时段",
                    "season": "季节特征", "camera_angle": "拍摄角度",
                    "key_elements": "核心元素", "composition": "构图分析",
                    "photo_guide": "拍照还原建议"
                }
                lines = []
                for key, label in labels.items():
                    val = data.get(key)
                    if val:
                        lines.append(f"- {label}: {val}")
                if lines:
                    return "\n".join(lines)
            except Exception:
                pass

        return raw
    except Exception as e:
        return f"{MIMO_ERROR_PREFIX} {str(e)}"
