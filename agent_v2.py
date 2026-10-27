"""Structured LangGraph planning run for the versioned Agent endpoint."""

import concurrent.futures
import json
import os
import time
import threading
from datetime import timedelta
from contextvars import copy_context
from typing import Any, Callable, TypedDict
from urllib.parse import urlparse

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

import agent_trace
import planning_progress as progress
from agent import apply_vision_analysis, llm_deepseek, parse_json_block
from plan_geometry import straight_line_distance_m
from plan_schema import (
    Plan, PlanIssue, PlanRequest, PlanSource, PointNote, ScenePreference, WeatherSnapshot,
    VISIT_TIME_LABELS, point_key,
)
from plan_validation import issue, normalize_candidate
from rag_service import rag_service
from weather_service import fetch_weather_snapshot


MAX_REVISIONS = max(0, int(os.getenv("AGENT_MAX_REVISIONS", "3")))
MODEL_TIMEOUT = max(1, float(os.getenv("AGENT_MODEL_TIMEOUT_SECONDS", "45")))
TOOL_TIMEOUT = max(1, float(os.getenv("AGENT_TOOL_TIMEOUT_SECONDS", "35")))
RUN_TIMEOUT = max(1, float(os.getenv("AGENT_RUN_TIMEOUT_SECONDS", "240")))


class AgentRunError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class PlanState(TypedDict, total=False):
    run_id: str
    request_snapshot: dict[str, Any]
    rag_context: str
    landmark_context: dict[str, Any]
    sources: list[dict[str, Any]]
    warnings: list[PlanIssue]
    weather: list[WeatherSnapshot]
    scene_preferences: list[ScenePreference]
    candidate: dict[str, Any]
    plan: Plan | None
    errors: list[PlanIssue]
    revision_count: int
    output_text: str


def _cfg(config: dict | None, name: str, default: Any = None) -> Any:
    return (config or {}).get("configurable", {}).get(name, default)


def _check(config: dict | None) -> float:
    if _cfg(config, "should_cancel", lambda: False)():
        raise AgentRunError("RUN_CANCELLED", "规划请求已取消")
    remaining = _cfg(config, "deadline", time.monotonic() + RUN_TIMEOUT) - time.monotonic()
    if remaining <= 0:
        raise AgentRunError("TOOL_TIMEOUT", "规划总时限已到，请减少点位后重试")
    return remaining


def _progress(config: dict | None, stage: str, message: str) -> None:
    _check(config)
    agent_trace.record_status(stage, message)
    progress.update_current(message)
    callback = _cfg(config, "on_progress")
    if callback:
        callback(stage, message)


