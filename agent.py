import os
import re
import json
import queue
import threading
import operator
from typing import Annotated, List, Dict, Any, TypedDict
from dotenv import load_dotenv

from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, END

# Import tools from workspace
from tools import get_anime_scene, get_weather, analyze_anime_scene_image

load_dotenv()

# Initialize DeepSeek Chat Model
llm_deepseek = init_chat_model(
    model="deepseek-v4-flash",
    base_url="https://api.deepseek.com",
    temperature=0.8,
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    model_provider="openai", 
    model_kwargs={"extra_body": {"thinking": {"type": "disabled"}}}
)

# ----------------- Prompts -----------------

PARSER_PROMPT = """
你是一个专业的数据解析助手。你的任务是仅从用户输入文本中“## 用户规划任务请求”部分的“需要访问的地标”列表中提取出巡礼规划要求和地标列表，并与给定的 RAG Context 进行关联。

【重要规则】
1. 绝对不允许从“## 检索到的巡礼背景与攻略知识 (RAG Context)”中提取任何不在“## 用户规划任务请求”列表中的额外地标。所提取的地标数量和名称必须与“需要访问的地标”列表完全一致。
2. “RAG Context”仅用于为所提取的这些地标匹配并填充“rag_info”字段。

输入文本：
{data_text}

请输出一个 JSON 对象，必须包含以下字段：
1. "days": 整数，代表巡礼的天数。
2. "landmarks": 一个对象列表，每个对象代表一个地标，包含以下字段：
   - "id": 整数，地标的序号（1, 2, 3...）
   - "name": 字符串，地标名称（例如："宇治桥"）
   - "bangumi": 字符串，动漫作品名称（例如："吹响吧！上低音号"）
   - "ep": 字符串，出现集数（如 "EP1"、"第3集"，若未提供则为 null）
   - "timestamp": 字符串，时间戳（如 "0:25"、"11:45"，若未提供则为 null）
   - "geo": 字符串，坐标（如 "34.8903, 135.8002"，若未提供则为 null）
   - "image": 字符串，Anitabi 动漫截图 URL（若用户输入中提供了"截图URL"字段则提取，否则为 null）
   - "rag_info": 字符串，如果在输入文本顶部的 "## 检索到的巡礼背景与攻略知识 (RAG Context)" 中有关于该地标的详细攻略、交通、最佳机位或名场面描写，请将该地标的全部相关背景内容提取并填入此处。如果 RAG Context 中没有提及该地标，或者只有一句话带过没有详细攻略，请填 null。

请务必只返回 JSON 块，并用 ```json 和 ``` 包裹。
"""

RELEVANCE_CHECK_PROMPT = """
你是一个动漫圣地巡礼验证专家。
请仔细评估以下检索到的网页搜索结果，判断其是否与地标 "{name}" 在动漫《{bangumi}》（集数: {ep}, 时间戳: {timestamp}）中的圣地巡礼打卡场景真实相关。

有些搜索结果可能包含无关的广告、泛泛的旅游攻略、同名但不同城市的地方、或者其他完全不相关的动漫。

网页搜索结果内容：
{search_result}

请输出一个 JSON 对象，包含以下字段：
1. "relevant": 布尔值（true 或 false），如果搜索结果确实包含关于该地标在《{bangumi}》中的名场面细节、巡礼攻略、交通路线或拍照机位，则为 true；否则（如纯广告、无关博客、非该动漫内容等）为 false。
2. "reason": 字符串，简短说明判定相关或不相关的理由。
3. "extracted_details": 字符串，如果相关，请从搜索结果中提取并整理出关于该地标的圣地巡礼有用信息（如具体地址、最近车站交通、名场面背景、最佳打卡时段、拍照角度、注意事项等）。如果判定为不相关，则该字段必须为 null。

请务必只返回 JSON 块，并用 ```json 和 ``` 包裹。
"""

