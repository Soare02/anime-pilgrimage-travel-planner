import os
from dotenv import load_dotenv
import requests
from langchain.tools import tool
from tavily import TavilyClient
from openai import OpenAI
load_dotenv()

# MiMo vision client (lazy init)
_mimo_client = None

def _get_mimo_client():
    global _mimo_client
    if _mimo_client is None:
        api_key = os.getenv("MIMO_API_KEY")
        base_url = os.getenv("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
        if not api_key:
            raise ValueError("未配置MIMO_API_KEY环境变量")
        _mimo_client = OpenAI(api_key=api_key, base_url=base_url, timeout=30.0)
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
        response = tavily.search(query=query, search_depth="basic", include_answer=True)
        
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
    
@tool
def get_anime_scene(anime_title: str, episode: str, location_name: str, timestamp: str = "") -> str:
    """
    查询动漫中某个特定场景的剧情细节、时间氛围和情节内容。
    模型可根据返回的场景信息（如黄昏、夜晚、雨天等氛围）调整巡礼路线的时间安排。

    Args:
        anime_title: 作品名称，如"吹响吧！上低音号"
        episode: 集数，如"EP1"、"第3集"
        location_name: 地点名称，如"宇治桥"、"大吉山展望台"
        timestamp: 时间戳，如"0:25"、"11:45"
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "错误:未配置TAVILY_API_KEY环境变量。"

    parts = [f"动画《{anime_title}》", episode, location_name]
    if timestamp:
        parts.append(f"第{timestamp}左右的剧情")
    parts.append("场景描写 时间 氛围 情节")
    query = " ".join(parts)

    tavily = TavilyClient(api_key=api_key)

    try:
        response = tavily.search(query=query, search_depth="basic", include_answer=True)

        if response.get("answer"):
            return response["answer"]

        formatted_results = []
        for result in response.get("results", []):
            formatted_results.append(f"- {result['title']}: {result['content']}")

        if not formatted_results:
            return f"未找到《{anime_title}》{episode}中{location_name}的相关场景信息。"

        return "为您找到以下场景信息:\n" + "\n".join(formatted_results)

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
    client = _get_mimo_client()
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
        import re, json as _json
        match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
        if match:
            try:
                data = _json.loads(match.group(1).strip())
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
        return f"[MiMo视觉分析异常] {str(e)}"