def _bounded_call(
    config: dict | None,
    fn: Callable[[], Any],
    *,
    timeout: float,
    timeout_code: str,
    label: str,
    retries: int = 0,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        remaining = _check(config)
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        parent_run_id = agent_trace.get_current_run_id()

        def traced() -> Any:
            agent_trace.attach_run(parent_run_id)
            return fn()

        future = executor.submit(copy_context().run, traced)
        end_at = time.monotonic() + min(timeout, remaining)
        try:
            while True:
                _check(config)
                wait = min(0.2, end_at - time.monotonic())
                if wait <= 0:
                    raise AgentRunError(timeout_code, f"{label}超时")
                try:
                    return future.result(timeout=wait)
                except concurrent.futures.TimeoutError:
                    if future.done():
                        return future.result()  # Propagate a tool timeout, or a result completed during the polling race.
                    continue
        except AgentRunError as exc:
            last_error = exc
            future.cancel()
            if exc.code == "RUN_CANCELLED" or attempt == retries:
                raise
        except (TimeoutError, ConnectionError) as exc:
            last_error = exc
            if attempt == retries:
                raise AgentRunError(timeout_code, f"{label}暂时不可用：{exc}") from exc
        except Exception as exc:
            class_name = type(exc).__name__.lower()
            transient = "timeout" in class_name or "connection" in class_name
            if transient and attempt < retries:
                last_error = exc
                continue
            code = timeout_code if "timeout" in class_name else ("MODEL_UNAVAILABLE" if timeout_code == "MODEL_TIMEOUT" else "TOOL_ERROR")
            raise AgentRunError(code, f"{label}失败：{exc}") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
    raise AgentRunError(timeout_code, f"{label}失败：{last_error}")


def _model(config: dict | None, node: str, prompt: str) -> dict[str, Any]:
    def invoke() -> str:
        response = llm_deepseek.invoke(prompt)
        return response.content if hasattr(response, "content") else str(response)

    raw = _bounded_call(config, invoke, timeout=MODEL_TIMEOUT, timeout_code="MODEL_TIMEOUT", label="主规划模型", retries=1)
    agent_trace.record_llm_call(node, node, prompt, raw, model=llm_deepseek.model_name)
    parsed = parse_json_block(raw)
    return parsed if isinstance(parsed, dict) else {}


def _sources(result: dict[str, Any], ids: set[str]) -> list[dict[str, Any]]:
    cleaned = []
    for item in result.get("sources", []) or []:
        if not isinstance(item, dict):
            continue
        refs = [ref for ref in item.get("point_ids", []) if point_key(ref) in ids]
        if not refs:
            continue
        url = item.get("url")
        # Only a safe HTTP(S) URL can be presented as an external reference.
        parsed_url = urlparse(url) if isinstance(url, str) else None
        if not parsed_url or parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc or any(char.isspace() for char in url):
            url = None
        review_status = item.get("review_status") if item.get("review_status") in {"approved", "unreviewed", "missing"} else "missing"
        if not url:
            review_status = "missing"
        cleaned.append({
            "source_id": str(item.get("source_id") or f"source_{len(cleaned) + 1}"),
            "url": url,
            "title": str(item.get("title") or "参考资料"),
            "retrieved_at": item.get("retrieved_at"),
            "review_status": review_status,
            "point_ids": refs,
        })
    return cleaned


@progress.track_stage("retrieve", "检索巡礼资料")
def retrieve_node(state: PlanState, config: RunnableConfig | None = None) -> dict[str, Any]:
    _progress(config, "retrieve", "正在检索已有资料与场景信息")
    request = PlanRequest.model_validate(state["request_snapshot"])
    landmarks = [lm.model_dump(mode="json", exclude_unset=True) for lm in request.landmarks]
    warnings: list[PlanIssue] = []
    result: dict[str, Any] = {}
    progress.activity("retrieve", "knowledge", "查询已有知识库", f"正在查询 {len(landmarks)} 处地点的已有资料", "running")
    try:
        result = _bounded_call(
            config, lambda: rag_service.query_landmarks_context(landmarks),
            timeout=TOOL_TIMEOUT, timeout_code="TOOL_TIMEOUT", label="资料检索", retries=1,
        ) or {}
    except AgentRunError as exc:
        if exc.code == "RUN_CANCELLED":
            raise
        warnings.append(issue(exc.code, f"资料检索失败：{exc}"))
    except Exception as exc:
        warnings.append(issue("TOOL_ERROR", f"资料检索失败：{exc}"))

    missing = result.get("missing_landmarks", landmarks)
    missing = missing if isinstance(missing, list) else landmarks
    known_count = max(0, len(landmarks) - len(missing))
    progress.activity("retrieve", "knowledge", "查询已有知识库", f"命中 {known_count} 处，{len(missing)} 处需要联网补充", "warning" if warnings else "completed")
    ingest: dict[str, Any] = {}
    if isinstance(missing, list) and missing:
        progress.activity("retrieve", "web", "联网补充公开资料", f"正在为 {len(missing)} 处地点检索公开资料", "running")
        retrieval_stopped = threading.Event()
        should_cancel_retrieval = lambda: retrieval_stopped.is_set() or _cfg(config, "should_cancel", lambda: False)()
        retrieval_deadline = min(
            _cfg(config, "deadline", float("inf")), time.monotonic() + max(0.1, TOOL_TIMEOUT - 1),
        )
        try:
            _progress(config, "retrieve", f"正在补充 {len(missing)} 个点位的公开资料")
            ingest = _bounded_call(
                config, lambda: rag_service.ingest_landmarks(
                    missing, should_cancel=should_cancel_retrieval, deadline=retrieval_deadline,
                ),
                timeout=TOOL_TIMEOUT, timeout_code="TOOL_TIMEOUT", label="联网补充",
            ) or {}
        except AgentRunError as exc:
            if exc.code == "RUN_CANCELLED":
                raise
            warnings.append(issue(exc.code, f"联网补充失败：{exc}"))
        except Exception as exc:
            warnings.append(issue("TOOL_ERROR", f"联网补充失败：{exc}"))
        finally:
            retrieval_stopped.set()
        added = len(ingest.get("landmark_context") or {})
        progress.activity("retrieve", "web", "联网补充公开资料",
                          f"补充 {added} 处地点，取得 {len(ingest.get('sources') or [])} 条来源；新增资料保留审核标记",
                          "completed" if added == len(missing) else "warning")

    ids = {point_key(lm.id) for lm in request.landmarks}
    sources = _sources(result, ids) + _sources(ingest, ids)
    statuses_by_source: dict[str, set[str]] = {}
    for source in sources:
        statuses_by_source.setdefault(source["source_id"], set()).add(source["review_status"])
    unique_sources: dict[tuple[str, str], dict[str, Any]] = {}
    for source in sources:
        key = (source["source_id"], source["review_status"])
        existing = unique_sources.get(key)
        if existing is None:
            source = dict(source)
            if len(statuses_by_source[source["source_id"]]) > 1:
                source["source_id"] = f"{source['source_id']}_{source['review_status']}"
            unique_sources[key] = source
        else:
            existing["point_ids"] = list(dict.fromkeys(existing["point_ids"] + source["point_ids"]))
    landmark_context = dict(result.get("landmark_context") or {})
    landmark_context.update(ingest.get("landmark_context") or {})
    warning_keys: dict[tuple[str, str], PlanIssue] = {}
    for failure in (result.get("failures") or []) + (ingest.get("failures") or []):
        if not isinstance(failure, dict):
            continue
        ref = failure.get("landmark_id")
        point_ids = [ref] if ref is not None and point_key(ref) in ids else []
        code = str(failure.get("code") or "TOOL_ERROR")
        message = str(failure.get("message") or "资料检索部分失败")
        key = (code, message)
        if key not in warning_keys:
            warning_keys[key] = issue(code, message, point_ids)
        else:
            warning_keys[key].point_ids = list(dict.fromkeys(warning_keys[key].point_ids + point_ids))
    warnings.extend(warning_keys.values())

    image_landmarks = [lm for lm in request.landmarks if lm.image]
    if image_landmarks and not os.getenv("MIMO_API_KEY"):
        warnings.append(issue("VISION_UNAVAILABLE", "视觉服务未配置，本次未分析截图", [lm.id for lm in image_landmarks]))
        progress.activity("retrieve", "vision-unavailable", "场景截图分析", f"视觉服务未配置，本次跳过 {len(image_landmarks)} 张截图", "skipped")
    elif image_landmarks:
        _progress(config, "retrieve", f"正在分析 {len(image_landmarks)} 张场景截图")
        for lm in image_landmarks:
            _check(config)
            progress.activity("retrieve", f"vision:{lm.id}", f"截图分析 · {lm.name}", "正在观察场景中的构图与氛围", "running")
            vision_input = {"name": lm.name, "bangumi": lm.bangumiName or "", "image": lm.image, "final_info": ""}
            try:
                ok, _ = _bounded_call(
                    config,
                    lambda entry=vision_input, point=lm: apply_vision_analysis(
                        entry, point.name, point.bangumiName or "", point.image or "", node="retrieve",
                    ),
                    timeout=TOOL_TIMEOUT, timeout_code="TOOL_TIMEOUT", label=f"{lm.name} 截图分析",
                )
                if ok:
                    key = point_key(lm.id)
                    existing = landmark_context.get(key)
                    if not isinstance(existing, dict):
                        existing = {"context": "", "chunks": [], "source_ids": []}
                    existing["context"] = (str(existing.get("context") or "") + "\n【截图观察（未核实）】\n" + vision_input.get("final_info", "")).strip()
                    landmark_context[key] = existing
                else:
                    warnings.append(issue("VISION_UNAVAILABLE", f"{lm.name} 截图分析不可用", [lm.id]))
                progress.activity("retrieve", f"vision:{lm.id}", f"截图分析 · {lm.name}",
                                  "截图观察已加入参考资料，仍需核实" if ok else "截图分析不可用，继续使用文字资料", "completed" if ok else "warning")
            except AgentRunError as exc:
                if exc.code == "RUN_CANCELLED":
                    raise
                warnings.append(issue(exc.code, f"{lm.name} 截图分析失败：{exc}", [lm.id]))
                progress.activity("retrieve", f"vision:{lm.id}", f"截图分析 · {lm.name}", "截图分析失败，继续使用已有资料", "warning")
            except Exception as exc:
                warnings.append(issue("VISION_UNAVAILABLE", f"{lm.name} 截图分析失败：{exc}", [lm.id]))
                progress.activity("retrieve", f"vision:{lm.id}", f"截图分析 · {lm.name}", "截图分析失败，继续使用已有资料", "warning")
    rag_context = "\n\n".join(filter(None, [result.get("context", ""), ingest.get("search_context", "")]))[:16000]
    agent_trace.record_event("retrieve", "资料检索结束", {"sources": len(unique_sources), "warnings": [w.code for w in warnings]})
    added = len(ingest.get("landmark_context") or {})
    return {"rag_context": rag_context, "landmark_context": landmark_context, "sources": list(unique_sources.values()), "warnings": warnings,
            "_step_summary": f"已有资料命中 {known_count} 处，联网补充 {added} 处，保留 {len(unique_sources)} 条来源" + (f"；有 {len(warnings)} 项资料提示" if warnings else ""),
            "_step_status": "warning" if known_count + added < len(landmarks) else "completed"}


def _scene_context(state: PlanState, request: PlanRequest) -> list[dict[str, Any]]:
    limit = min(1400, 20000 // len(request.landmarks))
    result = []
    for lm in request.landmarks:
        context = (state.get("landmark_context") or {}).get(point_key(lm.id))
        result.append({
            "point_id": lm.id, "name": lm.name, "bangumiName": lm.bangumiName or lm.bangumiOriginalName,
            "ep": lm.ep, "episode_timestamp_seconds": lm.s,
            "context": str(context.get("context") or "")[:limit] if isinstance(context, dict) else "",
        })
    return result


@progress.track_stage("experience", "分析天气与原作场景")
def experience_node(state: PlanState, config: RunnableConfig | None = None) -> dict[str, Any]:
    """Collect regional weather once and derive scene constraints before routing."""
    _progress(config, "experience", "正在结合目的地天气与原作情节安排巡礼时段")
    request = PlanRequest.model_validate(state["request_snapshot"])
    warnings = list(state.get("warnings", []))
    # Nearby landmarks share a forecast, while distant cities keep independent snapshots.
    groups = []
    for lm in request.landmarks:
        for group in groups:
            if straight_line_distance_m(group[0].geo, lm.geo) <= 40_000:
                group.append(lm)
                break
        else:
            groups.append([lm])

    weather = []
    for group in groups[:6]:
        _check(config)
        refs = [lm.id for lm in group]
        weather_key = f"weather:{group[0].id}"
        progress.activity("experience", weather_key, f"目的地天气 · {group[0].name}", f"正在为附近 {len(group)} 处地点查询天气与预报", "running")
        try:
            snapshot = _bounded_call(
                config, lambda geo=group[0].geo: fetch_weather_snapshot(geo),
                timeout=min(TOOL_TIMEOUT, 10), timeout_code="TOOL_TIMEOUT", label=f"{group[0].name} 所在地区天气",
            )
            snapshot.point_ids = refs
            weather.append(snapshot)
            progress.activity("experience", weather_key, f"目的地天气 · {snapshot.location}",
                              f"已取得实况与 {len(snapshot.forecast)} 天预报" + ("，按出发日期匹配" if request.start_date else "；未设出发日期，仅作参考"))
            if request.start_date:
                available = {day.date for day in snapshot.forecast}
                dates = [request.start_date + timedelta(days=index) for index in range(request.days)]
                missing = [date.isoformat() for date in dates if date not in available]
                if missing:
                    warnings.append(issue(
                        "WEATHER_FORECAST_UNAVAILABLE",
                        f"{snapshot.location} 的预报未覆盖 {', '.join(missing)}；这些日期仅提供条件式天气建议",
                        refs,
                    ))
                    progress.activity("experience", weather_key, f"目的地天气 · {snapshot.location}",
                                      f"取得 {len(snapshot.forecast)} 天预报，但未覆盖全部出行日期；缺失日期使用条件式建议", "warning")
        except AgentRunError as exc:
            if exc.code == "RUN_CANCELLED":
                raise
            warnings.append(issue("WEATHER_UNAVAILABLE", f"{group[0].name} 所在地区天气暂不可用：{exc}", refs))
            progress.activity("experience", weather_key, f"目的地天气 · {group[0].name}", "天气暂不可用，将提供条件式天气建议", "warning")
        except Exception as exc:
            warnings.append(issue("WEATHER_UNAVAILABLE", f"{group[0].name} 所在地区天气暂不可用：{exc}", refs))
            progress.activity("experience", weather_key, f"目的地天气 · {group[0].name}", "天气暂不可用，将提供条件式天气建议", "warning")
    if len(groups) > 6:
        warnings.append(issue("WEATHER_REGION_LIMIT", "目的地区域较多，部分区域未查询天气", [lm.id for group in groups[6:] for lm in group]))
    if not request.start_date:
        warnings.append(issue("WEATHER_DATE_UNSPECIFIED", "未设置出发日期，当前天气和近期预报仅作参考，不代表实际出行日天气"))

    preferences = {point_key(lm.id): ScenePreference(point_id=lm.id) for lm in request.landmarks}
    progress.activity("experience", "scenes", "提取原作场景偏好", "正在根据资料和截图观察识别推荐时段与剧情顺序", "running")
    prompt = (
        "你是动漫圣地巡礼情节策划。请在排路线前提取每个点位的原作场景氛围、适合还原的时段和剧情顺序。"
        "优先依据给定资料与截图观察；外部资料可能不准确。资料不足时 preferred_time=any、scene_order=null，"
        "scene_summary 说明无法核实，不凭作品名、集数编造剧情、台词、角色动作或室内外属性。"
        "episode_timestamp_seconds 只是视频播放位置，不是现实钟点，也不是原作昼夜时段。"
        "preferred_time 只能为 any/morning/afternoon/sunset/evening；仅当场景明确支持时设置时段。"
        "scene_order 只在同一作品的相对情节顺序有依据时填正整数，不同作品之间不比较。"
        "时段约束优先于剧情顺序；剧情顺序只在相同时段内适用，不应为还原剧情造成跨城市折返。"
        "weather_sensitivity 只能为 outdoor/indoor/unknown，无法核实时用 unknown。"
        "reason 解释为何推荐这个时段或顺序，说明建议属于还原偏好而非开放时间限制。"
        "只能使用原始 point_id，每个点位一次。返回严格 JSON："
        '{"preferences":[{"point_id":"原始ID","preferred_time":"any","scene_order":null,'
        '"scene_summary":"","reason":"","weather_sensitivity":"unknown"}]}。\n'
        f"点位资料：{json.dumps(_scene_context(state, request), ensure_ascii=False)}"
    )
    try:
        result = _model(config, "scene_preferences", prompt)
        raw_preferences = result.get("preferences")
        if not isinstance(raw_preferences, list):
            raise ValueError("未返回 preferences 数组")
        seen = set()
        for raw in raw_preferences:
            pref = ScenePreference.model_validate(raw)
            key = point_key(pref.point_id)
            if key not in preferences or key in seen:
                raise ValueError("场景偏好引用了未知或重复的地标 ID")
            pref.point_id = preferences[key].point_id
            preferences[key] = pref
            seen.add(key)
        if len(seen) != len(preferences):
            warnings.append(issue("SCENE_DATA_INCOMPLETE", "部分地标缺少原作场景依据，按地理位置安排"))
        timed = sum(pref.preferred_time != "any" for pref in preferences.values())
        progress.activity("experience", "scenes", "提取原作场景偏好", f"{timed} 处地点有时段偏好，其余按地理位置与资料安排",
                          "completed" if len(seen) == len(preferences) else "warning")
    except AgentRunError as exc:
        if exc.code == "RUN_CANCELLED":
            raise
        warnings.append(issue(exc.code, f"原作场景分析不可用，按地理位置安排：{exc}"))
        progress.activity("experience", "scenes", "提取原作场景偏好", "场景分析暂不可用，按地理位置安排", "warning")
    except Exception as exc:
        warnings.append(issue("SCENE_DATA_INCOMPLETE", f"原作场景分析不完整：{exc}"))
        progress.activity("experience", "scenes", "提取原作场景偏好", "部分场景资料无法解析，保留已取得的偏好", "warning")
    agent_trace.record_event("experience", "天气与原作情节分析结束", {
        "weather_regions": len(weather), "timed_points": sum(pref.preferred_time != "any" for pref in preferences.values()),
    })
    timed = sum(pref.preferred_time != "any" for pref in preferences.values())
    return {"weather": weather, "scene_preferences": list(preferences.values()), "warnings": warnings,
            "_step_summary": f"取得 {len(weather)} 个地区的天气；{timed} 处地点有原作时段偏好，其余按地理位置安排",
            "_step_status": "completed" if weather else "warning"}


@progress.track_stage("route", "编排每日路线")
def route_node(state: PlanState, config: RunnableConfig | None = None) -> dict[str, Any]:
    request = PlanRequest.model_validate(state["request_snapshot"])
    revision = state.get("revision_count", 0)
    _progress(config, "route", "正在结合地理位置、天气与剧情分天排线" if revision == 0 else f"正在修复计划（第 {revision} 次）")
    locations = [
        {"id": lm.id, "name": lm.name, "geo": lm.geo, "bangumiName": lm.bangumiName, "ep": lm.ep}
        for lm in request.landmarks
    ]
    errors = [error.model_dump(mode="json") for error in state.get("errors", [])]
    prompt = (
        "你是动漫圣地巡礼路线策划。只能使用输入中的原始 ID，结合地理位置、真实天气和番剧情节安排指定天数。"
        "只返回严格 JSON 对象：{\"days\":[{\"day\":1,\"point_ids\":[\"原始ID\"],\"planning_reason\":\"地理、剧情与时段安排理由\",\"weather_advice\":\"天气适配建议\"}]}。"
        "days 长度必须等于请求天数，day 从 1 连续编号；天数多于点位时保留空日。"
        "每个 ID 必须且只能出现一次；不得添加景点、改名、猜测用户住处，不能引用资料中的新点位。"
        "地理区域优先，避免跨城市折返；同作品尽量保留可核实的剧情体验顺序，黄昏/夜景点位留在对应时段。"
        "每日内部顺序由程序在保留场景时段和同一时段的剧情顺序约束后优化直线距离。"
        "天气必须按日期和 point_ids 所属地区匹配；若有对应出行日的雨雪预报，把已选的可核实室内点位优先放在雨天，"
        "hourly 中的 time 是该地区当地预报时刻；只有对应小时预报才能支持『上午雨、午后晴』等时段判断，"
        "不能从每日 summary 的词语或排列顺序推断时段。每日 rain_chance_percent 是小时降雨概率的最大值。"
        "sunrise/sunset 是该日期当地日出日落时刻；黄昏场景应靠近给定的 sunset，不能一律当成18:00，缺失时不猜测精确日落钟点。"
        "室外名场面优先安排在较适合拍照的日子，并提供防雨、防滑、避暑或休息建议。不得擅自新增室内景点。"
        "出发日期为空时，实况与近期预报只能作参考，不得声称第几天一定下雨或晴天。"
        "出行日超出预报日期时，只能给出『如遇雨…』等条件式建议；当前天气不能冒充未来天气。"
        "无法同时满足地理、天气和剧情偏好时，在 planning_reason 中解释取舍。"
        "资料不足就明确说明，不编造剧情、营业时间、车站、真实交通时长或精确日落钟点。返工时按错误修复。\n"
        f"请求天数：{request.days}\n点位：{json.dumps(locations, ensure_ascii=False)}\n"
        f"出发日期：{request.start_date.isoformat() if request.start_date else '未指定'}\n"
        f"场景时段与情节偏好：{json.dumps([pref.model_dump(mode='json') for pref in state.get('scene_preferences', [])], ensure_ascii=False)}\n"
        f"分地区天气实况和带日期预报：{json.dumps([snapshot.model_dump(mode='json') for snapshot in state.get('weather', [])], ensure_ascii=False)}\n"
        f"上次错误：{json.dumps(errors, ensure_ascii=False)}\n"
        f"仅供背景参考的资料：{state.get('rag_context', '')[:10000]}"
    )
    candidate = _model(config, "route", prompt)
    _cfg(config, "scratch", {})["candidate"] = candidate
    valid = isinstance(candidate.get("days"), list) and bool(candidate["days"])
    return {"candidate": candidate, "revision_count": revision + 1,
            "_step_summary": f"已生成 {len(candidate['days'])} 天路线初稿，接着核对地点完整性与时段顺序" if valid else "模型结果暂无法解析，将交由校验决定是否返工",
            "_step_status": "completed" if valid else "warning"}


def _content_audit(state: PlanState, plan: Plan, config: dict | None) -> list[PlanIssue]:
    request = PlanRequest.model_validate(state["request_snapshot"])
    audit_input = [day.model_dump(mode="json", exclude={"legs"}) for day in plan.days]
    prompt = (
        "审核以下动漫巡礼计划的点位引用和文字资料使用。仅判断明显的身份混淆、遗漏、虚构点位，"
        "或把直线距离冒充实际步行/交通时间的问题。不要要求虚构车站、住宿地、开放时间或交通班次。"
        "同时检查明显的天气日期/地区错配、把当前实况当未来预报、无预报却断言出行日天气，"
        "或只有日摘要却断言某个具体时段转晴/下雨（须有对应 hourly 预报支持），"
        "以及在已有 sunset 时刻时仍把明显不符的钟点当成黄昏，"
        "以及安排理由明显违背已提供的原作时段偏好。资料不足应保留条件式建议，不为缺资料本身判失败。"
        "返回严格 JSON：{\"is_valid\":true或false,\"errors\":[\"具体问题\"]}。"
        "不通过时 errors 必须至少一条。\n"
        f"选中点位：{json.dumps([{'id': lm.id, 'name': lm.name, 'bangumiName': lm.bangumiName} for lm in request.landmarks], ensure_ascii=False)}\n"
        f"出发日期：{request.start_date.isoformat() if request.start_date else '未指定'}\n"
        f"天气：{json.dumps([snapshot.model_dump(mode='json') for snapshot in plan.weather], ensure_ascii=False)}\n"
        f"原作偏好：{json.dumps([pref.model_dump(mode='json') for pref in plan.scene_preferences], ensure_ascii=False)}\n"
        f"路线：{json.dumps(audit_input, ensure_ascii=False)}"
    )
    result = _model(config, "content_audit", prompt)
    valid = result.get("is_valid")
    errors = result.get("errors")
    if not isinstance(valid, bool) or not isinstance(errors, list) or any(not isinstance(error, str) for error in errors):
        return [issue("MODEL_OUTPUT_INVALID", "内容审核输出无法解析或字段类型错误")]
    if valid and errors:
        return [issue("MODEL_OUTPUT_INVALID", "内容审核结论与错误列表矛盾")]
    if not valid:
        return [issue("CONTENT_AUDIT_FAILED", error) for error in errors if error.strip()] or [issue("CONTENT_AUDIT_FAILED", "内容审核未通过，且未提供具体原因")]
    return []


@progress.track_stage("validate", "校验与修复")
def validate_node(state: PlanState, config: RunnableConfig | None = None) -> dict[str, Any]:
    _progress(config, "validate", "正在核对点位完整性与直线距离")
    request = PlanRequest.model_validate(state["request_snapshot"])
    progress.activity("validate", "integrity", "检查地点与距离", "正在检查遗漏、重复、天数、时段顺序和直线距离", "running")
    plan, errors = normalize_candidate(
        request, state["run_id"], state.get("candidate"), warnings=state.get("warnings"),
        scene_preferences=state.get("scene_preferences"), weather=state.get("weather"),
    )
    assigned = sum(len(day.point_ids) for day in plan.days) if plan else 0
    integrity_summary = f"已安排 {assigned} / {len(request.landmarks)} 处地点"
    if errors:
        integrity_summary += "；" + "；".join(error.message for error in errors[:2])
    else:
        integrity_summary += "；点位、顺序和直线距离检查通过"
    progress.activity("validate", "integrity", "检查地点与距离", integrity_summary, "warning" if errors else "completed")
    if plan and not errors:
        progress.activity("validate", "audit", "审核路线与资料使用", "正在检查天气日期、原作时段和安排理由是否一致", "running")
        try:
            audit_errors = _content_audit(state, plan, config)
        except AgentRunError:
            raise
        except Exception as exc:
            audit_errors = [issue("MODEL_OUTPUT_INVALID", f"内容审核失败：{exc}")]
        if audit_errors:
            plan.status = "draft"
            plan.validation.passed = False
            plan.validation.errors.extend(audit_errors)
            errors = plan.validation.errors
        progress.activity("validate", "audit", "审核路线与资料使用",
                          "；".join(error.message for error in audit_errors[:2]) if audit_errors else "路线与天气、原作时段的内容审核通过",
                          "warning" if audit_errors else "completed")
    _cfg(config, "scratch", {})["plan"] = plan
    agent_trace.record_event("validate", "计划校验结束", {"passed": bool(plan and plan.validation.passed), "errors": [e.code for e in errors]})
    revision = state.get("revision_count", 0)
    if errors:
        summary = "；".join(error.message for error in errors[:2])
        summary += f"；准备进行第 {revision} 次修复" if revision <= MAX_REVISIONS else "；已达到修复上限，保留草案"
    else:
        summary = f"全部 {len(request.landmarks)} 处地点已覆盖，完整性、时段与内容审核通过"
        if revision > 1:
            summary += f"；经过 {revision - 1} 次修复"
    return {"plan": plan, "errors": errors, "_step_summary": summary,
            "_step_status": ("warning" if revision <= MAX_REVISIONS else "failed") if errors else "completed"}


def after_validate(state: PlanState) -> str:
    if state.get("errors") and state.get("revision_count", 0) <= MAX_REVISIONS:
        return "route"
    return "enrich"


def _make_notes(state: PlanState, plan: Plan, config: dict | None) -> list[PointNote]:
    request = PlanRequest.model_validate(state["request_snapshot"])
    source_ids_by_point: dict[str, list[str]] = {}
    approved_by_point: set[str] = set()
    for source in plan.sources:
        for ref in source.point_ids:
            key = point_key(ref)
            source_ids_by_point.setdefault(key, []).append(source.source_id)
            if source.review_status == "approved":
                approved_by_point.add(key)

    notes = []
    for lm in request.landmarks:
        key = point_key(lm.id)
        source_ids = source_ids_by_point.get(key, [])
        insufficient = not source_ids
        notes.append(PointNote(
            point_id=lm.id,
            scene_description="暂无可核实的场景说明" if insufficient else "可参考下列资料核对原作场景",
            photo_advice="请对照所选截图，在现场核对机位与拍摄许可",
            cautions="请遵守现场规定，避免影响居民和通行",
            source_ids=source_ids,
            inferred=True,
            insufficient_data=insufficient,
        ))
        if insufficient:
            plan.validation.warnings.append(issue("SOURCE_MISSING", f"{lm.name} 暂无可追溯资料", [lm.id]))

    if plan.status != "complete":
        return notes
    progress.activity("enrich", "notes", "整理场景与拍照建议", "正在结合资料、场景偏好和天气补充巡礼说明", "running")
    compact = [{
        "point_id": lm.id, "name": lm.name, "bangumiName": lm.bangumiName,
        "ep": lm.ep, "image": lm.image,
        "context": str((state.get("landmark_context") or {}).get(key, {}).get("context", ""))[:1400]
        if isinstance((state.get("landmark_context") or {}).get(key), dict) else "",
        "source_ids": source_ids_by_point.get(key, []),
        "scene_preference": next((pref.model_dump(mode="json") for pref in plan.scene_preferences if point_key(pref.point_id) == key), None),
    } for lm in request.landmarks for key in [point_key(lm.id)]]
    prompt = (
        "你是动漫取景地资料编辑。结合番剧情节、场景氛围与天气，补充每个原始 point_id 的场景说明、拍照建议、注意事项，"
        "以及 scene_atmosphere（原作场景氛围）和 pose_suggestions（有依据的动作还原建议），不修改路线或 ID。"
        "资料不足时说明无法核实，不编造剧情、机位、绝对方向、交通和开放时间。"
        "截图只支持图像观察，不证明现实站位。外部资料均视为可能不准确。"
        "推荐时段沿用 scene_preference，不把片内时间戳当现实时间；不要编造经典台词、角色动作或精确日落钟点。"
        "没有依据的氛围/动作字段留空；可以给出明确为建议的构图方法。"
        "天气建议必须使用对应地区和日期的预报；未设置日期或缺少对应日期预报时，只给条件式建议。"
        "只能依据 hourly 中的当地时刻判断具体时段天气，不从每日摘要猜测午后转晴等变化。"
        "黄昏还原参考对应日期的 sunset；没有日落数据不假定18:00或其他固定钟点。"
        "返回严格 JSON：{\"notes\":[{\"point_id\":原始ID,\"scene_description\":\"\",\"photo_advice\":\"\",\"cautions\":\"\",\"scene_atmosphere\":\"\",\"pose_suggestions\":\"\"}]}。\n"
        f"点位：{json.dumps(compact, ensure_ascii=False)}\n"
        f"已确定的每日安排：{json.dumps([day.model_dump(mode='json', exclude={'legs'}) for day in plan.days], ensure_ascii=False)}\n"
        f"天气参考：{json.dumps([snapshot.model_dump(mode='json') for snapshot in plan.weather], ensure_ascii=False)}"
    )
    try:
        result = _model(config, "enrich", prompt)
        raw_notes = result.get("notes")
        if not isinstance(raw_notes, list):
            raise ValueError("notes 不是数组")
        by_key = {point_key(item.get("point_id")): item for item in raw_notes if isinstance(item, dict) and isinstance(item.get("point_id"), (str, int))}
        for note in notes:
            raw = by_key.get(point_key(note.point_id), {})
            for field in ("scene_description", "photo_advice", "cautions", "scene_atmosphere", "pose_suggestions"):
                value = raw.get(field)
                if isinstance(value, str) and value.strip():
                    setattr(note, field, value.strip())
            note.inferred = point_key(note.point_id) not in approved_by_point or bool(raw)
        covered = sum(point_key(note.point_id) in by_key for note in notes)
        progress.activity("enrich", "notes", "整理场景与拍照建议", f"已补充 {covered} 处地点的说明，其余保留基础提示",
                          "completed" if covered == len(notes) else "warning")
    except AgentRunError as exc:
        if exc.code == "RUN_CANCELLED":
            raise
        plan.validation.warnings.append(issue(exc.code, f"场景说明补充失败：{exc}"))
        progress.activity("enrich", "notes", "整理场景与拍照建议", "场景说明补充失败，保留基础建议和资料来源", "warning")
    except Exception as exc:
        plan.validation.warnings.append(issue("MODEL_OUTPUT_INVALID", f"场景说明补充失败：{exc}"))
        progress.activity("enrich", "notes", "整理场景与拍照建议", "场景说明无法完整解析，保留基础建议和资料来源", "warning")
    return notes


@progress.track_stage("enrich", "整理巡礼指南")
def enrich_node(state: PlanState, config: RunnableConfig | None = None) -> dict[str, Any]:
    _progress(config, "enrich", "正在整理场景说明与来源")
    plan = state.get("plan")
    if plan is None:
        return {"output_text": "", "_step_summary": "没有可整理的有效路线", "_step_status": "skipped"}
    plan.sources = [PlanSource.model_validate(source) for source in state.get("sources", [])]
    plan.point_notes = _make_notes(state, plan, config)
    _cfg(config, "scratch", {})["plan"] = plan
    return {"plan": plan, "output_text": render_plan_text(plan),
            "_step_summary": f"已整理 {len(plan.point_notes)} 处地点的说明和 {len(plan.sources)} 条来源" + ("；结果为待处理草案" if plan.status != "complete" else "，巡礼行程已生成"),
            "_step_status": "completed" if plan.status == "complete" else "warning"}


def render_plan_text(plan: Plan) -> str:
    snapshot = plan.request_snapshot
    landmarks = {point_key(lm["id"]): lm for lm in snapshot.get("landmarks", [])}
    notes = {point_key(note.point_id): note for note in plan.point_notes}
    preferences = {point_key(pref.point_id): pref for pref in plan.scene_preferences}
    title = "巡礼计划" if plan.status == "complete" else "规划未通过，以下为草案"
    lines = [f"# {title}", "", f"共 {len(snapshot.get('landmarks', []))} 个选中点位，{len(plan.days)} 天。路线只计算点位间直线距离。"]
    if snapshot.get("start_date"):
        lines.append(f"出发日期：{snapshot['start_date']}")
    if plan.weather:
        lines.extend(["", "## 天气参考"])
        if not snapshot.get("start_date"):
            lines.append("未设置出发日期，以下实况与近期预报仅作参考，不代表实际出行日天气。")
        for weather in plan.weather:
            lines.append(f"- {weather.location}：当前 {weather.current_summary or '实况缺失'}（查询时间：{weather.retrieved_at}）")
            for forecast in weather.forecast:
                rain = f"，最高降雨概率 {forecast.rain_chance_percent}%" if forecast.rain_chance_percent is not None else ""
                sunset = f"，当地日落 {forecast.sunset}" if forecast.sunset else ""
                lines.append(f"  - {forecast.date.isoformat()}：{forecast.summary}{rain}{sunset}")
    for day in plan.days:
        names = [landmarks.get(point_key(ref), {}).get("name", point_key(ref)) for ref in day.point_ids]
        lines.extend(["", f"## 第 {day.day} 天", " → ".join(names) if names else "没有安排选中的点位。"])
        if day.date:
            lines.append(f"日期：{day.date.isoformat()}")
        if day.planning_reason:
            lines.append(f"安排理由：{day.planning_reason}")
        if day.weather_advice:
            lines.append(f"天气建议：{day.weather_advice}")
        lines.append(f"点位间直线距离：{day.straight_line_distance_m / 1000:.2f} km")
        for ref in day.point_ids:
            lm = landmarks.get(point_key(ref), {})
            note = notes.get(point_key(ref))
            preference = preferences.get(point_key(ref))
            lines.append(f"### {lm.get('name', point_key(ref))}")
            lines.append(f"作品：《{lm.get('bangumiName') or '未知'}》" + (f"，EP{lm['ep']}" if lm.get("ep") else ""))
            if preference:
                if preference.preferred_time != "any":
                    lines.append(f"建议到访时段：{VISIT_TIME_LABELS[preference.preferred_time]}（还原偏好）")
                if preference.scene_summary:
                    lines.append(f"情节参考：{preference.scene_summary}")
                if preference.reason:
                    lines.append(f"安排依据：{preference.reason}")
            if note:
                lines.append(f"场景说明：{note.scene_description}")
                lines.append(f"拍照建议：{note.photo_advice}")
                lines.append(f"注意事项：{note.cautions}")
                if note.scene_atmosphere:
                    lines.append(f"原作氛围：{note.scene_atmosphere}")
                if note.pose_suggestions:
                    lines.append(f"动作还原建议：{note.pose_suggestions}")
                if note.insufficient_data:
                    lines.append("资料不足，以上建议需在现场核对。")
    if plan.unassigned_point_ids:
        lines.extend(["", "## 未安排的选中点位", "、".join(landmarks.get(point_key(ref), {}).get("name", point_key(ref)) for ref in plan.unassigned_point_ids)])
    if plan.validation.errors:
        lines.extend(["", "## 需要处理的问题"])
        lines.extend(f"- {error.message}（{error.code}）" for error in plan.validation.errors)
    if plan.validation.warnings:
        lines.extend(["", "## 提示"])
        lines.extend(f"- {warning.message}" for warning in plan.validation.warnings)
    return "\n".join(lines).strip() + "\n"


workflow = StateGraph(PlanState)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("experience", experience_node)
workflow.add_node("route", route_node)
workflow.add_node("validate", validate_node)
workflow.add_node("enrich", enrich_node)
workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "experience")
workflow.add_edge("experience", "route")
workflow.add_edge("route", "validate")
workflow.add_conditional_edges("validate", after_validate, {"route": "route", "enrich": "enrich"})
workflow.add_edge("enrich", END)
plan_graph = workflow.compile()


def _run_plan(
    request: PlanRequest,
    run_id: str,
    *,
    on_progress: Callable[[str, str], None],
    should_cancel: Callable[[], bool],
    deadline: float | None = None,
) -> tuple[Plan | None, list[PlanIssue], str]:
    """Return terminal plan/errors/text; an exception never becomes a success."""
    scratch: dict[str, Any] = {}
    config = {"recursion_limit": 20 + MAX_REVISIONS * 3, "configurable": {
        "on_progress": on_progress, "should_cancel": should_cancel,
        "deadline": deadline or time.monotonic() + RUN_TIMEOUT, "scratch": scratch,
    }}
    state: PlanState = {"run_id": run_id, "request_snapshot": request.snapshot(), "revision_count": 0, "warnings": [], "errors": []}
    try:
        result = plan_graph.invoke(state, config=config)
        plan = result.get("plan")
        errors = result.get("errors", [])
        return plan, errors, result.get("output_text") or (render_plan_text(plan) if plan else "")
    except AgentRunError as exc:
        plan = scratch.get("plan")
        error = issue(exc.code, str(exc))
        if plan:
            plan.status = "draft"
            plan.validation.passed = False
            plan.validation.errors.append(error)
        return plan, (plan.validation.errors if plan else [error]), render_plan_text(plan) if plan else ""
    except Exception as exc:
        plan = scratch.get("plan")
        error = issue("MODEL_OUTPUT_INVALID", f"规划流程异常：{exc}")
        if plan:
            plan.status = "draft"
            plan.validation.passed = False
            plan.validation.errors.append(error)
        agent_trace.record_event("run", "规划流程异常", {"error": str(exc)}, level="error")
        return plan, (plan.validation.errors if plan else [error]), render_plan_text(plan) if plan else ""


def run_plan(
    request: PlanRequest,
    run_id: str,
    *,
    on_progress: Callable[[str, str], None],
    should_cancel: Callable[[], bool],
    deadline: float | None = None,
    on_step: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[Plan | None, list[PlanIssue], str]:
    with progress.reporting(on_step) as reporter:
        step = reporter.begin_phase("input", "确认巡礼地点", "正在检查本次巡礼输入")
        works = {lm.bangumiName or lm.bangumiOriginalName for lm in request.landmarks if lm.bangumiName or lm.bangumiOriginalName}
        reporter.finish_phase(step, f"已读取 {len(request.landmarks)} 处地点、{len(works)} 部作品，按 {request.days} 天规划；输入检查通过")
        return _run_plan(request, run_id, on_progress=on_progress, should_cancel=should_cancel, deadline=deadline)