ROUTING_PROMPT = """
你是一个专业的空间路由与交通规划专家。
你的任务是将补全后的地标列表，按照地理区域和空间距离，合理分配到 {days} 天的行程中。

目的地主要城市天气状况：
{weather_info}

地标详细数据（已完成联网检索与 RAG 补全）：
{landmarks_json}

主编打回的修改意见（若为“无”则忽略）：
{errors_text}

规则与要求：
1. **地理区域优先**：必须计算经纬度距离，将相近的点位划分在同一天，绝对禁止在同一天出现跨度极大（如京都和东京、或宇治和京都市区严重折返）的不合理路线。
2. **合理天数排布**：将所有地标平均或合理分配到 {days} 天中，并确保每一天的步行距离适中（单日推荐 6-10km，最大不超过 15km）。
3. **交通动线闭环**：每天的路线需要有起点站和终点站，按照「车站 -> 地标1 -> 地标2 -> ... -> 返程车站」的闭环排布。
4. **天气适配**：参考天气信息（{weather_info}），如果是雨雪等恶劣天气，请增加室内点位比例，或提供更详尽的轨道交通/巴士接驳建议。
5. **输出格式**：你必须以 JSON 格式输出你的规划大纲，不要输出任何 markdown 文本，以便下阶段的动漫专家加工。

请输出一个 JSON 对象，包含以下字段：
{{
  "days": [
    {{
      "day_number": 1,
      "region": "当日巡礼核心区域名称（如：京都宇治市）",
      "route_sequence": ["起点站", "地标1名称", "地标2名称", "返程站"],
      "transit_details": "详细的每日交通衔接描述，包含乘坐的铁路线、巴士、步行距离估算等",
      "landmarks": [
        # 按游览顺序排列的地标对象列表。必须保留输入中该地标的全部字段（包括 image, geo, final_info, ep 等），可额外添加 "visit_order" 字段
      ]
    }}
  ]
}}

请务必只返回 JSON 块，并用 ```json 和 ``` 包裹。
"""

ANIME_EXPERT_PROMPT = """
你是一个动漫原画与圣地巡礼名场面还原专家。
你的任务是为交通专家规划好的每日大纲注入“动漫情怀”与“拍照还原指南”。

空间交通规划大纲：
{routing_draft_json}

规则与要求：
1. **名场面时段还原优先**：检查每个地标在原作中的时间氛围（如清晨、黄昏、夜景等）。在不破坏交通专家划分的“同城同区域”大原则的前提下，微调同一天内点位的游览顺序，尽量让名场面在对应时段被访问（例如：黄昏时登大吉山展望台，晚上去京都车站）。
2. **打卡拍照指南**：对每个地标，结合其补全信息，给出最佳摄影角度（如：站在宇治桥西侧桥头往东拍）、镜头焦段建议、圣地还原的经典 Pose 动作建议（如：模仿久美子双手抱头、还原名台词等）。
3. **情怀与礼仪贴士**：补充相关的粉丝文化和当地礼仪（如：在宇治神社打卡时保持安静，不要打扰附近居民，或者吹奏部打卡礼仪）。
4. **不要破坏地理分组**：不得将地标跨天乱调，必须保留交通专家分配的每日地标组合。

请输出一个 JSON 对象，包含以下字段：
{{
  "days": [
    {{
      "day_number": 1,
      "region": "当日巡礼核心区域名称",
      "route_sequence": ["起点站", "地标1名称", "地标2名称", "返程站"],
      "transit_details": "交通细节",
      "landmarks": [
        {{
          "name": "地标名称",
          "bangumi": "作品名称",
          "ep": "集数",
          "timestamp": "时间戳",
          "geo": "坐标",
          "final_info": "基础信息",
          "anime_scene_atmosphere": "原作名场面剧情与时段氛围描述",
          "photo_guide": "极致详细的拍照还原指南（含角度、机位、推荐时段）",
          "pose_suggestions": "经典打卡 Pose 与台词还原建议",
          "fans_tips": "粉丝打卡专属贴士与圣地礼仪"
        }}
      ]
    }}
  ]
}}

请务必只返回 JSON 块，并用 ```json 和 ``` 包裹。
"""

SUPERVISOR_VALIDATION_PROMPT = """
你是一个挑剔的圣地巡礼路线监督员。
你的任务是严格审查动漫专家润色后的巡礼路线，检查是否存在地理折返冲突、地标遗漏或严重的交通时间冲突。

用户要求的地标列表：
{raw_landmarks_json}

动漫专家生成的巡礼路线：
{refined_itinerary_json}

请进行以下维度的校验：
1. **地标完整性**：用户要求的每一个地标是否都在行程中？（注意检查地标名称，不能漏掉任何一个）。
2. **地理合理性（不折返）**：同一天内的游览顺序是否合理？有没有出现跨度过大的折返（例如：A点 and C点在京都市，B点在宇治市，游览顺序却是 A -> B -> C，这属于严重折返错误）。
3. **步行强度**：每一天的步行距离是否在合理范围内？（推荐单日 6-10km，如果超过 15km 必须指出错误）。

请输出一个 JSON 对象，包含以下字段：
1. "is_valid": 布尔值（true 或 false），只有上述三个维度完全合格时，才为 true。
2. "errors": 字符串列表，如果 is_valid 为 false，请详细列出发现的所有错误和修改建议（例如："地标 京都音乐厅 遗漏，未出现在任何一天的行程中"、"第一天游览顺序存在折返：从宇治桥到京都音乐厅又回到宇治，建议将京都音乐厅调整到其他日子游览"）。如果 valid 为 true，则该字段为空列表。
3. "walking_distances": 对象，包含每一天的预估步行距离，键为 "第1天"、"第2天" 等，值为预估值（如 "8.5 km"）。

请务必只返回 JSON 块，并用 ```json 和 ``` 包裹。
"""

EDITOR_FORMATTING_PROMPT = """
你是一个资深的动漫圣地巡礼主编。
请根据下面的精排路由和动漫细节数据，生成一份极其精美、排版规整、充满情怀的 Markdown 巡礼路线规划方案。

巡礼路线细节数据：
{refined_itinerary_json}

每日步行距离：
{walking_distances_json}

你必须严格按照以下 Markdown 格式模板输出，不要使用任何多余的包裹标签（除了 markdown 本身）：

# 多作品混合圣地巡礼路线规划（X日版）
## 整体规划说明
- 地标总数：X个
- 涉及作品：xxx
- 出行方式：JR/地铁+步行，单日平均步行约Xkm
- 核心区域：xxx
- 推荐交通卡：xxx

---
## 第N天：XX区域巡礼（共X个地点）
### 路线顺序：起点站 → 地标1 → 地标2 → … → 返程站
### 当日步行：约Xkm | 总耗时：约X小时

1. 【地标：XX】
- 作品出处：《XX》EPX XX:XX
- 坐标：纬度/经度
- 现实地址：xxx
- 交通衔接：xxx
- 打卡建议：xxx
- 原作场景时段：xxx（EPX XX:XX）
- 推荐到访时段：xxx
- 预估停留：X分钟
- 拍照还原指南：xxx
- 经典动作(Pose)建议：xxx
- 巡礼文化贴士：xxx

### 当日餐饮休息建议
午餐/休息/晚餐顺路点位推荐

---
## 整体出行小贴士
交通卡、乘车APP、错峰打卡、名场面还原、当地礼仪、紧急电话极简要点即可，无需冗余描述。

请以中文撰写，语言应当充满对动漫作品的热爱与情怀，同时极具实用可落地性。
"""

# Helper to parse json block
def parse_json_block(text: str) -> Dict[str, Any]:
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass
    try:
        return json.loads(text.strip())
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                pass
    return {}

# ----------------- LangGraph Config -----------------

class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]
    days: int
    raw_landmarks: List[Dict[str, Any]]
    completed_landmarks: List[Dict[str, Any]]
    routing_draft: Dict[str, Any]
    refined_itinerary: Dict[str, Any]
    final_output: str
    errors: List[str]
    revision_count: int

def info_retriever_node(state: AgentState, config=None) -> Dict[str, Any]:
    callback = config.get("configurable", {}).get("on_chunk_callback") if config else None
    if callback:
        callback("__STATUS__:正在进行信息检索与验证...\n")
        
    msg = state["messages"][-1]
    if isinstance(msg, dict):
        user_message = msg.get("content", "")
    else:
        user_message = getattr(msg, "content", str(msg))
    
    # Parse input text to structured landmarks and days
    parse_prompt = PARSER_PROMPT.format(data_text=user_message)
    parser_res = llm_deepseek.invoke(parse_prompt).content
    data = parse_json_block(parser_res)
    
    days = data.get("days", 1)
    landmarks = data.get("landmarks", [])
    
    completed_landmarks = []
    total = len(landmarks)
    for idx, lm in enumerate(landmarks):
        name = lm.get("name")
        bangumi = lm.get("bangumi")
        ep = lm.get("ep") or ""
        timestamp = lm.get("timestamp") or ""
        rag_info = lm.get("rag_info")
        
        if callback and name:
            callback(f"__STATUS__:正在检索与验证地标: {name} ({idx+1}/{total})...\n")
        
        # Check if RAG has info
        if rag_info and len(rag_info.strip()) > 30:
            lm["final_info"] = rag_info
            lm["source"] = "RAG Context"
            completed_landmarks.append(lm)
        else:
            # Query Tavily via get_anime_scene
            search_res = get_anime_scene.func(
                anime_title=bangumi,
                episode=ep,
                location_name=name,
                timestamp=timestamp
            )
            
            # Relevance validation
            val_prompt = RELEVANCE_CHECK_PROMPT.format(
                name=name,
                bangumi=bangumi,
                ep=ep,
                timestamp=timestamp,
                search_result=search_res
            )
            val_res = llm_deepseek.invoke(val_prompt).content
            val_data = parse_json_block(val_res)
            
            if val_data.get("relevant", False):
                lm["final_info"] = val_data.get("extracted_details") or search_res
                lm["source"] = "Tavily Search (Validated)"
            else:
                lm["final_info"] = "未找到直接相关的动漫圣地巡礼背景信息（已过滤不相关搜索结果）。"
                lm["source"] = "None (Filtered)"

            completed_landmarks.append(lm)

        # MiMo 视觉分析：对有截图的 landmark 进行画面分析
        image_url = lm.get("image")
        if image_url and name and bangumi:
            try:
                if callback:
                    callback(f"__STATUS__:正在进行MiMo视觉分析: {name}...\n")
                vision_result = analyze_anime_scene_image(
                    image_url=image_url,
                    location_name=name,
                    anime_title=bangumi,
                    extra_context=lm.get("final_info", "")[:500]
                )
                if vision_result and not vision_result.startswith("[MiMo视觉分析异常]"):
                    lm["final_info"] = (
                        lm.get("final_info", "") +
                        "\n\n[MiMo视觉分析]\n" + vision_result
                    )
                    lm["vision_analyzed"] = True
            except Exception:
                pass  # 视觉分析失败不阻塞流程

    return {
        "days": days,
        "completed_landmarks": completed_landmarks,
        "raw_landmarks": landmarks
    }

def routing_specialist_node(state: AgentState, config=None) -> Dict[str, Any]:
    callback = config.get("configurable", {}).get("on_chunk_callback") if config else None
    if callback:
        callback("__STATUS__:正在根据地理区域和天气进行路线规划...\n")
        
    landmarks = state["completed_landmarks"]
    days = state["days"]
    errors = state.get("errors", [])
    
    # 1. Determine city for weather
    lm_names = [lm.get("name") for lm in landmarks]
    city_prompt = f"Based on these landmark names, identify the main city in Japan (e.g., 'Kyoto', 'Tokyo', 'Uji', 'Yokohama') where these locations are situated. Output only the city name.\nLandmarks: {lm_names}"
    city = llm_deepseek.invoke(city_prompt).content.strip().split("\n")[-1].strip(" '\"`*.")
    
    # 2. Get weather info
    try:
        weather_info = get_weather.func(city=city)
    except Exception:
        weather_info = "无法获取天气"
        
    # 3. Generate routing draft
    landmarks_json = json.dumps(landmarks, ensure_ascii=False, indent=2)
    errors_text = "\n".join([f"- {err}" for err in errors]) if errors else "无"
    
    prompt = ROUTING_PROMPT.format(
        days=days,
        weather_info=weather_info,
        landmarks_json=landmarks_json,
        errors_text=errors_text
    )
    
    res = llm_deepseek.invoke(prompt).content
    routing_draft = parse_json_block(res)
    
    return {
        "routing_draft": routing_draft
    }

def anime_expert_node(state: AgentState, config=None) -> Dict[str, Any]:
    callback = config.get("configurable", {}).get("on_chunk_callback") if config else None
    if callback:
        callback("__STATUS__:正在匹配动漫原作场景时段与拍照建议...\n")

    routing_draft = state["routing_draft"]
    completed_landmarks = state.get("completed_landmarks", [])

    # 构建 name→image 查找表 + 已分析集合（从 completed_landmarks 中提取）
    name_to_image = {}
    vision_analyzed = set()
    for lm in completed_landmarks:
        n = lm.get("name")
        img = lm.get("image")
        if n and img:
            name_to_image[n] = img
        if lm.get("vision_analyzed"):
            vision_analyzed.add(n)

    # 对 routing_draft 中每个 landmark，有截图但未做过视觉分析的 → 调 MiMo
    for day in routing_draft.get("days", []):
        for lm in day.get("landmarks", []):
            lm_name = lm.get("name")
            if not lm_name:
                continue
            if lm_name in vision_analyzed:
                continue
            image_url = lm.get("image") or name_to_image.get(lm_name)
            if not image_url:
                continue
            existing_info = lm.get("final_info", "") or ""
            try:
                if callback:
                    callback(f"__STATUS__:MiMo视觉分析: {lm_name}...\n")
                vision_result = analyze_anime_scene_image(
                    image_url=image_url,
                    location_name=lm_name,
                    anime_title=lm.get("bangumi", ""),
                    extra_context=existing_info[:500]
                )
                if vision_result and not vision_result.startswith("[MiMo视觉分析异常]"):
                    lm["final_info"] = existing_info + "\n\n[MiMo视觉分析]\n" + vision_result
                    vision_analyzed.add(lm_name)
            except Exception:
                pass

    # 用视觉增强后的 routing_draft 交给 DeepSeek 生成拍照指南
    prompt = ANIME_EXPERT_PROMPT.format(
        routing_draft_json=json.dumps(routing_draft, ensure_ascii=False, indent=2)
    )

    res = llm_deepseek.invoke(prompt).content
    refined_itinerary = parse_json_block(res)

    return {
        "refined_itinerary": refined_itinerary
    }

def supervisor_editor_node(state: AgentState, config=None) -> Dict[str, Any]:
    callback = config.get("configurable", {}).get("on_chunk_callback") if config else None
    raw_landmarks = state["raw_landmarks"]
    refined_itinerary = state["refined_itinerary"]
    revision_count = state.get("revision_count", 0)
    
    if callback:
        if revision_count > 0:
            callback(f"__STATUS__:正在进行路线合理性审查与微调 (第 {revision_count} 次修正)...\n")
        else:
            callback("__STATUS__:正在进行路线合理性审查与微调...\n")
    
    val_prompt = SUPERVISOR_VALIDATION_PROMPT.format(
        raw_landmarks_json=json.dumps(raw_landmarks, ensure_ascii=False),
        refined_itinerary_json=json.dumps(refined_itinerary, ensure_ascii=False)
    )
    val_res = llm_deepseek.invoke(val_prompt).content
    val_data = parse_json_block(val_res)
    
    is_valid = val_data.get("is_valid", False)
    errors = val_data.get("errors", [])
    walking_distances = val_data.get("walking_distances", {})
    
    if not is_valid and revision_count < 3:
        return {
            "errors": errors,
            "revision_count": revision_count + 1
        }
    
    # Validation passed or maximum revisions reached, format final output
    fmt_prompt = EDITOR_FORMATTING_PROMPT.format(
        refined_itinerary_json=json.dumps(refined_itinerary, ensure_ascii=False, indent=2),
        walking_distances_json=json.dumps(walking_distances, ensure_ascii=False)
    )
    
    callback = config.get("configurable", {}).get("on_chunk_callback") if config else None
    content = ""
    
    for chunk in llm_deepseek.stream(fmt_prompt):
        content += chunk.content
        if callback:
            callback(chunk.content)
            
    return {
        "final_output": content,
        "errors": []
    }

def should_continue(state: AgentState) -> str:
    if state.get("errors"):
        return "routing_specialist"
    return "end"

# Build StateGraph
workflow = StateGraph(AgentState)
workflow.add_node("info_retriever", info_retriever_node)
workflow.add_node("routing_specialist", routing_specialist_node)
workflow.add_node("anime_expert", anime_expert_node)
workflow.add_node("supervisor_editor", supervisor_editor_node)

workflow.set_entry_point("info_retriever")
workflow.add_edge("info_retriever", "routing_specialist")
workflow.add_edge("routing_specialist", "anime_expert")
workflow.add_edge("anime_expert", "supervisor_editor")

workflow.add_conditional_edges(
    "supervisor_editor",
    should_continue,
    {
        "routing_specialist": "routing_specialist",
        "end": END
    }
)

graph = workflow.compile()

# ----------------- Runnable Wrapper -----------------

class MultiAgentRunnable:
    """包装 LangGraph 的流式接口以保持与 FastAPI 后端的兼容性"""
    def __init__(self, graph):
        self.graph = graph
        
    def stream(self, input_dict, config=None, stream_mode="messages"):
        q = queue.Queue()
        
        def on_chunk(token):
            q.put(token)
            
        def run_graph():
            try:
                run_config = config or {}
                configurable = run_config.get("configurable", {})
                configurable["on_chunk_callback"] = on_chunk
                run_config["configurable"] = configurable
                
                self.graph.invoke(input_dict, run_config)
            except Exception as e:
                q.put(e)
            finally:
                q.put(None)
                
        t = threading.Thread(target=run_graph)
        t.start()
        
        while True:
            token = q.get()
            if token is None:
                break
            if isinstance(token, Exception):
                raise token
            
            class Chunk:
                def __init__(self, content):
                    self.content = content
            yield Chunk(token), None

# Export agent for use in server.py
agent = MultiAgentRunnable(graph)